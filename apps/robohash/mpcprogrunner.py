import asyncio
import logging
import pickle

from honeybadgermpc.elliptic_curve import Subgroup
from honeybadgermpc.field import GF
from honeybadgermpc.mpc import Mpc
from honeybadgermpc.utils.misc import _create_task

# imports needed for asynchromix
from honeybadgermpc.preprocessing import PreProcessedElements

field = GF(Subgroup.BLS12_381)

# TODO if possible, avoid the need for such a map. One way to do so would be to
# simply adopt the same naming convention for the db and the PreProcessingElements
# methods.
PP_ELEMENTS_MIXIN_MAP = {"triples": "_triples", "bits": "_one_minus_ones"}


def _load_pp_elements(node_id, n, t, epoch, db, cache, elements_metadata):
    cache._init_data_dir()
    elements = {}
    for element_name, slice_size in elements_metadata.items():
        _elements = pickle.loads(db[element_name.encode()])
        elements[element_name] = _elements[
            epoch * slice_size : (epoch + 1) * slice_size
        ]

    mixins = tuple(
        getattr(cache, PP_ELEMENTS_MIXIN_MAP[element_name]) for element_name in elements
    )
    # Hack explanation... the relevant mixins are in triples
    key = (node_id, n, t)
    for mixin in mixins:
        if key in mixin.cache:
            del mixin.cache[key]
            del mixin.count[key]

    for mixin, (kind, elems) in zip(mixins, elements.items()):
        if kind == "triples":
            elems = [e for sublist in elems for e in sublist]
        elems = [e.value for e in elems]
        mixin_filename = mixin.build_filename(n, t, node_id)
        logging.info(f"writing preprocessed {kind} to file {mixin_filename}")
        logging.info(f"number of elements is: {len(elems)}")
        mixin._write_preprocessing_file(mixin_filename, t, node_id, elems, append=False)

    for mixin in mixins:
        mixin._refresh_cache()


