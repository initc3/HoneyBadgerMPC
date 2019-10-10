import asyncio
import logging
from honeybadgermpc.hbavss import HbAvssLight
from honeybadgermpc.avss_value_processor import AvssValueProcessor
from honeybadgermpc.broadcast.crypto.boldyreva import dealer
from honeybadgermpc.betterpairing import G1, ZR
from honeybadgermpc.progs.random_refinement import refine_randoms
from honeybadgermpc.field import GF
from honeybadgermpc.elliptic_curve import Subgroup
from honeybadgermpc.utils.misc import wrap_send, subscribe_recv
from abc import ABC, abstractmethod


def get_avss_params(n, t, my_id):
    g, h = G1.rand(seed=[0, 0, 0, 1]), G1.rand(seed=[0, 0, 0, 2])
    public_keys, private_keys = [None] * n, [None] * n
    for i in range(n):
        private_keys[i] = ZR.random(seed=17 + i)
        public_keys[i] = pow(g, private_keys[i])
    return g, h, public_keys, private_keys[my_id]


class PreProcessingBase(ABC):
    PERIOD_IN_SECONDS = 3

    def __init__(
        self,
        n,
        t,
        my_id,
        send,
        recv,
        tag,
        batch_size=10,
        avss_value_processor_chunk_size=1,
    ):
        self.n, self.t, self.my_id = n, t, my_id
        self.tag = tag
        self.avss_value_processor_chunk_size = avss_value_processor_chunk_size

        # Batch size of values to AVSS from a node
        self.batch_size = batch_size
        # Minimum number of values before triggering another set of AVSSes
        self.low_watermark = self.batch_size

        self.output_queue = asyncio.Queue()

        # Create a mechanism to split the `send` and `recv` channels based on `tag`
        subscribe_recv_task, subscribe = subscribe_recv(recv)
        self.tasks = [subscribe_recv_task]

        def _get_send_recv(tag):
            return wrap_send(tag, send), subscribe(tag)

        self.get_send_recv = _get_send_recv

    async def get(self):
        return await self.output_queue.get()

    @abstractmethod
    def _get_input_batch(self):
        raise NotImplementedError

    async def _trigger_and_wait_for_avss(self, avss_id):
        inputs = self._get_input_batch()
        assert type(inputs) in [tuple, list]
        avss_tasks = []
        avss_tasks.append(
            asyncio.create_task(
                self.avss_instance.avss_parallel(
                    avss_id, len(inputs), values=inputs, dealer_id=self.my_id
                )
            )
        )
        for i in range(self.n):
            if i != self.my_id:
                avss_tasks.append(
                    asyncio.create_task(
                        self.avss_instance.avss_parallel(
                            avss_id, len(inputs), dealer_id=i
                        )
                    )
                )
        await asyncio.gather(*avss_tasks)

    async def _runner(self):
        counter = 0
        logging.debug("[%d] Starting preprocessing runner: %s", self.my_id, self.tag)
        while True:
            # If the number of values in the output queue are below the lower
            # watermark then we want to trigger the next set of AVSSes.
            if self.output_queue.qsize() < self.low_watermark:
                logging.debug("[%d] Starting AVSS Batch: %d", self.my_id, counter)
                await self._trigger_and_wait_for_avss(counter)
                logging.debug("[%d] AVSS Batch Completed: %d", self.my_id, counter)
                counter += 1
            # Wait for sometime before checking again.
            await asyncio.sleep(PreProcessingBase.PERIOD_IN_SECONDS)

    async def _get_output_batch(self, group_size=1):
        for i in range(self.batch_size):
            batch = []
            while True:
                value = await self.avss_value_processor.get()
                if value is None:
                    break
                batch.append(value)
            assert len(batch) / group_size >= self.n - self.t
            assert len(batch) / group_size <= self.n
            yield batch

    async def _extract(self):
        raise NotImplementedError

    def __enter__(self):
        n, t, my_id = self.n, self.t, self.my_id
        send, recv = self.get_send_recv(f"{self.tag}-AVSS")
        g, h, pks, sk = get_avss_params(n, t, my_id)
        crs = [g, h]
        self.avss_instance = HbAvssLight(pks, sk, crs, n, t, my_id, send, recv)
        self.avss_instance.__enter__()
        self.tasks.append(asyncio.create_task(self._runner()))

        send, recv = self.get_send_recv(f"{self.tag}-AVSS_VALUE_PROCESSOR")
        pk, sks = dealer(n, t + 1, seed=17)
        self.avss_value_processor = AvssValueProcessor(
            pk,
            sks[my_id],
            n,
            t,
            my_id,
            send,
            recv,
            self.avss_instance.output_queue.get,
            self.avss_value_processor_chunk_size,
        )
        self.avss_value_processor.__enter__()
        self.tasks.append(asyncio.create_task(self._extract()))
        return self

    def __exit__(self, *args):
        for task in self.tasks:
            task.cancel()
        self.avss_instance.__exit__(*args)
        self.avss_value_processor.__exit__(*args)


