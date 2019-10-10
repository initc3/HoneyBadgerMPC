import asyncio
from pytest import mark
from contextlib import ExitStack
from pickle import dumps
from honeybadgermpc.avss_value_processor import AvssValueProcessor
from honeybadgermpc.broadcast.crypto.boldyreva import dealer


@mark.asyncio
async def test_avss_value_processor_with_diff_inputs(test_router):
    n, t = 4, 1
    sends, recvs, _ = test_router(n)

    node_inputs = [
        [(0, 0, "00"), (1, 0, "10"), (2, 0, "20")],
        [(0, 0, "01")],
        [(0, 0, "02"), (2, 0, "22"), (3, 0, "32")],
        [(3, 0, "33")],
    ]

    get_tasks = [None] * n
    pk, sks = dealer(n, t + 1)
    avss_value_procs = [None] * n
    input_qs = [None] * n
    with ExitStack() as stack:
        for i in range(n):
            input_qs[i] = asyncio.Queue()
            for node_input in node_inputs[i]:
                input_qs[i].put_nowait(node_input)

            avss_value_procs[i] = AvssValueProcessor(
                pk, sks[i], n, t, i, sends[i], recvs[i], input_qs[i].get
            )
            stack.enter_context(avss_value_procs[i])
            get_tasks[i] = asyncio.create_task(avss_value_procs[i].get())

        futures = await asyncio.gather(*get_tasks)
        for i, future in enumerate(futures):
            assert type(future) is asyncio.Future
            if i == 3:
                # node 3 does not receive the value dealt from node 0
                assert not future.done()
            else:
                # all other nodes have received the value dealt from node 0
                assert (await future) == f"0{i}"

        # this is based on node_inputs
        inputs = [[1, 1, 1, 0], [1, 0, 0, 0], [1, 0, 1, 1], [0, 0, 0, 1]]
        # this is based on the fact that only values dealt by 0 and 2 have been agreed
        outputs = [[1, 0, 1, 1], [1, 0, 1, 1], [1, 0, 1, 1], [1, 0, 1, 1]]

        for j, proc in enumerate(avss_value_procs):
            assert [len(proc.inputs_per_dealer[i]) for i in range(n)] == inputs[j]
            assert [len(proc.outputs_per_dealer[i]) for i in range(n)] == outputs[j]
            # 1 value was already retrieved, two values and 1 batch delimiter expected
            assert proc.output_queue.qsize() == 3
            # The values from 0, 2 and 3 have been added to the queue so their
            # next indices should be updated
            assert proc.next_idx_to_return_per_dealer == [1, 0, 1, 1]

        for i in range(n):
            if i in [0, 2]:
                # only nodes 0 and 2 have received the value dealt by 2
                # executing this sequentially also ensurs that ACS is not run again
                # since this value is already available
                assert (await (await avss_value_procs[i].get())) == f"2{i}"
            else:
                # nodes 1 and 3 have not received the value dealt by 2
                assert not (await avss_value_procs[i].get()).done()

        for j, proc in enumerate(avss_value_procs):
            assert [len(proc.inputs_per_dealer[i]) for i in range(n)] == inputs[j]
            assert [len(proc.outputs_per_dealer[i]) for i in range(n)] == outputs[j]
            # values from node 0 and 1 have been requested
            assert proc.next_idx_to_return_per_dealer == [1, 0, 1, 1]