class MPCProgRunner:
    """MPC participant responsible to take part into a multi-party
    computation.

    """

    def __init__(
        self,
        sid,
        myid,
        w3,
        *,
        contract=None,
        db=None,
        channel=None,
        prog=None,
        mpc_config=None,
    ):
        """
        Parameters
        ----------
        sid: int
            Session id.
        myid: int
            Client id.
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
        self._create_tasks()
        self.get_send_recv = channel
        self.db = db
        self.prog = prog
        self.mpc_config = mpc_config or {}
        self.elements = {}  # cache of elements (cryptodna, triples, bits, etc)
        # self._init_elements("cryptodna", "triples", "bits")
        self._init_elements("cryptodna")

    def _init_elements(self, *element_names):
        for element_name in element_names:
            try:
                _element_set = self.db[element_name.encode()]
            except KeyError:
                element_set = []
            else:
                element_set = pickle.loads(_element_set)
            self.elements[element_name] = element_set

    def _create_tasks(self):
        self._mpc = _create_task(self._mpc_loop())
        self._mpc_init = _create_task(self._mpc_initiate_loop())

    async def start(self):
        await self._mpc
        await self._mpc_init

    async def _mpc_loop(self):
        logging.info("MPC loop started ...")
        # Task 3. Participating in MPC epochs
        # contract_concise = ConciseContract(self.contract)
        n = self.contract.caller.n()
        t = self.contract.caller.t()
        K = self.contract.caller.K()  # noqa: N806

        # XXX asynchromix
        PER_MIX_TRIPLES = self.contract.caller.PER_MIX_TRIPLES()  # noqa: N806
        PER_MIX_BITS = self.contract.caller.PER_MIX_BITS()  # noqa: N806
        pp_elements = PreProcessedElements()
        # deletes sharedata/ if present
        pp_elements.clear_preprocessing()
        # XXX asynchromix

        epoch = 0
        while True:
            logging.info(f"starting new loop at epoch: {epoch}")
            # 3.a. Wait for the next MPC to be initiated
            while True:
                logging.info(f"waiting for epoch {epoch} to be initiated ...")
                epochs_initiated = self.contract.caller.epochs_initiated()
                logging.info(
                    f"result of querying contract for epochs initiated: {epochs_initiated}"
                )
                if epochs_initiated > epoch:
                    break
                await asyncio.sleep(5)

            # XXX START HERE
            # 3.b. Collect the input
            # Get the public input (masked message)
            robot_details = []
            for idx in range(epoch * K, (epoch + 1) * K):
                (
                    token_id_1,
                    public_genome_1,
                    token_id_2,
                    public_genome_2,
                    token_id_3,
                ) = self.contract.caller.robot_request_queue(idx)
                logging.info(f"token_id_1: {token_id_1}")
                logging.info(f"public_genome_1: {public_genome_1}")
                logging.info(f"token_id_2: {token_id_2}")
                logging.info(f"public_genome_2: {public_genome_2}")
                logging.info(f"token_id_3: {token_id_3}")
                if (
                    token_id_1 not in self.elements["cryptodna"]
                    or token_id_2 not in self.elements["cryptodna"]
                    or token_id_3 not in self.elements["cryptodna"]
                ):
                    self.elements["cryptodna"] = pickle.loads(self.db[b"cryptodna"])
                try:
                    cryptodna_1 = self.elements["cryptodna"][token_id_1]
                except IndexError as err:
                    logging.error(
                        f"token id: {token_id_1} not in {self.elements['cryptodna']}"
                    )
                    raise err
                try:
                    cryptodna_2 = self.elements["cryptodna"][token_id_2]
                except IndexError as err:
                    logging.error(
                        f"token id: {token_id_2} not in {self.elements['cryptodna']}"
                    )
                    raise err
                try:
                    cryptodna_3 = self.elements["cryptodna"][token_id_3]
                except IndexError as err:
                    logging.error(
                        f"token id: {token_id_3} not in {self.elements['cryptodna']}"
                    )
                    raise err

                robot_details.append(
                    {
                        "parent_1": (token_id_1, public_genome_1, cryptodna_1),
                        "parent_2": (token_id_2, public_genome_2, cryptodna_2),
                        "kid": (token_id_3, cryptodna_3),
                    }
                )

            _load_pp_elements(
                self.myid,
                n,
                t,
                epoch,
                self.db,
                pp_elements,
                {"triples": PER_MIX_TRIPLES, "bits": PER_MIX_BITS},
            )
            send, recv = self.get_send_recv(f"mpc:{epoch}")
            logging.info(f"[{self.myid}] MPC initiated:{epoch}")

            prog_kwargs = {
                "robot_details": robot_details,
            }
            ctx = Mpc(
                f"mpc:{epoch}",
                n,
                t,
                self.myid,
                send,
                recv,
                self.prog,
                self.mpc_config,
                **prog_kwargs,
            )
            _result, cryptodnas = await ctx._run()
            crypto_DNAs = ", ".join(
                ": ".join((f"ROBOT-{token_id:05d}", f"{cryptodna}"))
                for token_id, cryptodna in cryptodnas
            )
            logging.info(f"[{self.myid}] MPC complete {crypto_DNAs}")
            logging.info(f"[{self.myid}] MPC complete - child genome: {_result}")

            # 3.e. Output the published messages to contract
            tx_hash = self.contract.functions.propose_output(
                # epoch, crypto_DNAs
                epoch,
                _result,
            ).transact({"from": self.w3.eth.accounts[self.myid]})
            tx_receipt = self.w3.eth.waitForTransactionReceipt(tx_hash)
            rich_logs = self.contract.events.MpcOutput().processReceipt(tx_receipt)
            if rich_logs:
                epoch = rich_logs[0]["args"]["epoch"]
                output = rich_logs[0]["args"]["output"]
                logging.info(40 * "*")
                logging.info(f"[{self.myid}] MPC OUTPUT[{epoch}] {output}")
                logging.info(40 * "*")

            epoch += 1

    async def _mpc_initiate_loop(self):
        logging.info("MPC initiator loop started ...")
        # Task 4. Initiate MPC epochs
        # contract_concise = ConciseContract(self.contract)
        # K = contract_concise.K()  # noqa: N806
        K = self.contract.caller.K()  # noqa: N806
        epoch = None
        while True:
            logging.info(f"looping to initiate MPC for epoch {epoch} ...")
            # Step 4.a. Wait until there are k values then call initiate_mpc

            while True:
                number_of_robot_requests = self.contract.caller.start_robot_assembly()
                pp_elems_available = self.contract.caller.pp_elems_available()
                logging.info(f"NUMBER OF ROBOT REQUESTS: {number_of_robot_requests}")
                logging.info(f"PREPROCESSING ELEMENTS AVAILABLE?: {pp_elems_available}")
                if number_of_robot_requests >= K and pp_elems_available >= 1:
                    break
                await asyncio.sleep(5)

            # Step 4.b. Call initiate_mpc
            logging.info("call contract function initiate_mpc() ...")
            try:
                tx_hash = self.contract.functions.initiate_mpc().transact(
                    {"from": self.w3.eth.accounts[0]}
                )
            except ValueError as err:
                # Since only one server is needed to initiate the MPC, once
                # intiated, a ValueError will occur due to the race condition
                # between the servers.
                logging.debug(err)
                continue
            tx_receipt = self.w3.eth.waitForTransactionReceipt(tx_hash)
            rich_logs = self.contract.events.MpcEpochInitiated().processReceipt(
                tx_receipt
            )
            if rich_logs:
                epoch = rich_logs[0]["args"]["epoch"]
                logging.info(f"[{self.myid}] MPC epoch initiated: {epoch}")
            else:
                logging.info(f"[{self.myid}] initiate_mpc failed (redundant?)")
            await asyncio.sleep(10)
