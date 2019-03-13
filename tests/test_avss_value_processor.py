import asyncio
from pytest import mark
from contextlib import ExitStack
from pickle import dumps
from honeybadgermpc.avss_value_processor import AvssValueProcessor
from honeybadgermpc.protocols.crypto.boldyreva import dealer


@mark.asyncio
async def test_avss_value_processor_with_diff_inputs(test_router):
    n, t = 4, 1
    sends, recvs, _ = test_router(n)

    node_inputs = [
        [(0, 0, "00"), (1, 0, "10"), (2, 0, "20")],
        [(0, 0, "01")],
        [(0, 0, "02"), (2, 0, "22")],
        [(3, 0, "33")]
    ]

    get_tasks = [None]*n
    pk, sks = dealer(n, t+1)
    avss_value_procs = [None]*n
    input_qs = [None]*n
    with ExitStack() as stack:
        for i in range(n):
            input_qs[i] = asyncio.Queue()
            for node_input in node_inputs[i]:
                input_qs[i].put_nowait(node_input)

            avss_value_procs[i] = AvssValueProcessor(
                pk, sks[i], n, t, i, sends[i], recvs[i], input_qs[i].get)
            stack.enter_context(avss_value_procs[i])
            get_tasks[i] = asyncio.create_task(avss_value_procs[i].get_value_future(0))

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
        inputs = [
            [1, 1, 1, 0],
            [1, 0, 0, 0],
            [1, 0, 1, 0],
            [0, 0, 0, 1],
        ]
        # this is based on the fact that only values dealt by 0 and 2 have been agreed
        outputs = [
            [1, 0, 1, 0],
            [1, 0, 1, 0],
            [1, 0, 1, 0],
            [1, 0, 1, 0],
        ]

        for j, proc in enumerate(avss_value_procs):
            assert [len(proc.inputs_per_dealer[i]) for i in range(n)] == inputs[j]
            assert [len(proc.outputs_per_dealer[i]) for i in range(n)] == outputs[j]
            # a value from node 0 was requested
            assert proc.next_idx_to_return_per_dealer == [1, 0, 0, 0]

        for i in range(n):
            if i in [0, 2]:
                # only nodes 0 and 2 have received the value dealt by 2
                # executing this sequentially also ensurs that ACS is not run again
                # since this value is already available
                await (await avss_value_procs[i].get_value_future(2)) == f"2{i}"
            else:
                # nodes 1 and 3 have not received the value dealt by 2
                assert not (await avss_value_procs[i].get_value_future(2)).done()

        for j, proc in enumerate(avss_value_procs):
            assert [len(proc.inputs_per_dealer[i]) for i in range(n)] == inputs[j]
            assert [len(proc.outputs_per_dealer[i]) for i in range(n)] == outputs[j]
            # values from node 0 and 1 have been requested
            assert proc.next_idx_to_return_per_dealer == [1, 0, 1, 0]