# [i][j] -> Represents the number of AVSSed values
# received by node `i` dealt by node `j`.
@mark.parametrize(
    "n, t, output_counts, next_idx, acs_outputs",
    (
        # When only one party has received one AVSSed value.
        (
            4,
            1,
            [0, 0, 0, 0],
            [0, 0, 0, 0],
            (
                dumps([1, 0, 0, 0]),
                dumps([0, 0, 0, 0]),
                dumps([0, 0, 0, 0]),
                dumps([0, 0, 0, 0]),
            ),
        ),
        # When only one party has received AVSSed values from all nodes.
        (
            4,
            1,
            [0, 0, 0, 0],
            [0, 0, 0, 0],
            (
                dumps([1, 1, 1, 1]),
                dumps([0, 0, 0, 0]),
                dumps([0, 0, 0, 0]),
                dumps([0, 0, 0, 0]),
            ),
        ),
        # When only one party has received AVSSed values from a subset of nodes.
        (
            4,
            1,
            [0, 0, 0, 0],
            [0, 0, 0, 0],
            (
                dumps([1, 0, 1, 0]),
                dumps([0, 0, 0, 0]),
                dumps([0, 0, 0, 0]),
                dumps([0, 0, 0, 0]),
            ),
        ),
        # When each party has received a value only from itself.
        (
            4,
            1,
            [0, 0, 0, 0],
            [0, 0, 0, 0],
            (
                dumps([1, 0, 0, 0]),
                dumps([0, 1, 0, 0]),
                dumps([0, 0, 1, 0]),
                dumps([0, 0, 0, 1]),
            ),
        ),
        # When each party has received a value from some other party but
        # t+1 parties have not yet received the same value.
        (
            4,
            1,
            [0, 0, 0, 0],
            [0, 0, 0, 0],
            (
                dumps([0, 0, 0, 1]),
                dumps([0, 0, 1, 0]),
                dumps([0, 1, 0, 0]),
                dumps([1, 0, 0, 0]),
            ),
        ),
        # When one party has received more than 1 value from multiple parties.
        (
            4,
            1,
            [0, 0, 0, 0],
            [0, 0, 0, 0],
            (
                dumps([2, 3, 4, 5]),
                dumps([0, 0, 0, 0]),
                dumps([0, 0, 0, 0]),
                dumps([0, 0, 0, 0]),
            ),
        ),
        # When two parties other than the current node receive the same value.
        (
            4,
            1,
            [0, 1, 0, 0],
            [0, 0, 0, 0],
            (
                dumps([0, 1, 0, 0]),
                dumps([0, 1, 0, 0]),
                dumps([0, 0, 0, 0]),
                dumps([0, 0, 0, 0]),
            ),
        ),
        # When all parties other than the current node receive the same value.
        (
            4,
            1,
            [0, 1, 0, 0],
            [0, 0, 0, 0],
            (
                dumps([0, 1, 0, 0]),
                dumps([0, 1, 0, 0]),
                dumps([0, 1, 0, 0]),
                dumps([0, 1, 0, 0]),
            ),
        ),
        # When two parties other than the current node receive the same values.
        (
            4,
            1,
            [0, 4, 0, 0],
            [0, 0, 0, 0],
            (
                dumps([0, 4, 0, 0]),
                dumps([0, 4, 0, 0]),
                dumps([0, 0, 0, 0]),
                dumps([0, 0, 0, 0]),
            ),
        ),
        # When all parties other than the current node receive the same values.
        (
            4,
            1,
            [0, 4, 0, 0],
            [0, 0, 0, 0],
            (
                dumps([0, 4, 0, 0]),
                dumps([0, 4, 0, 0]),
                dumps([0, 4, 0, 0]),
                dumps([0, 4, 0, 0]),
            ),
        ),
        # When two parties other than the current node receive at least k values.
        (
            4,
            1,
            [0, 4, 0, 0],
            [0, 0, 0, 0],
            (
                dumps([0, 4, 0, 0]),
                dumps([0, 10, 0, 0]),
                dumps([0, 0, 0, 0]),
                dumps([0, 0, 0, 0]),
            ),
        ),
        # When all parties other than the current node receive at least k values.
        (
            4,
            1,
            [0, 4, 0, 0],
            [0, 0, 0, 0],
            (
                dumps([0, 4, 0, 0]),
                dumps([0, 10, 0, 0]),
                dumps([0, 4, 0, 0]),
                dumps([0, 4, 0, 0]),
            ),
        ),
        # When t+1 parties other than the current node receive at least k values.
        (
            4,
            1,
            [0, 6, 0, 0],
            [0, 0, 0, 0],
            (
                dumps([0, 4, 0, 0]),
                dumps([0, 5, 0, 0]),
                dumps([0, 6, 0, 0]),
                dumps([0, 7, 0, 0]),
            ),
        ),
        (
            4,
            1,
            [3, 5, 3, 5],
            [3, 3, 3, 3],
            (
                dumps([1, 5, 4, 2]),
                dumps([2, 5, 3, 3]),
                dumps([3, 2, 0, 5]),
                dumps([4, 3, 0, 9]),
            ),
        ),
        (
            4,
            1,
            [0, 3, 2, 1],
            [0, 1, 1, 1],
            (
                dumps([0, 4, 0, 2]),
                dumps([0, 3, 0, 1]),
                dumps([0, 3, 2, 1]),
                dumps([4, 3, 8, 1]),
            ),
        ),
        (
            7,
            2,
            [4, 3, 5, 0, 4, 6, 2],
            [3, 3, 3, 0, 3, 3, 2],
            (
                dumps([0, 4, 1, 0, 2, 1, 0]),
                dumps([0, 3, 2, 0, 1, 1, 0]),
                dumps([0, 3, 3, 0, 3, 8, 1]),
                dumps([4, 3, 4, 0, 4, 6, 2]),
                dumps([0, 3, 5, 0, 6, 3, 3]),
                dumps([4, 3, 6, 8, 5, 9, 2]),
                dumps([4, 3, 7, 5, 4, 3, 4]),
            ),
        ),
    ),
)
@mark.asyncio
async def test_acs_output(n, t, output_counts, next_idx, acs_outputs):
    my_id = 0

    input_q = asyncio.Queue()
    with AvssValueProcessor(None, None, n, t, my_id, None, None, input_q.get) as proc:
        proc._process_acs_output(acs_outputs)
        assert [len(proc.outputs_per_dealer[i]) for i in range(n)] == output_counts
        for i in range(n):
            for output in proc.outputs_per_dealer[i]:
                assert type(output) is asyncio.Future

        # These are set by another method and shouldn't have been updated.
        assert all(len(proc.inputs_per_dealer[i]) == 0 for i in range(n))
        assert proc.next_idx_to_return_per_dealer == next_idx


