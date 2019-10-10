from pytest import mark
from contextlib import ExitStack
from random import randint
from honeybadgermpc.poly_commit_const import gen_pc_const_crs, PolyCommitConst
from honeybadgermpc.poly_commit_lin import PolyCommitLin
from honeybadgermpc.betterpairing import G1, ZR
from honeybadgermpc.hbavss import HbAvssLight, HbAvssBatch
from honeybadgermpc.field import GF
from honeybadgermpc.elliptic_curve import Subgroup
import asyncio


def get_avss_params(n, t):
    g, h = G1.rand(), G1.rand()
    public_keys, private_keys = [None] * n, [None] * n
    for i in range(n):
        private_keys[i] = ZR.random()
        public_keys[i] = pow(g, private_keys[i])
    return g, h, public_keys, private_keys


@mark.parametrize(
    "t, k",
    [
        (1, 5),
        (3, 5),
        (5, 5),
        (16, 5),
        (33, 5),
        (85, 5),
        (1, 25),
        (3, 25),
        (5, 25),
        (16, 25),
        (33, 25),
        (85, 25),
        (1, 50),
        (3, 50),
        (5, 50),
        (16, 50),
        (33, 50),
        (85, 50),
        (1, 100),
        (3, 100),
        (5, 100),
        (16, 100),
        (33, 100),
        (85, 100),
    ],
)  # (# noqa: E501)
def test_benchmark_hbavss_lite_dealer(test_router, benchmark, t, k):
    loop = asyncio.get_event_loop()
    field = ZR
    n = 3 * t
    g, h, pks, sks = get_avss_params(n, t)
    crs = [g, h]
    pc = PolyCommitLin(crs, field=field)
    pc.preprocess(8)
    values = [field.random() for _ in range(k)]
    params = (t, n, g, h, pks, sks, crs, pc, values, field)

    def _prog():
        loop.run_until_complete(hbavss_light_batch_dealer(test_router, params))

    benchmark(_prog)


@mark.parametrize(
    "t, k",
    [
        (1, 5),
        (3, 5),
        (5, 5),
        (16, 5),
        (33, 5),
        (1, 25),
        (3, 25),
        (5, 25),
        (16, 25),
        (33, 25),
        (1, 50),
        (3, 50),
        (5, 50),
        (16, 50),
        (33, 50),
        (1, 100),
        (3, 100),
        (5, 100),
        (16, 100),
        (33, 100),
    ],
)
def test_benchmark_hbavss_dealer(test_router, benchmark, t, k):
    loop = asyncio.get_event_loop()
    n = 3 * t + 1
    field = GF(Subgroup.BLS12_381)
    g, h, pks, sks = get_avss_params(n + 1, t)
    crs = gen_pc_const_crs(t, g=g, h=h)
    pc = PolyCommitConst(crs, field=field)
    pc.preprocess_prover(8)
    pc.preprocess_verifier(8)
    values = [field.random() for _ in range(k)]
    params = (t, n, g, h, pks, sks, crs, pc, values, field)

    def _prog():
        loop.run_until_complete(hbavss_multibatch_dealer(test_router, params))

    benchmark(_prog)


@mark.parametrize(
    "t, k",
    [
        (1, 5),
        (3, 5),
        (5, 5),
        (16, 5),
        (33, 5),
        (85, 5),
        (1, 25),
        (3, 25),
        (5, 25),
        (16, 25),
        (33, 25),
        (85, 25),
        (1, 50),
        (3, 50),
        (5, 50),
        (16, 50),
        (33, 50),
        (85, 50),
        (1, 100),
        (3, 100),
        (5, 100),
        (16, 100),
        (33, 100),
        (85, 100),
    ],
)  # (# noqa: E501)
def test_benchmark_hbavss_lite(test_router, benchmark, t, k):
    loop = asyncio.get_event_loop()
    # field = GF(Subgroup.BLS12_381)
    field = ZR
    n = 3 * t + 1
    g, h, pks, sks = get_avss_params(n, t)
    crs = [g, h]
    pc = PolyCommitLin(crs, field=field)
    pc.preprocess(8)
    values = [field.random() for _ in range(k)]
    params = (t, n, g, h, pks, sks, crs, pc, values, field)

    def _prog():
        loop.run_until_complete(hbavss_light_batch(test_router, params))

    benchmark(_prog)


