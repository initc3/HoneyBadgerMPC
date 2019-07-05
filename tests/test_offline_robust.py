import asyncio
from pytest import mark
from contextlib import ExitStack
from random import randint
from honeybadgermpc.offline_robust import RandomGenerator, TripleGenerator
from honeybadgermpc.mpc import TaskProgramRunner


@mark.asyncio
async def test_get_random(test_router, rust_field):
    n, t = 4, 1
    sends, recvs, _ = test_router(n)

    with ExitStack() as stack:
        random_generators = [None] * n
        tasks = [None] * n
        for i in range(n):
            random_generators[i] = RandomGenerator(n, t, i, sends[i], recvs[i], 1)
            stack.enter_context(random_generators[i])
            tasks[i] = asyncio.create_task(random_generators[i].get())

        shares = await asyncio.gather(*tasks)
        assert len(shares) == n

    async def _prog(context):
        opened_share = await context.Share(shares[context.myid]).open()
        return opened_share

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    rands = await program_runner.join()

    assert len(rands) == n
    # Verify that all nodes have the same values
    assert rands.count(rands[0]) == n


@mark.parametrize(
    "n, t, b",
    ((4, 1, 10),)
    # These work too, take a little too long, that's why commenting
    # "n, t, b", ((4, 1, 10), (4, 1, 50), (7, 2, 10))
)
@mark.asyncio
async def test_get_randoms(test_router, rust_field, n, t, b):
    sends, recvs, _ = test_router(n)

    with ExitStack() as stack:
        random_generators = [None] * n
        tasks = [None] * n * b
        for i in range(n):
            # k => each node has a different batch size
            # for the number of values which it AVSSes
            k = randint(1, 10)
            random_generators[i] = RandomGenerator(n, t, i, sends[i], recvs[i], k)
            stack.enter_context(random_generators[i])
            for j in range(b):
                tasks[b * i + j] = asyncio.create_task(random_generators[i].get())

        shares = await asyncio.gather(*tasks)
        assert len(shares) == n * b

    async def _prog(context):
        s = context.myid * b
        opened_share = await context.ShareArray(shares[s : s + b]).open()
        return tuple(opened_share)

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    rands = await program_runner.join()

    assert len(rands) == n
    # Verify that all nodes have the same values
    assert rands.count(rands[0]) == n


@mark.asyncio
async def test_get_triple(test_router, rust_field):
    n, t = 4, 1
    sends, recvs, _ = test_router(n)

    with ExitStack() as stack:
        triple_generators = [None] * n
        tasks = [None] * n
        for i in range(n):
            triple_generators[i] = TripleGenerator(n, t, i, sends[i], recvs[i], 1)
            stack.enter_context(triple_generators[i])
            tasks[i] = asyncio.create_task(triple_generators[i].get())

        shares = await asyncio.gather(*tasks)
        assert len(shares) == n

    async def _prog(context):
        a, b, ab = await context.ShareArray(list(shares[context.myid])).open()
        assert a * b == ab
        return tuple((a, b, ab))

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    triples = await program_runner.join()

    assert len(triples) == n
    # Verify that all nodes have the same values
    assert triples.count(triples[0]) == n


@mark.parametrize(
    "n, t, b",
    ((4, 1, 10),)
    # These work too, take a little too long, that's why commenting
    # "n, t, b", ((4, 1, 10), (4, 1, 50), (7, 2, 10))
)
@mark.asyncio
async def test_get_triples(test_router, rust_field, n, t, b):
    sends, recvs, _ = test_router(n)

    with ExitStack() as stack:
        triple_generators = [None] * n
        tasks = [None] * n * b
        for i in range(n):
            # k => each node has a different batch size
            # for the number of values which it AVSSes
            k = randint(50, 100)
            triple_generators[i] = TripleGenerator(n, t, i, sends[i], recvs[i], k)
            stack.enter_context(triple_generators[i])
            for j in range(b):
                tasks[b * i + j] = asyncio.create_task(triple_generators[i].get())

        shares = await asyncio.gather(*tasks)
        assert len(shares) == n * b

    async def _prog(context):
        s = context.myid * b
        triple_shares = sum(map(list, shares[s : s + b]), [])
        assert len(triple_shares) == b * 3
        opened_shares = await context.ShareArray(triple_shares).open()
        return tuple(opened_shares)

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    triples = await program_runner.join()

    assert len(triples) == n
    # Verify that all nodes have the same values
    assert triples.count(triples[0]) == n
    for i in range(0, len(triples[0]), 3):
        p, q, pq = triples[0][i : i + 3]
        assert p * q == p * q
