import random
from math import log
import os
import asyncio
import logging
from itertools import islice
from honeybadgermpc.mpc import (
    Field, Poly, generate_test_triples, write_polys, TaskProgramRunner
)
from time import time


sharedatadir = "sharedata"
triplesprefix = f'{sharedatadir}/test_triples'
oneminusoneprefix = f'{sharedatadir}/test_one_minusone'
filecount = 0


async def wait_for_preprocessing():
    while not os.path.exists(f"{sharedatadir}/READY"):
        logging.info(f"waiting for preprocessing {sharedatadir}/READY")
        await asyncio.sleep(1)


async def batch_beaver(ctx, xs, ys, as_, bs_, abs_):
    ds = await (xs - as_).open()  # noqa: W606
    es = await (ys - bs_).open()  # noqa: W606

    xys = [(ctx.Share(d*e) + d*b + e*a + ab).v for (
        a, b, ab, d, e) in zip(as_._shares, bs_._shares, abs_._shares, ds, es)]

    return xys


async def batch_switch(ctx, xs, ys, sbits, as_, bs_, abs_, n):
    ns = [1 / Field(2) for _ in range(n)]

    def to_share_array(arr):
        return ctx.ShareArray(list(map(ctx.Share, arr)))
    xs, ys, as_, bs_, abs_, sbits = list(
        map(to_share_array, [xs, ys, as_, bs_, abs_, sbits]))
    ms = list(map(ctx.Share, await batch_beaver(ctx, sbits, (xs - ys), as_, bs_, abs_)))

    t1s = [n * (x + y + m).v for x, y, m, n in zip(xs._shares, ys._shares, ms, ns)]
    t2s = [n * (x + y - m).v for x, y, m, n in zip(xs._shares, ys._shares, ms, ns)]
    return t1s, t2s


def write_to_file(shares, nodeid):
    global filecount
    with open(f"{sharedatadir}/butterfly_online_{filecount}_{nodeid}.share", "w") as f:
        for share in shares:
            print(share.value, file=f)
    filecount += 1


def get_triples_and_sbit(tripleshares, randshares):
    a, b, ab = next(tripleshares).v, next(tripleshares).v, next(tripleshares).v
    sbit = next(randshares).v
    return a, b, ab, sbit


def get_n_triple_and_sbits(tripleshares, randshares, n):
    as_, bs_, abs_ = [], [], []
    for _ in range(n):
        a, b, ab = list(islice(tripleshares, 3))
        as_.append(a.v), bs_.append(b.v), abs_.append(ab.v)
    sbits = list(map(lambda x: x.v, list(islice(randshares, n))))
    return as_, bs_, abs_, sbits


