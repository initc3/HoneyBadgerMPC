"""
hbMPC tutorial 2.

Instructions:
   run this with
```
scripts/launch-tmuxlocal.sh apps/tutorial/hbmpc-tutorial-2.py conf/mpc/local
```
"""
import asyncio
import logging
from honeybadgermpc.preprocessing import (
    PreProcessedElements as FakePreProcessedElements,
)
from honeybadgermpc.progs.mixins.share_arithmetic import (
    MixinConstants,
    BeaverMultiply,
    BeaverMultiplyArrays,
)

mpc_config = {
    MixinConstants.MultiplyShareArray: BeaverMultiplyArrays(),
    MixinConstants.MultiplyShare: BeaverMultiply(),
}


async def dot_product(ctx, xs, ys):
    return sum((x * y for x, y in zip(xs, ys)), ctx.Share(0))


async def prog(ctx, k=50):
    # Computing a dot product by MPC (k openings)
    xs = [ctx.preproc.get_bit(ctx) for _ in range(k)]
    ys = [ctx.preproc.get_bit(ctx) for _ in range(k)]
    logging.info(f"[{ctx.myid}] Running prog 1.")
    res = await dot_product(ctx, xs, ys)

    R = await res.open()
    XS = await ctx.ShareArray(xs).open()
    YS = await ctx.ShareArray(ys).open()
    assert R == sum([X * Y for X, Y in zip(XS, YS)])
    logging.info(f"[{ctx.myid}] done")


async def _run(peers, n, t, my_id):
    from honeybadgermpc.ipc import ProcessProgramRunner

    async with ProcessProgramRunner(peers, n, t, my_id, mpc_config) as runner:
        await runner.execute("0", prog)
        bytes_sent = runner.node_communicator.bytes_sent
        print(f"[{my_id}] Total bytes sent out: {bytes_sent}")


if __name__ == "__main__":
    from honeybadgermpc.config import HbmpcConfig
    import sys

    if not HbmpcConfig.peers:
        print(
            f"WARNING: the $CONFIG_PATH environment variable wasn't set. "
            f"Please run this file with `scripts/launch-tmuxlocal.sh "
            f"apps/tutorial/hbmpc-tutorial-2.py conf/mpc/local`"
        )
        sys.exit(1)

    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    loop.set_debug(True)
    try:
        if HbmpcConfig.my_id == 0:
            k = 100  # How many of each kind of preproc
            pp_elements = FakePreProcessedElements()
            pp_elements.generate_bits(k, HbmpcConfig.N, HbmpcConfig.t)
            pp_elements.generate_triples(k, HbmpcConfig.N, HbmpcConfig.t)
            pp_elements.preprocessing_done()
        else:
            loop.run_until_complete(pp_elements.wait_for_preprocessing())

        loop.run_until_complete(
            _run(HbmpcConfig.peers, HbmpcConfig.N, HbmpcConfig.t, HbmpcConfig.my_id)
        )
    finally:
        loop.close()
