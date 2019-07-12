import random
import asyncio
from pytest import mark
from honeybadgermpc.broadcast.commoncoin import shared_coin
from honeybadgermpc.broadcast.crypto.boldyreva import dealer


def byzantine_router(n, maxdelay=0.01, seed=None, **byzargs):
    """Builds a set of connected channels, with random delay.

    :return: (receives, sends) endpoints.
    """
    rnd = random.Random(seed)

    queues = [asyncio.Queue() for _ in range(n)]

    def make_broadcast(i):
        def _send(j, o):
            delay = rnd.random() * maxdelay
            asyncio.get_event_loop().call_later(delay, queues[j].put_nowait, (i, o))

        def _bc(o):
            for j in range(n):
                _send(j, o)

        return _bc

    def make_recv(j):
        async def _recv():
            return await queues[j].get()

        async def _recv_redundant():
            i, o = await queues[j].get()
            if i == 3 and o[1] == 3:
                o = list(o)
                o[1] -= 1
                o = tuple(o)
            return (i, o)

        async def _recv_fail_pk_verify_share():
            (i, o) = await queues[j].get()
            if i == 3 and o[1] == 3:
                o = list(o)
                o[1] += 1
                o = tuple(o)
            return (i, o)

        if j == byzargs.get("node") and byzargs.get("sig_redundant"):
            return _recv_redundant
        if j == byzargs.get("node") and byzargs.get("sig_err"):
            return _recv_fail_pk_verify_share
        return _recv

    return ([make_broadcast(i) for i in range(n)], [make_recv(j) for j in range(n)])


@mark.asyncio
async def test_commoncoin(test_router):
    n, f, seed = 4, 1, None
    # Generate keys
    pk, sks = dealer(n, f + 1)
    sid = "sidA"
    # Test everything when runs are OK
    _, recvs, sends = test_router(n, seed=seed)
    result = await asyncio.gather(
        *[shared_coin(sid, i, n, f, pk, sks[i], sends[i], recvs[i]) for i in range(n)]
    )
    coins, recv_tasks = zip(*result)

    for i in range(10):
        assert len(set(await asyncio.gather(*[c(i) for c in coins]))) == 1
    for task in recv_tasks:
        task.cancel()


@mark.asyncio
async def test_when_signature_share_verify_fails():
    n, f, seed = 4, 1, None
    pk, sks = dealer(n, f + 1)
    sid = "sidA"
    sends, recvs = byzantine_router(n, seed=seed, node=2, sig_err=True)
    result = await asyncio.gather(
        *[shared_coin(sid, i, n, f, pk, sks[i], sends[i], recvs[i]) for i in range(n)]
    )
    coins, recv_tasks = zip(*result)

    for i in range(10):
        assert len(set(await asyncio.gather(*[c(i) for c in coins]))) == 1
    for task in recv_tasks:
        task.cancel()


@mark.asyncio
async def test_when_redundant_signature_share_is_received():
    n, f, seed = 4, 1, None
    pk, sks = dealer(n, f + 1)
    sid = "sidA"
    sends, recvs = byzantine_router(n, seed=seed, node=2, sig_redundant=True)
    result = await asyncio.gather(
        *[shared_coin(sid, i, n, f, pk, sks[i], sends[i], recvs[i]) for i in range(n)]
    )
    coins, recv_tasks = zip(*result)

    for i in range(10):
        assert len(set(await asyncio.gather(*[c(i) for c in coins]))) == 1
    for task in recv_tasks:
        task.cancel()
