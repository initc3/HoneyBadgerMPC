import random
from math import log
import os
import asyncio
from itertools import islice
from operator import __mul__, __floordiv__
from honeybadgermpc.mpc import (
    Field, Poly, generate_test_triples, write_polys, TaskProgramRunner
)
from honeybadgermpc.logger import BenchmarkLogger
from time import time


sharedatadir = "sharedata"
triplesprefix = f'{sharedatadir}/test_triples'
oneminusoneprefix = f'{sharedatadir}/test_one_minusone'
filecount = 0


async def wait_for_preprocessing():
    while not os.path.exists(f"{sharedatadir}/READY"):
        print(f"waiting for preprocessing {sharedatadir}/READY")
        await asyncio.sleep(1)


async def batchBeaver(ctx, Xs, Ys, As, Bs, ABs):
    Ds = await (Xs - As).open()  # noqa: W606
    Es = await (Ys - Bs).open()  # noqa: W606

    XYs = [(ctx.Share(D*E) + D*b + E*a + ab).v for (
        a, b, ab, D, E) in zip(As._shares, Bs._shares, ABs._shares, Ds, Es)]

    return XYs


async def batchSwitch(ctx, Xs, Ys, sbits, As, Bs, ABs, n):
    Ns = [1 / Field(2) for _ in range(n)]

    def toShareArray(arr):
        return ctx.ShareArray(list(map(ctx.Share, arr)))
    Xs, Ys, As, Bs, ABs, sbits = list(map(toShareArray, [Xs, Ys, As, Bs, ABs, sbits]))
    Ms = list(map(ctx.Share, await batchBeaver(ctx, sbits, (Xs - Ys), As, Bs, ABs)))

    t1s = [n * (x + y + m).v for x, y, m, n in zip(Xs._shares, Ys._shares, Ms, Ns)]
    t2s = [n * (x + y - m).v for x, y, m, n in zip(Xs._shares, Ys._shares, Ms, Ns)]
    return t1s, t2s


def writeToFile(shares, nodeid):
    global filecount
    with open(f"{sharedatadir}/butterfly_online_{filecount}_{nodeid}.share", "w") as f:
        for share in shares:
            print(share.value, file=f)
    filecount += 1


def getTriplesAndSbit(tripleshares, randshares):
    a, b, ab = next(tripleshares).v, next(tripleshares).v, next(tripleshares).v
    sbit = next(randshares).v
    return a, b, ab, sbit


def getNTriplesAndSbits(tripleshares, randshares, n):
    As, Bs, ABs = [], [], []
    for _ in range(n):
        a, b, ab = list(islice(tripleshares, 3))
        As.append(a.v), Bs.append(b.v), ABs.append(ab.v)
    sbits = list(map(lambda x: x.v, list(islice(randshares, n))))
    return As, Bs, ABs, sbits


async def permutationNetwork(ctx, inputs, k, delta, randshares, tripleshares):
    assert k == len(inputs)
    assert k & (k-1) == 0, "Size of input must be a power of 2"
    benchLogger = BenchmarkLogger.get(ctx.myid)
    iteration = 0
    for j in range(2):
        s, e, op = (1, k, __mul__) if j == 0 else (k//2, 1, __floordiv__)
        while s != e:
            stime = time()
            As, Bs, ABs, sbits = getNTriplesAndSbits(tripleshares, randshares, k//2)
            Xs, Ys = [], []
            first = True
            i = 0
            while i < k:
                for _ in range(s):
                    arr = Xs if first else Ys
                    arr.append(inputs[i])
                    i += 1
                first = not first
            assert len(Xs) == len(Ys)
            assert len(Xs) != 0
            result = await batchSwitch(ctx, Xs, Ys, sbits, As, Bs, ABs, k)
            inputs = [*sum(zip(result[0], result[1]), ())]
            s = op(s, 2)
            benchLogger.info(f"[ButterflyNetwork-{iteration}]: {time()-stime}")
            iteration += 1
    return inputs


async def butterflyNetwork(ctx, **kwargs):
    k, delta = kwargs['k'], kwargs['delta']
    inputs = list(map(lambda x: x.v, list(ctx._rands)[:k]))
    tripleshares = ctx.read_shares(open(f'{triplesprefix}-{ctx.myid}.share'))
    randshares = ctx.read_shares(open(f'{oneminusoneprefix}-{ctx.myid}.share'))
    print(f"[{ctx.myid}] Running permutation network.")
    shuffled = await permutationNetwork(
        ctx, inputs, k, delta, iter(randshares), iter(tripleshares)
    )
    if shuffled is not None:
        shuffledShares = list(map(ctx.Share, shuffled))
        openedValues = await asyncio.gather(*[s.open() for s in shuffledShares])
        print(f"[{ctx.myid}]", openedValues)
        return shuffledShares
    return None


def generate_random_shares(prefix, k, N, t):
    polys = [Poly.random(t, random.randint(0, 1)*2 - 1) for _ in range(k)]
    write_polys(prefix, Field.modulus, N, t, polys)


def runButterlyNetworkInTasks():
    from honeybadgermpc.mpc import generate_test_randoms, random_files_prefix

    N, t, k, delta = 3, 1, 128, 6

    os.makedirs("sharedata/", exist_ok=True)
    print('Generating random shares of triples in sharedata/')
    generate_test_triples(triplesprefix, 1000, N, t)
    print('Generating random shares of 1/-1 in sharedata/')
    generate_random_shares(oneminusoneprefix, k * int(log(k, 2)), N, t)
    print('Generating random inputs in sharedata/')
    generate_test_randoms(random_files_prefix, 1000, N, t)

    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    loop.set_debug(True)
    try:
        programRunner = TaskProgramRunner(N, t)
        programRunner.add(butterflyNetwork, k=k, delta=delta)
        loop.run_until_complete(programRunner.join())
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
                os.makedirs("sharedata/", exist_ok=True)
                print('Generating random shares of triples in sharedata/')
                generate_test_triples(triplesprefix, 1000, N, t)
                print('Generating random shares of 1/-1 in sharedata/')
                generate_random_shares(oneminusoneprefix, k * int(log(k, 2)), N, t)
                print('Generating random inputs in sharedata/')
                generate_test_randoms(random_files_prefix, 1000, N, t)
                os.mknod(f"{sharedatadir}/READY")
            else:
                loop.run_until_complete(wait_for_preprocessing())

        programRunner = ProcessProgramRunner(network_info, N, t, nodeid)
        loop.run_until_complete(programRunner.start())
        programRunner.add(0, butterflyNetwork, k=k, delta=delta)
        loop.run_until_complete(programRunner.join())
        loop.run_until_complete(programRunner.close())
    finally:
        loop.close()
    # runButterlyNetworkInTasks()