# [i][j] -> Represents the number of AVSSed values
# received by node `i` dealt by node `j`.
@mark.parametrize(
    "k, acs_outputs",
    (
        # When two parties receive the same value.
        (
            1,
            (
                dumps([1, 0, 0, 0]),
                dumps([1, 0, 0, 0]),
                dumps([0, 0, 0, 0]),
                dumps([0, 0, 0, 0]),
            ),
        ),
        # When all parties receive the same value.
        (
            1,
            (
                dumps([1, 0, 0, 0]),
                dumps([1, 0, 0, 0]),
                dumps([1, 0, 0, 0]),
                dumps([1, 0, 0, 0]),
            ),
        ),
        (
            3,
            (
                dumps([3, 0, 0, 0]),
                dumps([4, 0, 0, 0]),
                dumps([0, 0, 0, 0]),
                dumps([1, 0, 0, 0]),
            ),
        ),
    ),
)
@mark.asyncio
async def test_with_agreed_values_on_same_node_with_input(k, acs_outputs):
    n, t, my_id = 4, 1, 0

    input_q = asyncio.Queue()
    with AvssValueProcessor(None, None, n, t, my_id, None, None, input_q.get) as proc:
        for i in range(k):
            value = (my_id, i, i)  # dealer_id, avss_id, value
            input_q.put_nowait(value)
        await asyncio.sleep(0.1)  # Give the recv loop a chance to run
        proc._process_acs_output(acs_outputs)

        assert [len(proc.inputs_per_dealer[i]) for i in range(n)] == [k, 0, 0, 0]
        assert [len(proc.outputs_per_dealer[i]) for i in range(n)] == [k, 0, 0, 0]
        for i in range(k):
            assert type(proc.outputs_per_dealer[my_id][i]) is asyncio.Future
            assert proc.outputs_per_dealer[my_id][i].done()
            assert (await proc.outputs_per_dealer[my_id][i]) == i

        # This is set by another method and should not have been updated.
        assert all(proc.next_idx_to_return_per_dealer[i] == 0 for i in range(n))


