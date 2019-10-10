import random
from asyncio import Queue, Event
from asyncio import get_event_loop, create_task, gather
from pytest import mark, raises

from honeybadgermpc.broadcast.commoncoin import shared_coin
from honeybadgermpc.broadcast.binaryagreement import binaryagreement
from honeybadgermpc.broadcast.crypto.boldyreva import dealer
from collections import defaultdict


def byzantine_broadcast_router(n, maxdelay=0.005, seed=None, **byzargs):
    """Builds a set of connected channels, with random delay.

    :return: (receives, sends) endpoints.
    """
    rnd = random.Random(seed)
    queues = [Queue() for _ in range(n)]

    def make_broadcast(i):
        def _send(j, o):
            delay = rnd.random() * maxdelay
            if j == byzargs.get("byznode"):
                try:
                    byz_tag = byzargs["byz_message_type"]
                except KeyError:
                    pass
                else:
                    o = list(o)
                    o[0] = byz_tag
                    o = tuple(o)
            get_event_loop().call_later(delay, queues[j].put_nowait, (i, o))

            if j == byzargs.get("byznode") and o[0] == byzargs.get(
                "redundant_msg_type"
            ):
                get_event_loop().call_later(delay, queues[j].put_nowait, (i, o))

        def _bc(o):
            for j in range(n):
                _send(j, o)

        return _bc

    def make_recv(j):
        async def _recv():
            # print('RECV %2d' % (j))
            (i, o) = await queues[j].get()
            return (i, o)

        return _recv

    return ([make_broadcast(i) for i in range(n)], [make_recv(j) for j in range(n)])


def release_held_messages(q, receivers):
    for m in q:
        receivers[m["receiver"]].put((m["sender"], m["msg"]))


def dummy_coin(sid, n, f):
    counter = defaultdict(int)
    events = defaultdict(Event)

    async def get_coin(round):
        # Return a pseudorandom number depending on the round, without blocking
        counter[round] += 1
        if counter[round] == f + 1:
            events[round].set()
        await events[round].wait()
        return hash((sid, round)) % 2

    return get_coin


# Test binary agreement with a dummy coin
@mark.asyncio
async def test_binaryagreement_dummy(test_router):
    n, f, seed = 4, 1, None
    # Generate keys
    sid = "sidA"
    # Test everything when runs are OK
    # if seed is not None: print 'SEED:', seed
    _, recvs, sends = test_router(n, seed=seed)

    threads = []
    inputs = []
    outputs = []
    coin = dummy_coin(sid, n, f)  # One dummy coin function for all nodes

    for i in range(n):
        inputs.append(Queue())
        outputs.append(Queue())

        t = create_task(
            binaryagreement(
                sid,
                i,
                n,
                f,
                coin,
                inputs[i].get,
                outputs[i].put_nowait,
                sends[i],
                recvs[i],
            )
        )
        threads.append(t)

    for i in range(n):
        inputs[i].put_nowait(random.randint(0, 1))

    for i in range(n - f, n):
        inputs[i].put_nowait(0)
    outs = await gather(*[outputs[i].get() for i in range(n)])
    assert len(set(outs)) == 1
    await gather(*threads)


@mark.parametrize("msg_type", ("EST", "AUX", "CONF"))
@mark.parametrize("byznode", (1, 2, 3))
@mark.asyncio
async def test_binaryagreement_dummy_with_redundant_messages(byznode, msg_type):
    n = 4
    f = 1
    seed = None
    sid = "sidA"
    sends, recvs = byzantine_broadcast_router(
        n, seed=seed, byznode=byznode, redundant_msg_type=msg_type
    )
    threads = []
    inputs = []
    outputs = []
    coin = dummy_coin(sid, n, f)  # One dummy coin function for all nodes

    for i in range(n):
        inputs.append(Queue())
        outputs.append(Queue())
        t = create_task(
            binaryagreement(
                sid,
                i,
                n,
                f,
                coin,
                inputs[i].get,
                outputs[i].put_nowait,
                sends[i],
                recvs[i],
            )
        )
        threads.append(t)

    for i in range(n):
        inputs[i].put_nowait(random.randint(0, 1))

    outs = await gather(*[outputs[i].get() for i in range(n) if i != byznode])
    assert all(v in (0, 1) and v == outs[0] for v in outs)
    await gather(*[threads[i] for i in range(len(threads)) if i != byznode])
    threads[byznode].cancel()


