import os
import asyncio
import logging
from math import log
from honeybadgermpc.mpc import TaskProgramRunner
from honeybadgermpc.preprocessing import PreProcessedElements, PreProcessingConstants
from honeybadgermpc.preprocessing import wait_for_preprocessing, preprocessing_done
from time import time


filecount = 0


async def batch_beaver(ctx, xs, ys, as_, bs_, abs_):
    ds = await (xs - as_).open()  # noqa: W606
    es = await (ys - bs_).open()  # noqa: W606

    xys = [(ctx.Share(d*e) + d*b + e*a + ab).v for (
        a, b, ab, d, e) in zip(as_._shares, bs_._shares, abs_._shares, ds, es)]

    return xys


async def batch_switch(ctx, xs, ys, sbits, as_, bs_, abs_, n):
    ns = [1 / ctx.field(2) for _ in range(n)]

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
    file_name = f"butterfly_online_{filecount}_{nodeid}.share"
    file_path = f"{PreProcessingConstants.SHARED_DATA_DIR}{file_name}"
    with open(file_path, "w") as f:
        for share in shares:
            print(share.value, file=f)
    filecount += 1


def get_n_triple_and_sbits(ctx, n):
    as_, bs_, abs_, sbits = [], [], [], []
    pp_elements = PreProcessedElements()
    for _ in range(n):
        a, b, ab = pp_elements.get_triple(ctx)
        as_.append(a.v), bs_.append(b.v), abs_.append(ab.v)
        sbits.append(pp_elements.get_one_minus_one_rand(ctx).v)
    return as_, bs_, abs_, sbits


async def iterated_butterfly_network(ctx, inputs, k, delta):
    # This runs O(log k) iterations of the butterfly permutation network,
    # each of which has log k elements. The total number of switches is
    # k (log k)^2
    assert k == len(inputs)
    assert k & (k-1) == 0, "Size of input must be a power of 2"
    bench_logger = logging.LoggerAdapter(
        logging.getLogger("benchmark_logger"), {"node_id": ctx.myid})
    iteration = 0
    num_iterations = int(log(k, 2))
    for _ in range(num_iterations):
        stride = 1
        while stride < k:
            stime = time()
            as_, bs_, abs_, sbits = get_n_triple_and_sbits(ctx, k//2)
            assert len(as_) == len(bs_) == len(abs_) == len(sbits) == k//2
            xs_, ys_ = [], []
            first = True
            i = 0
            while i < k:
                for _ in range(stride):
                    arr = xs_ if first else ys_
                    arr.append(inputs[i])
                    i += 1
                first = not first
            assert len(xs_) == len(ys_)
            assert len(xs_) != 0
            result = await batch_switch(ctx, xs_, ys_, sbits, as_, bs_, abs_, k)
            inputs = [*sum(zip(result[0], result[1]), ())]
            stride *= 2
            bench_logger.info(f"[ButterflyNetwork-{iteration}]: {time()-stime}")
            iteration += 1
    return inputs


async def butterfly_network_helper(ctx, **kwargs):
    k, delta = kwargs['k'], kwargs['delta']
    pp_elements = PreProcessedElements()
    inputs = [pp_elements.get_rand(ctx).v for _ in range(k)]
    logging.info(f"[{ctx.myid}] Running permutation network.")
    shuffled = await iterated_butterfly_network(ctx, inputs, k, delta)
    if shuffled is not None:
        shuffled_shares = ctx.ShareArray(list(map(ctx.Share, shuffled)))
        opened_values = await shuffled_shares.open()
        logging.info(f"[{ctx.myid}] {opened_values}")
        return shuffled_shares
    return None


def run_butterfly_network_in_tasks():
    n, t, k, delta = 3, 1, 128, 6

    num_switches = k * int(log(k, 2)) ** 2

    pp_elements = PreProcessedElements()
    pp_elements.generate_one_minus_one_rands(num_switches, n, t)
    pp_elements.generate_triples(2 * num_switches, n, t)
    pp_elements.generate_rands(k, n, t)

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
                pp_elements = PreProcessedElements()
                pp_elements.generate_one_minus_one_rands(NUM_SWITCHES, N, t)
                pp_elements.generate_triples(2 * NUM_SWITCHES, N, t)
                pp_elements.generate_rands(k, N, t)
                preprocessing_done()
            else:
                loop.run_until_complete(wait_for_preprocessing())

        program_runner = ProcessProgramRunner(network_info, N, t, nodeid)
        loop.run_until_complete(program_runner.start())
        program_runner.add(0, butterfly_network_helper, k=k, delta=delta)
        loop.run_until_complete(program_runner.join())
        loop.run_until_complete(program_runner.close())
    finally:
        loop.close()
    # runButterlyNetworkInTasks()
