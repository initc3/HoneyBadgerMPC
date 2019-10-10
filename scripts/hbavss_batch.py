from honeybadgermpc.config import HbmpcConfig
from honeybadgermpc.ipc import ProcessProgramRunner
from honeybadgermpc.poly_commit_const import gen_pc_const_crs
from .hbavss import get_avss_params, HbAvssBatch
from honeybadgermpc.betterpairing import ZR
import asyncio
import time
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)
# Uncomment this when you want logs from this file.
logger.setLevel(logging.NOTSET)


async def _run(peers, n, t, my_id, batch_size):
    g, h, pks, sks = get_avss_params(n + 1, t)
    async with ProcessProgramRunner(peers, n + 1, t, my_id) as runner:
        send, recv = runner.get_send_recv("HBAVSS_BATCH")
        crs = gen_pc_const_crs(t, g=g, h=h)
        values = None
        dealer_id = n
        if my_id == dealer_id:
            # Dealer
            values = [ZR.random(0)] * batch_size
            logger.info("Starting DEALER")
            logger.info(f"Dealer timestamp: {time.time()}")
        else:
            logger.info("Starting RECIPIENT: %d", my_id)

        with HbAvssBatch(pks, sks[my_id], crs, n, t, my_id, send, recv) as hbavss:
            begin_time = time.time()
            if my_id != dealer_id:
                hbavss_task = asyncio.create_task(
                    hbavss.avss(0, dealer_id=dealer_id, values=values, client_mode=True)
                )
                await hbavss.output_queue.get()
                end_time = time.time()
                logger.info(f"Recipient time: {(end_time - begin_time)}")
                hbavss_task.cancel()
            else:
                await hbavss.avss(
                    0, dealer_id=dealer_id, values=values, client_mode=True
                )
                end_time = time.time()
                logger.info(f"Dealer time: {(end_time - begin_time)}")


if __name__ == "__main__":
    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()

    try:
        loop.run_until_complete(
            _run(
                HbmpcConfig.peers,
                HbmpcConfig.N,
                HbmpcConfig.t,
                HbmpcConfig.my_id,
                HbmpcConfig.extras["k"],
            )
        )
    finally:
        loop.close()