async def iterated_butterfly_network(ctx, inputs, k, delta, randshares, tripleshares):
    # This runs O(log k) iterations of the butterfly permutation network,
    # each of which has log k elements. The total number of switches is
    # k (log k)^2
    assert k == len(inputs)
    assert k & (k-1) == 0, "Size of input must be a power of 2"
    benchLogger = logging.LoggerAdapter(
        logging.getLogger("benchmark_logger"), {"node_id": ctx.myid})
    iteration = 0
    num_iterations = int(log(k, 2))
    for cur_iter in range(num_iterations):
        stride = 1
        while stride < k:
            stime = time()
            As, Bs, ABs, sbits = get_n_triple_and_sbits(tripleshares, randshares, k//2)
            assert len(As) == len(Bs) == len(ABs) == len(sbits) == k//2
            Xs, Ys = [], []
            first = True
            i = 0
            while i < k:
                for _ in range(stride):
                    arr = Xs if first else Ys
                    arr.append(inputs[i])
                    i += 1
                first = not first
            assert len(Xs) == len(Ys)
            assert len(Xs) != 0
            result = await batch_switch(ctx, Xs, Ys, sbits, As, Bs, ABs, k)
            inputs = [*sum(zip(result[0], result[1]), ())]
            stride *= 2
            benchLogger.info(f"[ButterflyNetwork-{iteration}]: {time()-stime}")
            iteration += 1
    return inputs


async def butterfly_network_helper(ctx, **kwargs):
    k, delta = kwargs['k'], kwargs['delta']
    inputs = list(map(lambda x: x.v, list(ctx._rands)[:k]))
    tripleshares = ctx.read_shares(open(f'{triplesprefix}-{ctx.myid}.share'))
    randshares = ctx.read_shares(open(f'{oneminusoneprefix}-{ctx.myid}.share'))
    logging.info(f"[{ctx.myid}] Running permutation network.")
    shuffled = await iterated_butterfly_network(
        ctx, inputs, k, delta, iter(randshares), iter(tripleshares)
    )
    if shuffled is not None:
        shuffledShares = ctx.ShareArray(list(map(ctx.Share, shuffled)))
        openedValues = await shuffledShares.open()
        logging.info(f"[{ctx.myid}] {openedValues}")
        return shuffledShares
    return None


def generate_random_shares(prefix, k, n, t):
    polys = [Poly.random(t, random.randint(0, 1)*2 - 1) for _ in range(k)]
    write_polys(prefix, Field.modulus, n, t, polys)


def run_butterfly_network_in_tasks():
    from honeybadgermpc.mpc import generate_test_randoms, random_files_prefix

    n, t, k, delta = 3, 1, 128, 6

    num_switches = k * int(log(k, 2)) ** 2

    os.makedirs("sharedata/", exist_ok=True)
    logging.info('Generating random shares of triples in sharedata/')
    generate_test_triples(triplesprefix, 2*num_switches, n, t)
    logging.info('Generating random shares of 1/-1 in sharedata/')
    generate_random_shares(oneminusoneprefix, num_switches, n, t)
    logging.info('Generating random inputs in sharedata/')
    generate_test_randoms(random_files_prefix, k, n, t)

    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    loop.set_debug(True)
    try:
        pgm_runner = TaskProgramRunner(n, t)
        pgm_runner.add(butterfly_network_helper, k=k, delta=delta)
        loop.run_until_complete(pgm_runner.join())
    finally:
        loop.close()


if __name__ == "__main__":
    import sys
    from honeybadgermpc.config import load_config
    from honeybadgermpc.ipc import NodeDetails, ProcessProgramRunner
    from honeybadgermpc.exceptions import ConfigurationError
    from honeybadgermpc.mpc import generate_test_randoms, random_files_prefix

    configfile = os.environ.get('HBMPC_CONFIG')
    nodeid = os.environ.get('HBMPC_NODE_ID')
    runid = os.environ.get('HBMPC_RUN_ID')

    # override configfile if passed to command
    try:
        nodeid = sys.argv[1]
        configfile = sys.argv[2]
    except IndexError:
        pass

    if not nodeid:
        raise ConfigurationError('Environment variable `HBMPC_NODE_ID` must be set'
                                 ' or a node id must be given as first argument.')

    if not configfile:
        raise ConfigurationError('Environment variable `HBMPC_CONFIG` must be set'
                                 ' or a config file must be given as second argument.')

    config_dict = load_config(configfile)
    nodeid = int(nodeid)
    N = config_dict['N']
    t = config_dict['t']
    k = config_dict['k']
    delta = int(config_dict['delta'])

    network_info = {
        int(peerid): NodeDetails(addrinfo.split(':')[0], int(addrinfo.split(':')[1]))
        for peerid, addrinfo in config_dict['peers'].items()
    }

    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    loop.set_debug(True)
    try:
        if not config_dict['skipPreprocessing']:
            if nodeid == 0:
                NUM_SWITCHES = k * int(log(k, 2)) ** 2
                os.makedirs("sharedata/", exist_ok=True)
                logging.info('Generating random shares of triples in sharedata/')
                generate_test_triples(triplesprefix, 2 * NUM_SWITCHES, N, t)
                logging.info('Generating random shares of 1/-1 in sharedata/')
                generate_random_shares(oneminusoneprefix, NUM_SWITCHES, N, t)
                logging.info('Generating random inputs in sharedata/')
                generate_test_randoms(random_files_prefix, k, N, t)
                os.mknod(f"{sharedatadir}/READY")
            else:
                loop.run_until_complete(wait_for_preprocessing())

        programRunner = ProcessProgramRunner(network_info, N, t, nodeid)
        loop.run_until_complete(programRunner.start())
        programRunner.add(0, butterfly_network_helper, k=k, delta=delta)
        loop.run_until_complete(programRunner.join())
        loop.run_until_complete(programRunner.close())
    finally:
        loop.close()
    # runButterlyNetworkInTasks()