@mark.parametrize(
    "t, k",
    [
        (1, 5),
        (3, 5),
        (5, 5),
        (16, 5),
        (33, 5),
        (1, 25),
        (3, 25),
        (5, 25),
        (16, 25),
        (33, 25),
        (1, 50),
        (3, 50),
        (5, 50),
        (16, 50),
        (33, 50),
        (1, 100),
        (3, 100),
        (5, 100),
        (16, 100),
        (33, 100),
    ],
)
def test_benchmark_hbavss(test_router, benchmark, t, k):
    loop = asyncio.get_event_loop()
    n = 3 * t + 1
    field = GF(Subgroup.BLS12_381)
    g, h, pks, sks = get_avss_params(n, t)
    crs = gen_pc_const_crs(t, g=g, h=h)
    pc = PolyCommitConst(crs, field=field)
    pc.preprocess_prover(8)
    pc.preprocess_verifier(8)
    values = [field.random() for _ in range(k)]
    params = (t, n, g, h, pks, sks, crs, pc, values, field)

    def _prog():
        loop.run_until_complete(hbavss_multibatch(test_router, params))

    benchmark(_prog)


async def hbavss_light_batch(test_router, params):
    (t, n, g, h, pks, sks, crs, pc, values, field) = params
    sends, recvs, _ = test_router(n)
    avss_tasks = [None] * n
    hbavss_list = [None] * n
    dealer_id = randint(0, n - 1)

    with ExitStack() as stack:
        for i in range(n):
            hbavss = HbAvssLight(
                pks, sks[i], crs, n, t, i, sends[i], recvs[i], pc=pc, field=field
            )
            hbavss_list[i] = hbavss
            stack.enter_context(hbavss)
            if i == dealer_id:
                avss_tasks[i] = asyncio.create_task(hbavss.avss(0, value=values))
            else:
                avss_tasks[i] = asyncio.create_task(hbavss.avss(0, dealer_id=dealer_id))
        await asyncio.gather(*[hbavss_list[i].output_queue.get() for i in range(n)])
        for task in avss_tasks:
            task.cancel()


async def hbavss_light_batch_dealer(test_router, params):

    (t, n, g, h, pks, sks, crs, pc, values, field) = params
    sends, recvs, _ = test_router(n + 1)
    dealer_id = n

    hbavss = HbAvssLight(
        pks,
        None,
        crs,
        n,
        t,
        dealer_id,
        sends[dealer_id],
        recvs[dealer_id],
        pc=pc,
        field=field,
    )  # (# noqa: E501)
    await asyncio.create_task(hbavss.avss(0, value=values, client_mode=True))


async def hbavss_multibatch(test_router, params):

    (t, n, g, h, pks, sks, crs, pc, values, field) = params
    sends, recvs, _ = test_router(n)
    avss_tasks = [None] * n
    dealer_id = randint(0, n - 1)

    with ExitStack() as stack:
        hbavss_list = [None] * n
        for i in range(n):
            hbavss = HbAvssBatch(
                pks, sks[i], crs, n, t, i, sends[i], recvs[i], pc=pc, field=field
            )
            hbavss_list[i] = hbavss
            stack.enter_context(hbavss)
            if i == dealer_id:
                avss_tasks[i] = asyncio.create_task(hbavss.avss(0, values=values))
            else:
                avss_tasks[i] = asyncio.create_task(hbavss.avss(0, dealer_id=dealer_id))
        await asyncio.gather(*[hbavss_list[i].output_queue.get() for i in range(n)])
        for task in avss_tasks:
            task.cancel()


async def hbavss_multibatch_dealer(test_router, params):
    (t, n, g, h, pks, sks, crs, pc, values, field) = params
    sends, recvs, _ = test_router(n + 1)
    dealer_id = n
    hbavss = HbAvssBatch(
        pks,
        None,
        crs,
        n,
        t,
        dealer_id,
        sends[dealer_id],
        recvs[dealer_id],
        pc=pc,
        field=field,
    )  # (# noqa: E501)
    await hbavss.avss(0, values=values, client_mode=True)
