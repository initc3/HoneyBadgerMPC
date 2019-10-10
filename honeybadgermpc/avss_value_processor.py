import asyncio
import logging
from pickle import dumps, loads
from collections import defaultdict
from honeybadgermpc.broadcast.commonsubset import run_common_subset
from honeybadgermpc.utils.misc import wrap_send, subscribe_recv
from honeybadgermpc.utils.sequencer import Sequencer


class AvssValueProcessor(object):
    # How long to wait before running another instance of ACS?
    ACS_PERIOD_IN_SECONDS = 1

    # Delimiter to separate two batches in the output queue.
    BATCH_DELIMITER = None

    def __init__(self, pk, sk, n, t, my_id, send, recv, get_input, chunk_size=1):
        # This stores the AVSSed values which have been received from each dealer.
        self.inputs_per_dealer = [list() for _ in range(n)]

        # This stores the AVSSed values for each dealer which have been agreed.
        # This is a list of Futures which are marked done when the value is received.
        # The Future gurantees that the AVSS value has been agreed by at least `t+1`
        # parties and will resolve to a share once it is received by this node.
        self.outputs_per_dealer = [list() for _ in range(n)]

        # This stores a list of the indices of the next AVSS value to be returned
        # when a consumer requests a value dealt from a particular dealer.
        self.next_idx_to_return_per_dealer = [0] * n

        # The input to ACS is the count of values received at this node dealt by all
        # the nodes. In order to get the share of the same element at each node the
        # ordering of messages per dealer needs to be ensured. This is ensured by a
        # using an instance of a sequencer per dealer. The sequencer buffers any values
        # received out of order and delivers them in an order based on the AVSS Id.
        self.sequencers = defaultdict(Sequencer)

        # This queue contains values AVSSed from all nodes such that at least `n-t`
        # nodes have received a value corresponding to a particular batch.
        # Eg: Let the following be the set of values received by all nodes:
        #
        #   |  0  |  1  |  2  |  3  |
        #   -------------------------
        #   |  x0 |  x1 |     |     |  => Each row is a batch.
        #   |     |     |     |     |
        #
        # n=4, t=1. Since n-t nodes have not yet received a value therefore we will not
        # add any of the available values to the output. Once we get a value dealt from
        # 2 or 3, then we can go ahead and output all the available values to the queue.
        self.output_queue = asyncio.Queue()

        # This is for retrieving consecutive values from the same dealer in a situation
        # when they are coupled to each other. This is true for triples and powers.
        self.chunk_size = chunk_size

        subscribe_recv_task, subscribe = subscribe_recv(recv)
        self.tasks = [subscribe_recv_task]

        def _get_send_recv(tag):
            return wrap_send(tag, send), subscribe(tag)

        self.get_send_recv = _get_send_recv

        self.pk, self.sk = pk, sk
        self.n, self.t, self.my_id = n, t, my_id
        self.get_input = get_input

    async def get(self):
        return await self.output_queue.get()

    async def _recv_loop(self):
        logging.debug("[%d] Starting _recv_loop", self.my_id)
        while True:
            dealer_id, avss_id, avss_value = await self.get_input()
            assert type(dealer_id) is int
            assert dealer_id >= 0 and dealer_id < self.n
            assert type(avss_id) is int
            assert avss_id >= 0

            self.sequencers[dealer_id].add((avss_id, avss_value))

            # Process the values only if they are in order.
            while self.sequencers[dealer_id].is_next_available():
                _, avss_value = self.sequencers[dealer_id].get()

                # Add the value to the input list based on who dealt the value
                self.inputs_per_dealer[dealer_id].append(avss_value)

                # If this value has already been agreed upon by other parties
                # then it means that its Future has been added to the output list.
                # So we need to set the result of that future to be equal to this value.
                idx = len(self.inputs_per_dealer[dealer_id]) - 1
                if idx < len(self.outputs_per_dealer[dealer_id]):
                    assert not self.outputs_per_dealer[dealer_id][idx].done()
                    self.outputs_per_dealer[dealer_id][idx].set_result(avss_value)

    async def _acs_runner(self):
        logging.debug("[%d] Starting ACS runner", self.my_id)
        acs_counter = 0
        while True:
            # Sleep first, then run so that you wait until some values are received
            await asyncio.sleep(AvssValueProcessor.ACS_PERIOD_IN_SECONDS)
            sid = f"AVSS-ACS-{acs_counter}"
            logging.debug("[%d] ACS Id: %s", self.my_id, sid)
            await self._run_acs_to_process_values(sid)
            acs_counter += 1

    def _process_acs_output(self, pickled_acs_outputs):
        # Do a transpose of the AVSS counts from each party.
        #
        # acs_outputs[i][j] -> Represents the number of AVSSed
        # values received by node `i` dealt by node `j`.
        #
        # counts_view_at_all_nodes[i][j] -> Represents the number of AVSSed values
        # which have been dealt by node `i` and received at node `j`.
        #
        # Each row is basically a node's view of its own
        # values which have been received by other nodes.

        # Some parties may be slow in submitting their inputs and as a result ACS might
        # return None for them. In order to handle this, initialize acs_outputs to be
        # the same as the current set of agreed output values for that party. This
        # indicates that the parties which were late are treated as if it has not seen
        # any new values.
        acs_outputs = [None] * self.n
        default_acs_output = [len(self.outputs_per_dealer[j]) for j in range(self.n)]
        for i, pickled_acs_output in enumerate(pickled_acs_outputs):
            if pickled_acs_output is not None:
                acs_outputs[i] = loads(pickled_acs_output)
            else:
                acs_outputs[i] = default_acs_output[::]

        logging.debug("[%d] ACS output: %s", self.my_id, acs_outputs)
        counts_view_at_all_nodes = list(map(list, zip(*acs_outputs)))

        logging.debug("[%d] Counts View: %s", self.my_id, counts_view_at_all_nodes)

        # After you have every node's view, you find the kth largest element in each
        # row where k = n-(t+1). This element denotes the minimum number of values
        # which have been received by at least t+1 nodes.

        # This is done by sorting each row and then retrieiving the kth element.
        # This is n^2[log(n)], and can be optimized to expected n^2 using a variant
        # of randomized quick sort.
        for i in range(self.n):
            counts_view_at_all_nodes[i].sort()  # This is the nlog(n) part.
            agreed_value_count = counts_view_at_all_nodes[i][self.n - (self.t + 1)]

            # This agreed count should always be more than the number
            # of outputs which are available at any instant on any node.
            assert len(self.outputs_per_dealer[i]) <= agreed_value_count

            # You take the total number of values which have already been agreed upon
            # and are present in the output and compare it with the new agreed count.
            # If more values have been agreed upon then you add them to the output list
            # by adding a Future object.
            for j in range(len(self.outputs_per_dealer[i]), agreed_value_count):
                future = asyncio.Future()
                self.outputs_per_dealer[i].append(future)
                # If the output value has already been recieved by this node then
                # you also set the result of the future to the corresponding value.
                if j < len(self.inputs_per_dealer[i]):
                    future.set_result(self.inputs_per_dealer[i][j])

        self._add_to_output_queue()

    def _add_to_output_queue(self):
        # TODO: This can definitelt be optimized for space.
        # The first loop is probably not needed.

        # Get all the values dealt by each dealer which have been agreed and not
        # yet added to the output queue. i_th row represents the set of values
        # dealt by the i_th dealer.
        pending_values = [None] * self.n
        pending_counts = [0] * self.n
        for i in range(self.n):
            s, e = (
                self.next_idx_to_return_per_dealer[i],
                len(self.outputs_per_dealer[i]),
            )
            assert e - s >= 0
            pending_values[i] = list(self.outputs_per_dealer[i][s:])
            pending_counts[i] = len(pending_values[i])

        pending_counts.sort()
        # The t_th index represents the maximum values which at least `n-t` nodes have
        # received. So we can add at max `pending_counts[t]` values to the output queue
        # from the `n-t` nodes. We pick all the values from the nodes which have less
        # than `pending_counts[t]`. Values are added in a round robin order from all
        # nodes until all the required values have been added.

        # |  0  |  1  |  2  |  3  |
        # -------------------------
        # | 00  | 10  | 20  | 30  |  => Each row is a batch.
        # | 01  | 11  | 21  | 31  |
        # |     | 12  | 22  | 32  |
        # |     |     | 23  | 33  |
        # |     |     |     | 34  |
        # |     |     |     | 35  |

        # Counts => [2, 3, 4, 6]

        # Sorted in ascending order:
        # max_values_to_output_per_dealer = pending_counts[t] = t_th idx value = 3
        # Batch 1 => 00, 10, 20, 30
        # Batch 2 => 01, 11, 21, 31
        # Batch 3 => 12, 22, 32

        # We want values from at least `n-t` nodes in one batch.

        # AVSS Value Proessor Output Order =>
        # 00, 10, 20, 30, None, 01, 11, 21, 31, None, 12, 22, 32, None
        # `None` is the batch delimiter here.
        max_values_to_output_per_dealer = pending_counts[self.t] // self.chunk_size
        for i in range(max_values_to_output_per_dealer):
            for j in range(self.n):
                if len(pending_values[j]) // self.chunk_size > i:
                    for k in range(self.chunk_size):
                        self.output_queue.put_nowait(pending_values[j][i + k])
                        # Increment the index of the next return value for this dealer
                        self.next_idx_to_return_per_dealer[j] += 1
            self.output_queue.put_nowait(AvssValueProcessor.BATCH_DELIMITER)

    async def _run_acs_to_process_values(self, sid):
        # Get a count of all values which have been received
        # until now from all the other participating nodes.
        value_counts_per_dealer = [
            len(self.inputs_per_dealer[i]) for i in range(self.n)
        ]

        acs_input = dumps(value_counts_per_dealer)
        logging.debug(
            "[%d] ACS [%s] Input:%s", self.my_id, sid, value_counts_per_dealer
        )

        send, recv = self.get_send_recv(sid)

        acs_outputs = await run_common_subset(
            sid, self.pk, self.sk, self.n, self.t, self.my_id, send, recv, acs_input
        )

        assert type(acs_outputs) is tuple
        assert len(acs_outputs) == self.n

        logging.debug("[%d] ACS [%s] completed", self.my_id, sid)

        # The output of ACS is a tuple of `n` entries.
        # Each entry denotes the count of AVSSed values which
        # that node has received from each of the other nodes.
        self._process_acs_output(acs_outputs)

        logging.debug("[%d] All values processed [%s]", self.my_id, sid)

    def __enter__(self):
        self.tasks.append(asyncio.create_task(self._recv_loop()))
        self.tasks.append(asyncio.create_task(self._acs_runner()))
        return self

    def __exit__(self, type, value, traceback):
        for task in self.tasks:
            task.cancel()