# [i][j] -> Represents the number of AVSSed values
# received by node `i` dealt by node `j`.
@mark.parametrize(
    "k, acs_outputs",
    (
        # When two parties other than the current node receive the same value.
        (
            1,
            (
                dumps([0, 1, 0, 0]),
                dumps([0, 1, 0, 0]),
                dumps([0, 0, 0, 0]),
                dumps([0, 0, 0, 0]),
            ),
        ),
        # When all parties other than the current node receive the same value.
        (
            1,
            (
                dumps([0, 1, 0, 0]),
                dumps([0, 1, 0, 0]),
                dumps([0, 1, 0, 0]),
                dumps([0, 1, 0, 0]),
            ),
        ),
    ),
)
@mark.asyncio
async def test_with_agreed_values_on_another_node_with_input(k, acs_outputs):
    n, t, sender_id = 4, 1, 1

    input_q = asyncio.Queue()
    with AvssValueProcessor(None, None, n, t, 0, None, None, input_q.get) as proc:
        proc._process_acs_output(acs_outputs)

        # 0th node has not received any AVSSed value from node 1 yet
        assert [len(proc.inputs_per_dealer[i]) for i in range(n)] == [0, 0, 0, 0]
        # 0th node should however know that one value sent by 1st node has been agreed
        assert [len(proc.outputs_per_dealer[i]) for i in range(n)] == [0, k, 0, 0]
        for i in range(k):
            assert type(proc.outputs_per_dealer[sender_id][i]) is asyncio.Future
            # This value is not yet available
            assert not proc.outputs_per_dealer[sender_id][i].done()

        # This is set by another method and should not have been updated.
        assert all(proc.next_idx_to_return_per_dealer[i] == 0 for i in range(n))

        for i in range(k):
            value = (sender_id, i, i)  # dealer_id, avss_id, value
            input_q.put_nowait(value)  # Make the 0th node receive the value now

        await asyncio.sleep(0.1)  # Give the recv loop a chance to run

        # 0th node has received the AVSSed value from node 1
        assert [len(proc.inputs_per_dealer[i]) for i in range(n)] == [0, k, 0, 0]
        # 0th node already knows that one value sent by 1st node has been agreed
        assert [len(proc.outputs_per_dealer[i]) for i in range(n)] == [0, k, 0, 0]
        for i in range(k):
            assert proc.outputs_per_dealer[sender_id][i].done()
            assert (await proc.outputs_per_dealer[sender_id][i]) == i

        # This is set by another method and should not have been updated.
        assert all(proc.next_idx_to_return_per_dealer[i] == 0 for i in range(n))


