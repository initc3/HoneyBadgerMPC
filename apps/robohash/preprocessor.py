import asyncio
import logging
import pickle
import time

from web3.contract import ConciseContract

from apps.robohash._preprocessor import PreProcessor as _PreProcessor, field

# from apps.sdk.preprocessor import PreProcessor as _PreProcessor, field

from honeybadgermpc.offline_randousha import generate_bits, generate_triples
from honeybadgermpc.utils.misc import _create_task


class PreProcessor(_PreProcessor):
    def __init__(
        self,
        sid,
        myid,
        w3,
        *,
        contract=None,
        db,
        channel=None,
        elements=("triples", "bits"),
    ):
        super().__init__(sid, myid, w3, contract=contract, db=db, channel=channel)
        self._init_elements(*elements)
        self._offline_pp_elems_task = _create_task(self._offline_pp_elems_loop())

    async def start(self):
        await super().start()
        await self._offline_pp_elems_task

    async def _offline_pp_elems_loop(self):
        contract_concise = ConciseContract(self.contract)
        n = contract_concise.n()
        t = contract_concise.t()
        preproc_round = 0
        PER_MIX_TRIPLES = contract_concise.PER_MIX_TRIPLES()  # noqa: N806
        PER_MIX_BITS = contract_concise.PER_MIX_BITS()  # noqa: N806

        # FIXME not sure if needed
        # Start up:
        # await self._preprocess_report()

        while True:
            # Wait for more pp elements to be needed
            while True:
                ppelems_available = contract_concise.pp_elems_available()

                # Policy: try to maintain a buffer of mixes
                target = 100
                if ppelems_available < target:
                    break
                # already have enough triples/bits, sleep
                await asyncio.sleep(5)

            # triples
            logging.info(
                f"[{self.myid}] preprocessing elements available: {ppelems_available} \
                   target: {target}"
            )
            logging.info(f"[{self.myid}] Initiating Triples {PER_MIX_TRIPLES}")
            send, recv = self.get_send_recv(f"preproc:mixes:triples:{preproc_round}")
            start_time = time.time()
            triples = await generate_triples(
                n, t, PER_MIX_TRIPLES, self.myid, send, recv, field
            )
            end_time = time.time()
            logging.info(f"[{self.myid}] Triples finished in {end_time-start_time}")
            self.elements["triples"] += triples
            self.db[b"triples"] = pickle.dumps(self.elements["triples"])

            # bits
            logging.info(f"[{self.myid}] Initiating Bits {PER_MIX_BITS}")
            send, recv = self.get_send_recv(f"preproc:mixes:bits:{preproc_round}")
            start_time = time.time()
            bits = await generate_bits(n, t, PER_MIX_BITS, self.myid, send, recv, field)
            end_time = time.time()
            logging.info(f"[{self.myid}] Bits finished in {end_time-start_time}")
            self.elements["bits"] += bits
            self.db[b"bits"] = pickle.dumps(self.elements["bits"])

            # Submit an updated report
            await self._preprocess_report()

            # Increment the preprocessing round and continue
            preproc_round += 1