# [i][j] -> Represents the number of AVSSed values
# received by node `i` dealt by node `j`.
@mark.parametrize("n, t, output_counts, acs_outputs", (
    # When only one party has received one AVSSed value.
    (4, 1, [0, 0, 0, 0], (
        dumps([1, 0, 0, 0]),
        dumps([0, 0, 0, 0]),
        dumps([0, 0, 0, 0]),
        dumps([0, 0, 0, 0]),
    )),
    # When only one party has received AVSSed values from all nodes.
    (4, 1, [0, 0, 0, 0], (
        dumps([1, 1, 1, 1]),
        dumps([0, 0, 0, 0]),
        dumps([0, 0, 0, 0]),
        dumps([0, 0, 0, 0]),
    )),
    # When only one party has received AVSSed values from a subset of nodes.
    (4, 1, [0, 0, 0, 0], (
        dumps([1, 0, 1, 0]),
        dumps([0, 0, 0, 0]),
        dumps([0, 0, 0, 0]),
        dumps([0, 0, 0, 0]),
    )),
    # When each party has received a value only from itself.
    (4, 1, [0, 0, 0, 0], (
        dumps([1, 0, 0, 0]),
        dumps([0, 1, 0, 0]),
        dumps([0, 0, 1, 0]),
        dumps([0, 0, 0, 1]),
    )),
    # When each party has received a value from some other party but
    # t+1 parties have not yet received the same value.
    (4, 1, [0, 0, 0, 0], (
        dumps([0, 0, 0, 1]),
        dumps([0, 0, 1, 0]),
        dumps([0, 1, 0, 0]),
        dumps([1, 0, 0, 0]),
    )),
    # When one party has received more than 1 value from multiple parties.
    (4, 1, [0, 0, 0, 0], (
        dumps([2, 3, 4, 5]),
        dumps([0, 0, 0, 0]),
        dumps([0, 0, 0, 0]),
        dumps([0, 0, 0, 0]),
    )),
    # When two parties other than the current node receive the same value.
    (4, 1, [0, 1, 0, 0], (
        dumps([0, 1, 0, 0]),
        dumps([0, 1, 0, 0]),
        dumps([0, 0, 0, 0]),
        dumps([0, 0, 0, 0]),
    )),
    # When all parties other than the current node receive the same value.
    (4, 1, [0, 1, 0, 0], (
        dumps([0, 1, 0, 0]),
        dumps([0, 1, 0, 0]),
        dumps([0, 1, 0, 0]),
        dumps([0, 1, 0, 0]),
    )),
    # When two parties other than the current node receive the same values.
    (4, 1, [0, 4, 0, 0], (
        dumps([0, 4, 0, 0]),
        dumps([0, 4, 0, 0]),
        dumps([0, 0, 0, 0]),
        dumps([0, 0, 0, 0]),
    )),
    # When all parties other than the current node receive the same values.
    (4, 1, [0, 4, 0, 0], (
        dumps([0, 4, 0, 0]),
        dumps([0, 4, 0, 0]),
        dumps([0, 4, 0, 0]),
        dumps([0, 4, 0, 0]),
    )),
    # When two parties other than the current node receive at least k values.
    (4, 1, [0, 4, 0, 0], (
        dumps([0, 4, 0, 0]),
        dumps([0, 10, 0, 0]),
        dumps([0, 0, 0, 0]),
        dumps([0, 0, 0, 0]),
    )),
    # When all parties other than the current node receive at least k values.
    (4, 1, [0, 4, 0, 0], (
        dumps([0, 4, 0, 0]),
        dumps([0, 10, 0, 0]),
        dumps([0, 4, 0, 0]),
        dumps([0, 4, 0, 0]),
    )),
    # When t+1 parties other than the current node receive at least k values.
    (4, 1, [0, 6, 0, 0], (
        dumps([0, 4, 0, 0]),
        dumps([0, 5, 0, 0]),
        dumps([0, 6, 0, 0]),
        dumps([0, 7, 0, 0]),
    )),
    (4, 1, [3, 5, 3, 5], (
        dumps([1, 5, 4, 2]),
        dumps([2, 5, 3, 3]),
        dumps([3, 2, 0, 5]),
        dumps([4, 3, 0, 9]),
    )),
    (4, 1, [0, 3, 2, 1], (
        dumps([0, 4, 0, 2]),
        dumps([0, 3, 0, 1]),
        dumps([0, 3, 2, 1]),
        dumps([4, 3, 8, 1]),
    )),
    (7, 2, [4, 3, 5, 0, 4, 6, 2], (
        dumps([0, 4, 1, 0, 2, 1, 0]),
        dumps([0, 3, 2, 0, 1, 1, 0]),
        dumps([0, 3, 3, 0, 3, 8, 1]),
        dumps([4, 3, 4, 0, 4, 6, 2]),
        dumps([0, 3, 5, 0, 6, 3, 3]),
        dumps([4, 3, 6, 8, 5, 9, 2]),
        dumps([4, 3, 7, 5, 4, 3, 4]),
    )),
))
@mark.asyncio
async def test_acs_output(n, t, output_counts, acs_outputs):
    my_id = 0

    input_q = asyncio.Queue()
    with AvssValueProcessor(None, None, n, t, my_id,
                            None, None, input_q.get) as proc:
        proc._process_acs_output(acs_outputs)
        assert [len(proc.outputs_per_dealer[i]) for i in range(n)] == output_counts
        for i in range(n):
            for output in proc.outputs_per_dealer[i]:
                assert type(output) is asyncio.Future

        # These are set by another method and shouldn't have been updated.
        assert all(len(proc.inputs_per_dealer[i]) == 0 for i in range(n))
        assert all(proc.next_idx_to_return_per_dealer[i] == 0 for i in range(n))


# [i][j] -> Represents the number of AVSSed values
# received by node `i` dealt by node `j`.
@mark.parametrize("k, acs_outputs", (
    # When two parties receive the same value.
    (1, (
        dumps([1, 0, 0, 0]),
        dumps([1, 0, 0, 0]),
        dumps([0, 0, 0, 0]),
        dumps([0, 0, 0, 0]),
    )),
    # When all parties receive the same value.
    (1, (
        dumps([1, 0, 0, 0]),
        dumps([1, 0, 0, 0]),
        dumps([1, 0, 0, 0]),
        dumps([1, 0, 0, 0]),
    )),
    (3, (
        dumps([3, 0, 0, 0]),
        dumps([4, 0, 0, 0]),
        dumps([0, 0, 0, 0]),
        dumps([1, 0, 0, 0]),
    )),
))
@mark.asyncio
async def test_with_agreed_values_on_same_node_with_input(k, acs_outputs):
    n, t, my_id = 4, 1, 0

    input_q = asyncio.Queue()
    with AvssValueProcessor(None, None, n, t, my_id,
                            None, None, input_q.get) as proc:
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
@mark.parametrize("k, acs_outputs", (
    # When two parties other than the current node receive the same value.
    (1, (
        dumps([0, 1, 0, 0]),
        dumps([0, 1, 0, 0]),
        dumps([0, 0, 0, 0]),
        dumps([0, 0, 0, 0]),
    )),
    # When all parties other than the current node receive the same value.
    (1, (
        dumps([0, 1, 0, 0]),
        dumps([0, 1, 0, 0]),
        dumps([0, 1, 0, 0]),
        dumps([0, 1, 0, 0]),
    )),
))
@mark.asyncio
async def test_with_agreed_values_on_another_node_with_input(k, acs_outputs):
    n, t, sender_id = 4, 1, 1

    input_q = asyncio.Queue()
    with AvssValueProcessor(None, None, n, t, 0,
                            None, None, input_q.get) as proc:
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
