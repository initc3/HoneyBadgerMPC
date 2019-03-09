import asyncio
import logging
from pickle import dumps, loads
from honeybadgermpc.protocols.commonsubset import run_common_subset
from honeybadgermpc.exceptions import HoneyBadgerMPCError


class NotEnoughAVSSValuesError(HoneyBadgerMPCError):
    pass


class AvssValueProcessor(object):

    def __init__(self, pk, sk, n, t, my_id, send, recv, get_input):

        # This stores the AVSSed values which have been received from each dealer.
        self.inputs_per_dealer = [list() for _ in range(n)]

        # This stores the AVSSed values for each dealer which have been agreed.
        # This is a list of Futures which are marked done when the value is received.
        # The Future gurantees that the AVSS value has been agreed by at least `t+1`
        # parties and will resolve to the value once it is received by this node.
        self.outputs_per_dealer = [list() for _ in range(n)]

        # This stores a list of the idxes of the next AVSS value to be returned
        # when a consumer requests a value dealt from a particular dealer.
        self.next_idx_to_return_per_dealer = [0]*n

        self.pk, self.sk = pk, sk
        self.n, self.t, self.my_id = n, t, my_id
        self.send, self.recv = send, recv
        self.get_input = get_input

    async def get_value_future(self, dealer_id):
        assert type(dealer_id) is int
        assert dealer_id >= 0 and dealer_id < self.n

        next_id = self.next_idx_to_return_per_dealer[dealer_id]
        outputs = self.outputs_per_dealer[dealer_id]

        # If we have already added the Future for the next value to be returned
        # then we just return a reference to that future and increment the next idx.
        if next_id < len(outputs):
            logging.debug("[%d] Future already available, id: %d", self.my_id, next_id)
            future = self.outputs_per_dealer[dealer_id][next_id]
            self.next_idx_to_return_per_dealer[dealer_id] += 1
            return future

        # If we don't have the Future then we need to run ACS and then check again.
        logging.debug("[%d] Future not available, will need to run ACS", self.my_id)
        await self._process_values()

        next_id = self.next_idx_to_return_per_dealer[dealer_id]
        outputs = self.outputs_per_dealer[dealer_id]
        if next_id < len(outputs):
            logging.debug("[%d] Future available after ACS, id: %d", self.my_id, next_id)
            future = self.outputs_per_dealer[dealer_id][next_id]
            self.next_idx_to_return_per_dealer[dealer_id] += 1
            return future

        logging.error(
            "[%d] No value from dealer [%d] even after ACS", self.my_id, dealer_id)
        raise NotEnoughAVSSValuesError(f"DealerId: {dealer_id}")

    async def _recv_loop(self):
        logging.debug("[%d] Starting recv_loop", self.my_id)

        while True:
            dealer_id, avss_value = await self.get_input()
            assert type(dealer_id) is int
            assert dealer_id >= 0 and dealer_id < self.n

            # Add the value to the input list based on who dealt the value
            self.inputs_per_dealer[dealer_id].append(avss_value)

            # If this value has already been agreed upon by other parties
            # then it means that its Future has been added to the output list.
            # So we need to set the result of that future to be equal to this value.
            idx = len(self.inputs_per_dealer[dealer_id])-1
            if idx < len(self.outputs_per_dealer[dealer_id]):
                assert not self.outputs_per_dealer[dealer_id][idx].done()
                self.outputs_per_dealer[dealer_id][idx].set_result(avss_value)

    def _process_acs_output(self, acs_outputs):
        # This loop does a transpose of the AVSS counts from each party.
        #
        # acs_outputs[i][j] -> Represents the number of AVSSed
        # values received by node `i` dealt by node `j`.
        #
        # counts_view_at_all_nodes[i][j] -> Represents the number of AVSSed values
        # which have been dealt by node `i` and received at node `j`.
        #
        # Each row is basically a node's view of its own
        # values which have been received by other nodes.

        counts_view_at_all_nodes = [[0 for _ in range(self.n)] for _ in range(self.n)]
        for i in range(self.n):
            value_counts_at_node = loads(acs_outputs[i])
            assert type(value_counts_at_node) == list
            assert len(value_counts_at_node) == self.n
            for j in range(self.n):
                counts_view_at_all_nodes[j][i] = value_counts_at_node[j]

        # After you have every node's view, you find the kth largest element in each
        # row where k = n-(t+1). This element denotes the minimum number of values
        # which have been received by at least t+1 nodes.

        # This is done by sorting each row and then retrieiving the kth element.
        # This is n^2[log(n)], and can be optimized to expected n^2 using a variant
        # of randomized quick sort.
        for i in range(self.n):
            counts_view_at_all_nodes[i].sort()  # This is the nlog(n) part.
            agreed_value_count = counts_view_at_all_nodes[i][self.n-(self.t+1)]

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

    async def _process_values(self):
        # Get a count of all values which have been received
        # until now from all the other participating nodes.
        value_counts_per_dealer = [len(self.inputs_per_dealer[i]) for i in range(self.n)]

        acs_input = dumps(value_counts_per_dealer)
        logging.debug("[%d] Starting ACS for AVSS", self.my_id)
        logging.debug("[%d] ACS Input: %s", self.my_id, value_counts_per_dealer)

        acs_outputs = await run_common_subset(
            "AVSS-ACS",
            self.pk, self.sk,
            self.n, self.t, self.my_id,
            self.send, self.recv,
            acs_input)

        logging.debug("[%d] ACS completed", self.my_id)

        assert type(acs_outputs) is tuple
        assert len(acs_outputs) == self.n

        # The output of ACS is a tuple of `n` entries.
        # Each entry denotes the count of AVSSed values which
        # that node has received from each of the other nodes.
        self._process_acs_output(acs_outputs)

        logging.debug("[%d] All values processed", self.my_id)

    def __enter__(self):
        self.recv_loop_task = asyncio.create_task(self._recv_loop())
        return self

    def __exit__(self, type, value, traceback):
        self.recv_loop_task.cancel()