@mark.parametrize(
    "n, t, b, input_next_ids, output_next_ids, per_dealer_input, output_queue_vals",
    (
        (4, 1, 1, [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], []),  # 1 test case
        (4, 1, 1, [0, 0, 0, 0], [0, 0, 0, 0], [0, 1, 0, 0], []),
        (4, 1, 1, [0, 0, 0, 0], [0, 0, 0, 0], [0, 1, 1, 0], []),
        # b = 3, we want to get a triple, so we need at least three values per dealer
        (4, 1, 3, [0, 0, 0, 0], [0, 0, 0, 0], [2, 2, 2, 2], []),
        (4, 1, 3, [0, 0, 0, 0], [0, 0, 0, 0], [0, 2, 0, 0], []),
        (4, 1, 3, [0, 0, 0, 0], [0, 0, 0, 0], [0, 3, 0, 0], []),
        (4, 1, 3, [0, 0, 0, 0], [0, 0, 0, 0], [0, 10, 0, 0], []),
        (
            4,
            1,
            3,
            [0, 0, 0, 0],
            [0, 3, 3, 3],
            [0, 3, 3, 3],
            ["10", "11", "12", "20", "21", "22", "30", "31", "32", None],
        ),
        (
            4,
            1,
            3,
            [0, 0, 0, 0],
            [0, 3, 3, 3],
            [0, 3, 6, 6],
            ["10", "11", "12", "20", "21", "22", "30", "31", "32", None],
        ),
        (4, 1, 1, [0, 0, 0, 0], [1, 1, 1, 0], [1, 1, 1, 0], ["00", "10", "20", None]),
        (
            4,
            1,
            1,
            [0, 0, 0, 0],
            [1, 1, 1, 1],
            [1, 1, 1, 1],
            ["00", "10", "20", "30", None],
        ),
        (
            4,
            1,
            1,
            [0, 0, 0, 0],
            [1, 1, 1, 1],
            [1, 1, 2, 1],
            ["00", "10", "20", "30", None],
        ),
        (
            4,
            1,
            1,
            [0, 0, 0, 0],
            [1, 1, 1, 1],
            [1, 1, 2, 2],
            ["00", "10", "20", "30", None],
        ),
        (
            4,
            1,
            1,
            [0, 0, 0, 0],
            [1, 1, 1, 1],
            [1, 1, 2, 2],
            ["00", "10", "20", "30", None],
        ),
        (
            4,
            1,
            1,
            [0, 0, 0, 0],
            [1, 2, 2, 2],
            [1, 2, 2, 2],
            ["00", "10", "20", "30", None, "11", "21", "31", None],
        ),
        (
            4,
            1,
            1,
            [0, 0, 0, 0],
            [2, 2, 2, 2],
            [2, 2, 2, 2],
            ["00", "10", "20", "30", None, "01", "11", "21", "31", None],
        ),
        (4, 1, 1, [1, 0, 1, 0], [1, 1, 2, 1], [1, 2, 2, 2], ["10", "21", "30", None]),
        (
            4,
            1,
            1,
            [1, 0, 1, 0],
            [1, 2, 3, 2],
            [1, 2, 3, 2],
            ["10", "21", "30", None, "11", "22", "31", None],
        ),
        (4, 1, 1, [1, 0, 1, 0], [1, 0, 1, 0], [1, 0, 1, 0], []),
        (4, 1, 1, [1, 0, 1, 0], [1, 0, 1, 0], [1, 0, 1, 0], []),
        (4, 1, 1, [1, 2, 3, 4], [1, 2, 3, 4], [1, 2, 3, 4], []),
        (
            7,
            2,
            1,
            [0, 0, 0, 0, 0, 1, 0],
            [0, 0, 0, 0, 0, 1, 0],
            [0, 0, 1, 1, 1, 1, 1],
            [],
        ),
        (
            7,
            2,
            1,
            [0, 0, 0, 0, 0, 1, 0],
            [0, 1, 1, 1, 1, 1, 1],
            [0, 1, 1, 1, 1, 1, 1],
            ["10", "20", "30", "40", "60", None],
        ),
    ),
)
@mark.asyncio
async def test_add_to_output_queue(
    n, t, b, input_next_ids, output_next_ids, per_dealer_input, output_queue_vals
):
    """
    Each row is a test case.
    This test runs on only one node.
    This is to test the part of code which runs after ACS i.e. all nodes see the same
    view of the output list and they have to add a set of values in the output queue
    in the same order such that each batch of values has values from at least `n-t`
    dealers.



    input_next_idx:     This denotes the index which has the next value to be added to
                        the output queue for a particular dealer. Basically this
                        represents the state of already outputted values.
    output_next_ids:    This denotes the next index to return after the values have been
                        added to the output queue. This is to verify the output.
    per_dealer_input:   This is the count of values that have been received by this node
                        per dealer. We take this list and add as many values as the
                        counts in the output list. The output list is the one which gets
                        updated after ACS and all nodes have the same view of the output
                        list.
    output_queue_vals:  This is for verification. This denotes the order in which the
                        output values should be available in the queue. THe first
                        character is the node who dealt the value and the second
                        character is the count starting from 0 for each dealer.


    We want to verify the AVSS Value Proessor Output Order.

    |  0  |  1  |  2  |  3  |
    -------------------------
    | 00  | 10  | 20  | 30  |  => Each row is a batch.
    | 01  | 11  | 21  | 31  |
    |     | 12  | 22  | 32  |
    |     |     | 23  | 33  |
    |     |     |     | 34  |
    |     |     |     | 35  |

    Counts => [2, 3, 4, 6]
    Sorted in ascending order:
    max_values_to_output_per_dealer = pending_counts[t] = t_th idx value = 3
    Batch 1 => 00, 10, 20, 30
    Batch 2 => 01, 11, 21, 31
    Batch 3 => 12, 22, 32
    AVSS Value Proessor Output Order => 00, 10, 20, 30, 01, 11, 21, 31, 12, 22, 32
    """
    avss_proc = AvssValueProcessor(None, None, n, t, 0, None, None, None, b)
    avss_proc.next_idx_to_return_per_dealer = input_next_ids
    for i in range(n):
        for j in range(per_dealer_input[i]):
            avss_proc.outputs_per_dealer[i].append(f"{i}{j}")
    avss_proc._add_to_output_queue()
    assert output_next_ids == avss_proc.next_idx_to_return_per_dealer
    assert len(output_queue_vals) == avss_proc.output_queue.qsize()
    for val in output_queue_vals:
        assert val == avss_proc.output_queue.get_nowait()