@mark.parametrize("byznode", (1,))
@mark.asyncio
async def test_binaryagreement_dummy_with_byz_message_type(byznode):
    n = 4
    f = 1
    seed = None
    sid = "sidA"
    sends, recvs = byzantine_broadcast_router(
        n, seed=seed, byznode=byznode, byz_message_type="BUG"
    )
    threads = []
    inputs = []
    outputs = []
    coin = dummy_coin(sid, n, f)  # One dummy coin function for all nodes

    for i in range(n):
        inputs.append(Queue())
        outputs.append(Queue())
        t = create_task(
            binaryagreement(
                sid,
                i,
                n,
                f,
                coin,
                inputs[i].get,
                outputs[i].put_nowait,
                sends[i],
                recvs[i],
            )
        )
        threads.append(t)

    for i in range(n):
        inputs[i].put_nowait(random.randint(0, 1))

    outs = await gather(*[outputs[i].get() for i in range(n) if i != byznode])
    assert all(v in (0, 1) and v == outs[0] for v in outs)
    await gather(*[threads[i] for i in range(len(threads)) if i != byznode])
    threads[byznode].cancel()


# Test binary agreement with boldyreva coin
async def _make_coins(test_router, sid, n, f, seed):
    # Generate keys
    pk, sks = dealer(n, f + 1)
    _, recvs, sends = test_router(n, seed=seed)
    result = await gather(
        *[shared_coin(sid, i, n, f, pk, sks[i], sends[i], recvs[i]) for i in range(n)]
    )
    return zip(*result)


@mark.parametrize("seed", (1, 2, 3, 4, 5))
@mark.asyncio
async def test_binaryagreement(seed, test_router):
    n, f = 4, 1
    # Generate keys
    sid = "sidA"
    # Test everything when runs are OK
    # if seed is not None: print 'SEED:', seed
    rnd = random.Random(seed)

    # Instantiate the common coin
    coins_seed = rnd.random()
    coins, recv_tasks = await _make_coins(test_router, sid + "COIN", n, f, coins_seed)

    # Router
    _, recvs, sends = test_router(n, seed=seed)

    threads = []
    inputs = []
    outputs = []

    for i in range(n):
        inputs.append(Queue())
        outputs.append(Queue())

        t = create_task(
            binaryagreement(
                sid,
                i,
                n,
                f,
                coins[i],
                inputs[i].get,
                outputs[i].put_nowait,
                sends[i],
                recvs[i],
            )
        )
        threads.append(t)

    for i in range(n):
        inputs[i].put_nowait(random.randint(0, 1))

    outs = await gather(*[outputs[i].get() for i in range(n)])
    assert len(set(outs)) == 1
    await gather(*threads)
    [task.cancel() for task in recv_tasks]


@mark.parametrize(
    "values,s,already_decided,expected_est," "expected_already_decided,expected_output",
    (({0}, 0, None, 0, 0, 0), ({1}, 1, None, 1, 1, 1)),
)
@mark.asyncio
async def test_set_next_round_estimate_with_decision(
    values, s, already_decided, expected_est, expected_already_decided, expected_output
):
    from honeybadgermpc.broadcast.binaryagreement import set_new_estimate

    decide = Queue()
    updated_est, updated_already_decided = set_new_estimate(
        values=values, s=s, already_decided=already_decided, decide=decide.put_nowait
    )
    assert updated_est == expected_est
    assert updated_already_decided == expected_already_decided
    assert await decide.get() == expected_output


@mark.parametrize(
    "values,s,already_decided," "expected_est,expected_already_decided",
    (
        ({0}, 0, 1, 0, 1),
        ({0}, 1, None, 0, None),
        ({0}, 1, 0, 0, 0),
        ({0}, 1, 1, 0, 1),
        ({1}, 0, None, 1, None),
        ({1}, 0, 0, 1, 0),
        ({1}, 0, 1, 1, 1),
        ({1}, 1, 0, 1, 0),
        ({0, 1}, 0, None, 0, None),
        ({0, 1}, 0, 0, 0, 0),
        ({0, 1}, 0, 1, 0, 1),
        ({0, 1}, 1, None, 1, None),
        ({0, 1}, 1, 0, 1, 0),
        ({0, 1}, 1, 1, 1, 1),
    ),
)
def test_set_next_round_estimate(
    values, s, already_decided, expected_est, expected_already_decided
):
    from honeybadgermpc.broadcast.binaryagreement import set_new_estimate

    decide = Queue()
    updated_est, updated_already_decided = set_new_estimate(
        values=values, s=s, already_decided=already_decided, decide=decide.put_nowait
    )
    assert updated_est == expected_est
    assert updated_already_decided == expected_already_decided
    assert decide.empty()


@mark.parametrize("values,s,already_decided", (({0}, 0, 0), ({1}, 1, 1)))
def test_set_next_round_estimate_raises(values, s, already_decided):
    from honeybadgermpc.broadcast.binaryagreement import set_new_estimate
    from honeybadgermpc.exceptions import AbandonedNodeError

    with raises(AbandonedNodeError):
        updated_est, updated_already_decided = set_new_estimate(
            values=values, s=s, already_decided=already_decided, decide=None
        )