class RandomGenerator(PreProcessingBase):
    def __init__(self, n, t, my_id, send, recv, batch_size=10):
        super(RandomGenerator, self).__init__(
            n, t, my_id, send, recv, "rand", batch_size
        )
        self.field = GF(Subgroup.BLS12_381)

    def _get_input_batch(self):
        return [self.field.random().value for _ in range(self.batch_size)]

    async def _extract(self):
        while True:
            async for batch in self._get_output_batch():
                random_shares_int = await asyncio.gather(*batch)
                output_shares_int = refine_randoms(
                    self.n, self.t, self.field, random_shares_int
                )
                for value in output_shares_int:
                    self.output_queue.put_nowait(self.field(value))


class TripleGenerator(PreProcessingBase):
    def __init__(self, n, t, my_id, send, recv, batch_size=10):
        super(TripleGenerator, self).__init__(
            n,
            t,
            my_id,
            send,
            recv,
            "triple",
            batch_size,
            avss_value_processor_chunk_size=3,
        )
        self.field = GF(Subgroup.BLS12_381)

    def _get_input_batch(self):
        inputs = []
        for _ in range(self.batch_size):
            a, b = self.field.random(), self.field.random()
            ab = a * b
            inputs += [a.value, b.value, ab.value]
        return inputs

    async def _extract(self):
        while True:
            async for batch in self._get_output_batch(3):
                triple_shares_int = await asyncio.gather(*batch)
                # Number of nodes which have contributed values to this batch
                n = len(triple_shares_int)
                assert n % 3 == 0

                for i in range(0, n, 3):
                    a, b, ab = triple_shares_int[i : i + 3]
                    self.output_queue.put_nowait((a, b, ab))


async def get_random(n, t, my_id, send, recv):
    with RandomGenerator(n, t, my_id, send, recv) as random_generator:
        while True:
            yield await random_generator.get()


async def _mpc_prog(context, **kwargs):
    randoms = kwargs["randoms"]
    n, i = 10, 0
    async for random in randoms:
        logging.info("i: %d => %d", i, await context.Share(random).open())
        i += 1
        if i == n:
            break
    await randoms.aclose()


async def _prog(peers, n, t, my_id):
    async with ProcessProgramRunner(peers, n, t, my_id) as runner:
        send, recv = runner.get_send_recv(0)
        runner.execute(1, _mpc_prog, randoms=get_random(n, t, my_id, send, recv))


if __name__ == "__main__":
    from honeybadgermpc.config import HbmpcConfig
    from honeybadgermpc.ipc import ProcessProgramRunner

    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    loop.set_debug(True)
    try:
        loop.run_until_complete(
            _prog(HbmpcConfig.peers, HbmpcConfig.N, HbmpcConfig.t, HbmpcConfig.my_id)
        )
    finally:
        loop.close()
