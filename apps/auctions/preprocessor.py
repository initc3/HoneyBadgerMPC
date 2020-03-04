import asyncio
import logging
import pickle
import time

from web3.contract import ConciseContract

from apps.toolkit.preprocessor import PreProcessor as _PreProcessor, field

from honeybadgermpc.offline_randousha import generate_bits, generate_triples
from honeybadgermpc.utils.misc import _create_task


class PreProcessor(_PreProcessor):
    def __init__(self, sid, myid, w3, *, contract=None, db, channel=None):
        super().__init__(sid, myid, w3, contract=contract, db=db, channel=channel)
        self._init_elements("triples", "bits")
        self._offline_mixes_task = _create_task(self._offline_mixes_loop())

    async def start(self):
        await super().start()
        await self._offline_mixes_task

    async def _offline_mixes_loop(self):
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
            # Step 1a. I) Wait for more triples/bits to be needed
            while True:
                # TODO implement mixes_available() in contract
                mixes_available = contract_concise.mixes_available()

                # Policy: try to maintain a buffer of mixes
                target = 10
                if mixes_available < target:
                    break
                # already have enough triples/bits, sleep
                await asyncio.sleep(5)

            # Step 1a. II) Run generate triples and generate_bits
            logging.info(
                f"[{self.myid}] mixes available: {mixes_available} \
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

            # Bits
            logging.info(f"[{self.myid}] Initiating Bits {PER_MIX_BITS}")
            send, recv = self.get_send_recv(f"preproc:mixes:bits:{preproc_round}")
            start_time = time.time()
            bits = await generate_bits(n, t, PER_MIX_BITS, self.myid, send, recv, field)
            end_time = time.time()
            logging.info(f"[{self.myid}] Bits finished in {end_time-start_time}")

            # Append each triple
            self.elements["triples"] += triples
            self.elements["bits"] += bits
            self.db[b"triples"] = pickle.dumps(self.elements["triples"])
            self.db[b"bits"] = pickle.dumps(self.elements["bits"])

            # Step 1a. III) Submit an updated report
            # TODO parametrize generic method in apps/preprocessor.py
            await self._preprocess_report()

            # Increment the preprocessing round and continue
            preproc_round += 1
