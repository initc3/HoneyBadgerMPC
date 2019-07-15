import asyncio
import logging
from math import log
from honeybadgermpc.preprocessing import PreProcessedElements
from time import time


async def batch_switch(ctx, xs, ys, n):
    sbits = [ctx.preproc.get_one_minus_ones(ctx).v for _ in range(n // 2)]
    ns = [1 / ctx.field(2) for _ in range(n // 2)]

    assert len(xs) == len(ys) == len(sbits) == n // 2
    xs, ys, sbits = list(map(ctx.ShareArray, [xs, ys, sbits]))
    ms = (await (sbits * (xs - ys)))._shares

    t1s = [n * (x + y + m).v for x, y, m, n in zip(xs._shares, ys._shares, ms, ns)]
    t2s = [n * (x + y - m).v for x, y, m, n in zip(xs._shares, ys._shares, ms, ns)]
    return t1s, t2s


async def iterated_butterfly_network(ctx, inputs, k):
    # This runs O(log k) iterations of the butterfly permutation network,
    # each of which has log k elements. The total number of switches is
    # k (log k)^2
    assert k == len(inputs)
    assert k & (k - 1) == 0, "Size of input must be a power of 2"
    bench_logger = logging.LoggerAdapter(
        logging.getLogger("benchmark_logger"), {"node_id": ctx.myid}
    )
    iteration = 0
    num_iterations = int(log(k, 2))
    for _ in range(num_iterations):
        stride = 1
        while stride < k:
            stime = time()
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
            result = await batch_switch(ctx, xs_, ys_, k)
            inputs = [*sum(zip(result[0], result[1]), ())]
            stride *= 2
            bench_logger.info(f"[ButterflyNetwork-{iteration}]: {time()-stime}")
            iteration += 1
    return inputs


async def butterfly_network_helper(ctx, **kwargs):
    k = kwargs["k"]

    inputs = kwargs["inputs"]
    if inputs is None:
        inputs = [ctx.preproc.get_rand(ctx).v for _ in range(k)]

    logging.info(f"[{ctx.myid}] Running permutation network.")
    shuffled = await iterated_butterfly_network(ctx, inputs, k)
    if shuffled is not None:
        shuffled_shares = ctx.ShareArray(list(map(ctx.Share, shuffled)))
        opened_values = await shuffled_shares.open()
        logging.debug(f"[{ctx.myid}] {opened_values}")
        return shuffled_shares
    return None


async def _run(peers, n, t, my_id):
    from honeybadgermpc.ipc import ProcessProgramRunner
    from honeybadgermpc.progs.mixins.share_arithmetic import (
        MixinConstants,
        BeaverMultiplyArrays,
    )

    mpc_config = {MixinConstants.MultiplyShareArray: BeaverMultiplyArrays()}
    async with ProcessProgramRunner(peers, n, t, my_id, mpc_config) as runner:
        runner.execute("0", butterfly_network_helper, k=k)


if __name__ == "__main__":
    from honeybadgermpc.config import HbmpcConfig

    k = int(HbmpcConfig.extras["k"])

    pp_elements = PreProcessedElements()
    pp_elements.clear_preprocessing()

    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    loop.set_debug(True)
    try:
        if not HbmpcConfig.skip_preprocessing:
            if HbmpcConfig.my_id == 0:
                NUM_SWITCHES = k * int(log(k, 2)) ** 2
                pp_elements.generate_one_minus_ones(
                    NUM_SWITCHES, HbmpcConfig.N, HbmpcConfig.t
                )
                pp_elements.generate_triples(
                    2 * NUM_SWITCHES, HbmpcConfig.N, HbmpcConfig.t
                )
                pp_elements.generate_rands(k, HbmpcConfig.N, HbmpcConfig.t)
                pp_elements.preprocessing_done()
            else:
                loop.run_until_complete(pp_elements.wait_for_preprocessing())

        loop.run_until_complete(
            _run(HbmpcConfig.peers, HbmpcConfig.N, HbmpcConfig.t, HbmpcConfig.my_id)
        )
    finally:
        loop.close()
        pp_elements.clear_preprocessing()
