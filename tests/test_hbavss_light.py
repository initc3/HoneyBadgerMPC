from pytest import mark
from random import randint
from contextlib import ExitStack
from honeybadgermpc.polynomial import polynomials_over
from honeybadgermpc.betterpairing import G1, ZR
from honeybadgermpc.hbavss_light import HbAvssLight
from honeybadgermpc.mpc import TaskProgramRunner
import asyncio


def get_avss_params(n, t):
    g, h = G1.rand(), G1.rand()
    public_keys, private_keys = [None]*n, [None]*n
    for i in range(n):
        private_keys[i] = ZR.random()
        public_keys[i] = pow(g, private_keys[i])
    return g, h, public_keys, private_keys


@mark.asyncio
async def test_hbavss(test_router):
    t = 2
    n = 3*t + 1

    g, h, pks, sks = get_avss_params(n, t)
    sends, recvs, _ = test_router(n)

    value = ZR.random()
    avss_tasks = [None]*n
    dealer_id = randint(0, n-1)

    with ExitStack() as stack:
        for i in range(n):
            hbavss = HbAvssLight(pks, sks[i], g, h, n, t, i, sends[i], recvs[i])
            stack.enter_context(hbavss)
            if i == dealer_id:
                avss_tasks[i] = asyncio.create_task(hbavss.avss(value=value))
            else:
                avss_tasks[i] = asyncio.create_task(hbavss.avss(dealer_id=dealer_id))
        shares = await asyncio.gather(*avss_tasks)

    assert polynomials_over(ZR).interpolate_at(zip(range(1, n+1), shares)) == value


@mark.asyncio
async def test_hbavss_client_mode(test_router):
    t = 2
    n = 3*t + 1

    g, h, pks, sks = get_avss_params(n, t)
    sends, recvs, _ = test_router(n+1)

    value = ZR.random()
    avss_tasks = [None]*(n+1)
    dealer_id = n

    with ExitStack() as stack:
        client_hbavss = HbAvssLight(
            pks, None, g, h, n, t, dealer_id, sends[dealer_id], recvs[dealer_id])
        stack.enter_context(client_hbavss)
        avss_tasks[n] = asyncio.create_task(
            client_hbavss.avss(value=value, client_mode=True))
        for i in range(n):
            hbavss = HbAvssLight(pks, sks[i], g, h, n, t, i, sends[i], recvs[i])
            stack.enter_context(hbavss)
            avss_tasks[i] = asyncio.create_task(
                hbavss.avss(dealer_id=dealer_id, client_mode=True))

        # Ignore the result from the dealer
        shares = (await asyncio.gather(*avss_tasks))[:-1]

    assert polynomials_over(ZR).interpolate_at(zip(range(1, n+1), shares)) == value


@mark.asyncio
async def test_hbavss_share_open(test_router):
    t = 2
    n = 3*t + 1

    g, h, pks, sks = get_avss_params(n, t)
    sends, recvs, _ = test_router(n)
    value = int(ZR.random())
    dealer_id = randint(0, n-1)

    with ExitStack() as stack:
        avss_tasks = [None]*n
        for i in range(n):
            hbavss = HbAvssLight(pks, sks[i], g, h, n, t, i, sends[i], recvs[i])
            stack.enter_context(hbavss)
            if i == dealer_id:
                avss_tasks[i] = asyncio.create_task(hbavss.avss(value=value))
            else:
                avss_tasks[i] = asyncio.create_task(hbavss.avss(dealer_id=dealer_id))
        shares = await asyncio.gather(*avss_tasks)

    async def _prog(context):
        share_value = context.field(int(shares[context.myid]))
        assert await context.Share(share_value).open() == value

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    await program_runner.join()


@mark.asyncio
async def test_hbavss_parallel_share_array_open(test_router):
    t = 2
    n = 3*t + 1
    k = 4

    g, h, pks, sks = get_avss_params(n, t)
    sends, recvs, _ = test_router(n)
    values = [int(ZR.random()) for _ in range(k)]
    dealer_id = randint(0, n-1)

    with ExitStack() as stack:
        avss_tasks = [None]*n
        for i in range(n):
            hbavss = HbAvssLight(pks, sks[i], g, h, n, t, i, sends[i], recvs[i])
            stack.enter_context(hbavss)
            if i == dealer_id:
                v, d = values, None
            else:
                v, d = None, dealer_id
            avss_tasks[i] = asyncio.create_task(hbavss.avss_parallel(k, v, d))
        shares = await asyncio.gather(*avss_tasks)

    async def _prog(context):
        share_ints = list(map(int, shares[context.myid]))
        share_values = list(map(context.field, share_ints))
        opened_shares = set(await context.ShareArray(share_values).open())
        # The set of opened share should have exactly `k` values
        assert len(opened_shares) == k
        # All the values in the set of opened shares should be from the initial values
        for i in opened_shares:
            assert i.value in values

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    await program_runner.join()
