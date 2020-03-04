import asyncio
import logging
import pickle
import time

from web3.contract import ConciseContract

from apps.sdk.utils import wait_for_receipt

from honeybadgermpc.elliptic_curve import Subgroup
from honeybadgermpc.field import GF
from honeybadgermpc.offline_randousha import randousha
from honeybadgermpc.utils.misc import _create_task

field = GF(Subgroup.BLS12_381)


class PreProcessor:
    """Class to generate preprocessing elements.


    Notes
    -----
    From the paper [0]_:

        The offline phase [9]_, [11]_ runs continuously to replenish a
        buffer of preprocessing elements used by the online phase.

    References
    ----------
    .. [0] Donghang Lu, Thomas Yurek, Samarth Kulshreshtha, Rahul Govind,
        Aniket Kate, and Andrew Miller. 2019. HoneyBadgerMPC and
        AsynchroMix: Practical Asynchronous MPC and its Application to
        Anonymous Communication. In Proceedings of the 2019 ACM SIGSAC
        Conference on Computer and Communications Security (CCS ’19).
        Association for Computing Machinery, New York, NY, USA, 887–903.
        DOI:https://doi.org/10.1145/3319535.3354238
    .. [9] Assi Barak, Martin Hirt, Lior Koskas, and Yehuda Lindell.
        2018. An End-to-EndSystem for Large Scale P2P MPC-as-a-Service
        and Low-Bandwidth MPC for Weak Participants. In Proceedings of
        the 2018 ACM SIGSAC Conference on Computer and Communications
        Security. ACM, 695–712.
    .. [11] Zuzana Beerliová-Trubíniová and Martin Hirt. 2008.
        Perfectly-secure MPC with linear communication complexity. In
        Theory of Cryptography Conference. Springer, 213–230.
    """

    def __init__(
        self, sid, myid, w3, *, contract=None, db, channel=None,
    ):
        """
        Parameters
        ----------
        sid: int
            Session id.
        myid: int
            Client id.
        send:
            Function used to send messages.
        recv:
            Function used to receive messages.
        w3:
            Connection instance to an Ethereum node.
        contract_context: dict
            Contract attributes needed to interact with the contract
            using web3. Should contain the address, name and source code
            file path.
        """
        self.sid = sid
        self.myid = myid
        self.contract = contract
        self.w3 = w3
        self._preprocessing = _create_task(self._offline_inputmasks_loop())
        self.db = db
        self.get_send_recv = channel
        self.elements = {}  # cache of elements (inputmasks, triples, bits, etc)
        self._init_elements("inputmasks")

    def _init_elements(self, *element_names):
        for element_name in element_names:
            try:
                _element_set = self.db[element_name.encode()]
            except KeyError:
                element_set = []
            else:
                element_set = pickle.loads(_element_set)
            self.elements[element_name] = element_set

    async def start(self):
        await self._preprocessing
        # await self._offline_inputmasks_loop()

    async def _preprocess_report(self):
        # Submit the preprocessing report
        logging.info(f"node {self.myid} submitting preprocessing report ...")
        report = [len(e) for e in self.elements.values()]
        logging.info(f"report for elements: {tuple(self.elements.keys())} is: {report}")
        tx_hash = self.contract.functions.preprocess_report(report).transact(
            {"from": self.w3.eth.accounts[self.myid]}
        )

        # Wait for the tx receipt
        logging.info(f"node {self.myid} waiting for preprocessing report receipt")
        tx_receipt = await wait_for_receipt(self.w3, tx_hash)
        logging.info(
            f"node {self.myid} received preprocessing report receipt: {tx_receipt}"
        )
        return tx_receipt

    async def _offline_inputmasks_loop(self):
        contract_concise = ConciseContract(self.contract)
        n = contract_concise.n()
        t = contract_concise.t()
        K = contract_concise.K()  # noqa: N806
        preproc_round = 0
        k = K // (n - 2 * t) or 1  # batch size
        while True:
            logging.info(f"starting preprocessing round {preproc_round}")
            # Step 1. I) Wait until needed
            while True:
                inputmasks_available = contract_concise.inputmasks_available()
                totalmasks = contract_concise.preprocess()

                logging.info(f"available input masks: {inputmasks_available}")
                logging.info(f"total input masks: {totalmasks}")
                # Policy: try to maintain a buffer of 10 input masks
                target = 10 * K
                if inputmasks_available < target:
                    break
                # already have enough input masks, sleep
                await asyncio.sleep(5)

            # Step 1. II) Run Randousha
            logging.info(
                f"[{self.myid}] totalmasks: {totalmasks} \
                inputmasks available: {inputmasks_available} \
                target: {target} Initiating Randousha {k * (n - 2*t)}"
            )
            send, recv = self.get_send_recv(f"preproc:inputmasks:{preproc_round}")
            start_time = time.time()
            rs_t, rs_2t = zip(*await randousha(n, t, k, self.myid, send, recv, field))
            assert len(rs_t) == len(rs_2t) == k * (n - 2 * t)

            # Note: here we just discard the rs_2t
            # In principle both sides of randousha could be used with
            # a small modification to randousha
            end_time = time.time()
            logging.info(f"[{self.myid}] Randousha finished in {end_time-start_time}")
            logging.info(f"len(rs_t): {len(rs_t)}")
            logging.info(f"rs_t: {rs_t}")
            self.elements["inputmasks"] += rs_t
            self.db[b"inputmasks"] = pickle.dumps(self.elements["inputmasks"])

            # Step 1. III) Submit an updated report
            await self._preprocess_report()

            # Increment the preprocessing round and continue
            preproc_round += 1
