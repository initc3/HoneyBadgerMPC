import asyncio
import logging
import time

from web3.contract import ConciseContract

from apps.utils import wait_for_receipt

from honeybadgermpc.elliptic_curve import Subgroup
from honeybadgermpc.field import GF
from honeybadgermpc.mpc import Mpc
from honeybadgermpc.offline_randousha import randousha
from honeybadgermpc.utils.misc import (
    print_exception_callback,
    subscribe_recv,
    wrap_send,
)

field = GF(Subgroup.BLS12_381)


class Server:
    """MPC server class. The server's main functions are, for one epoch:

    * preprocessing for client masks and intershard masks
    * consume secret from client
    * produce masked message for other shard
    * consume secret from other shard

    Notes
    -----
    preprocessing
    ^^^^^^^^^^^^^
    1. (inner-shard communication) generate input masks via randousha
       (requires innershard collab with other nodes)
    2. (inter-shard communication) generate intershard masks via
       randousha (requires intershard collab with other nodes)

    consume secret from client
    ^^^^^^^^^^^^^^^^^^^^^^^^^^
    1. (blockchain state read) consume a client's secret from a contract
    2. (inner-shard communication) unmask the secret in a MPC with
       nodes of its shard

    produce masked message for other shard
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    1. mask the client message with an intershard mask share
    2. (inner-shard communication) open the masked share to get the
       intershard masked message
    3. (blockchain state write) submit the intershard masked message to
       the contract

    consume secret from other shard
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    1. (blockchain state read) consume intershard secret
    2. set [m] = secret - intershard_mask
    3. m = [m].open()
    4. (blockchain state write) notify other shard that message has been
       received -- propose output to contract
    """

    def __init__(
        self,
        sid,
        myid,
        send,
        recv,
        w3,
        contract,
        *,
        shard_id,
        intershardmask_shares,
        is_gateway_shard=False,
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
        contract:
            Contract instance on the Ethereum blockchain.
        """
        self.sid = sid
        self.myid = myid
        self.contract = contract
        self.w3 = w3
        self.shard_id = shard_id
        self.intershardmask_shares = tuple(intershardmask_shares)
        self.is_gateway_shard = is_gateway_shard
        self._init_tasks()
        self._subscribe_task, subscribe = subscribe_recv(recv)

        def _get_send_recv(tag):
            return wrap_send(tag, send), subscribe(tag)

        self.get_send_recv = _get_send_recv
        self._inputmasks = []

    @property
    def global_id(self):
        """Unique of id of the server with respect to other servers,
        in its shard and other shards.
        """
        return f"{self.myid}-{self.shard_id}"

    @property
    def eth_account_index(self):
        return self.myid + self.shard_id * 4

    def _init_tasks(self):
        if self.is_gateway_shard:
            self._task1 = asyncio.ensure_future(self._offline_inputmasks_loop())
            self._task1.add_done_callback(print_exception_callback)
        if not self.is_gateway_shard:
            self._task1b = asyncio.ensure_future(self._recv_intershard_msg_loop())
            self._task1b.add_done_callback(print_exception_callback)
        self._task2 = asyncio.ensure_future(self._client_request_loop())
        self._task2.add_done_callback(print_exception_callback)
        self._task3 = asyncio.ensure_future(self._mpc_loop())
        self._task3.add_done_callback(print_exception_callback)
        self._task4 = asyncio.ensure_future(self._mpc_initiate_loop())
        self._task4.add_done_callback(print_exception_callback)

    async def join(self):
        if self.is_gateway_shard:
            await self._task1
        if not self.is_gateway_shard:
            await self._task1b
        await self._task2
        await self._task3
        await self._task4
        await self._subscribe_task

    #######################
    # Step 1. Offline Phase
    #######################
    """
    1a. offline inputmasks
    """

    async def _preprocess_report(self):
        # Submit the preprocessing report
        tx_hash = self.contract.functions.preprocess_report(
            [len(self._inputmasks)]
        ).transact({"from": self.w3.eth.accounts[self.eth_account_index]})

        # Wait for the tx receipt
        tx_receipt = await wait_for_receipt(self.w3, tx_hash)
        return tx_receipt

    async def _offline_inputmasks_loop(self):
        contract_concise = ConciseContract(self.contract)
        n = contract_concise.n()
        t = contract_concise.t()
        preproc_round = 0
        k = 1  # batch size
        while True:
            # Step 1. I) Wait until needed
            while True:
                inputmasks_available = contract_concise.inputmasks_available()
                totalmasks = contract_concise.preprocess()[1]
                # Policy: try to maintain a buffer of 10 input masks
                target = 10
                if inputmasks_available < target:
                    break
                # already have enough input masks, sleep
                await asyncio.sleep(5)

            # Step 1. II) Run Randousha
            logging.info(
                f"[{self.global_id}] totalmasks: {totalmasks} \
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
            logging.debug(
                f"[{self.global_id}] Randousha finished in {end_time-start_time}"
            )
            logging.debug(f"len(rs_t): {len(rs_t)}")
            logging.debug(f"rs_t: {rs_t}")
            self._inputmasks += rs_t

            # Step 1. III) Submit an updated report
            await self._preprocess_report()

            # Increment the preprocessing round and continue
            preproc_round += 1

    async def _client_request_loop(self):
        # Task 2. Handling client input
        # TODO: if a client requests a share,
        # check if it is authorized and if so send it along
        pass

    def _collect_client_input(self, *, index, queue):
        # Get the public input (masked message)
        masked_message_bytes, inputmask_idx = queue(index)
        masked_message = field(int.from_bytes(masked_message_bytes, "big"))
        # Get the input mask
        logging.debug(f"[{self.global_id}] inputmask idx: {inputmask_idx}")
        logging.debug(f"[{self.global_id}] inputmasks: {self._inputmasks}")
        try:
            inputmask = self._inputmasks[inputmask_idx]
        except KeyError as err:
            logging.error(err)
            logging.error(f"[{self.global_id}] inputmask idx: {inputmask_idx}")
            logging.error(f"[{self.global_id}] inputmasks: {self._inputmasks}")

        msg_field_elem = masked_message - inputmask
        return msg_field_elem

    # TODO generalize client and intershard collection
    def _collect_intershard_msg(self, *, index, queue):
        masked_message_bytes, mask_idx = queue(index)
        masked_message = field(int.from_bytes(masked_message_bytes, "big"))
        mask = self.intershardmask_shares[mask_idx]
        msg_field_elem = masked_message - mask
        return msg_field_elem

    async def _mpc_loop(self):
        # Task 3. Participating in MPC epochs
        contract_concise = ConciseContract(self.contract)
        n = contract_concise.n()
        t = contract_concise.t()

        epoch = 0
        while True:
            # 3.a. Wait for the next MPC to be initiated
            while True:
                epochs_initiated = contract_concise.epochs_initiated()
                if epochs_initiated > epoch:
                    break
                await asyncio.sleep(5)

            if self.is_gateway_shard:
                client_msg_field_elem = self._collect_client_input(
                    index=epoch, queue=contract_concise.input_queue
                )

                # 3.d. Call the MPC program
                async def prog(ctx):
                    logging.info(f"[{self.global_id}] Running MPC network")
                    client_msg_share = ctx.Share(client_msg_field_elem)
                    client_msg = await client_msg_share.open()
                    logging.info(f"[{self.global_id}] Client secret opened.")
                    mask_field_elem = field(self.intershardmask_shares[epoch])
                    intershard_masked_msg_share = ctx.Share(
                        client_msg + mask_field_elem
                    )
                    intershard_masked_msg = await intershard_masked_msg_share.open()
                    return intershard_masked_msg.value

                send, recv = self.get_send_recv(f"mpc:{epoch}")
                logging.info(f"[{self.global_id}] MPC initiated:{epoch}")

                config = {}
                ctx = Mpc(
                    f"mpc:{epoch}",
                    n,
                    t,
                    self.myid,
                    send,
                    recv,
                    prog,
                    config,
                    shard_id=self.shard_id,
                )
                result = await ctx._run()
                logging.info(
                    f"[{self.global_id}] MPC Intershard message queued: {result}"
                )

                # 3.e. Output the published messages to contract
                # TODO instead of proposing output, mask the output with an intershard
                # mask, and submit the masked output
                #
                # 1) fetch an intershard mask
                # 2) intershard_secret = message + intershard_mask
                # 3) submit intershard secret to contract
                intershard_masked_msg = result.to_bytes(32, "big")
                tx_hash = self.contract.functions.transfer_intershard_message(
                    epoch, intershard_masked_msg
                ).transact({"from": self.w3.eth.accounts[self.eth_account_index]})
                tx_receipt = await wait_for_receipt(self.w3, tx_hash)
                rich_logs = self.contract.events.IntershardMessageReady().processReceipt(
                    tx_receipt
                )
                if rich_logs:
                    epoch = rich_logs[0]["args"]["epoch"]
                    msg_idx = rich_logs[0]["args"]["msg_idx"]
                    masked_msg = rich_logs[0]["args"]["masked_msg"]
                    logging.info(
                        f"[{self.global_id}] MPC INTERSHARD XFER [{epoch}] {msg_idx} {masked_msg}"
                    )

            epoch += 1

    async def _recv_intershard_msg_loop(self):
        # Task 3. Participating in MPC epochs
        contract_concise = ConciseContract(self.contract)
        n = contract_concise.n()
        t = contract_concise.t()

        epoch = 0
        while True:
            # Wait for a message to be available
            while True:
                intershard_msg_ready = contract_concise.intershard_msg_ready()
                if intershard_msg_ready > epoch:
                    break
                await asyncio.sleep(5)

            if not self.is_gateway_shard:
                msg_field_elem = self._collect_intershard_msg(
                    index=epoch, queue=contract_concise.intershard_msg_queue
                )

                # Call the MPC program
                async def prog(ctx):
                    logging.info(f"[{self.global_id}] Processing intershard message")
                    msg_share = ctx.Share(msg_field_elem)
                    msg = await msg_share.open()
                    logging.info(f"[{self.global_id}] Intershard message opened.")
                    return msg.value

                send, recv = self.get_send_recv(f"mpc:{epoch}")
                logging.info(
                    f"[{self.global_id}] MPC intershard message processing:{epoch}"
                )

                config = {}
                ctx = Mpc(
                    f"mpc:{epoch}",
                    n,
                    t,
                    self.myid,
                    send,
                    recv,
                    prog,
                    config,
                    shard_id=self.shard_id,
                )
                result = await ctx._run()
                logging.info(
                    f"[{self.global_id}] MPC intershard message processing done {result}"
                )
                intershard_msg = result.to_bytes(32, "big").decode().strip("\x00")
                logging.info(
                    f"[{self.global_id}] MPC intershard message processing done {intershard_msg}"
                )
                logging.info(
                    f"[{self.global_id}] eth account index: {self.eth_account_index}"
                )
                eth_addr = self.w3.eth.accounts[self.eth_account_index]
                logging.info(f"[{self.global_id}] eth addr: {eth_addr}")
                balance = self.w3.eth.getBalance(eth_addr)
                logging.info(f"[{self.global_id}] eth account balance: {balance}")
                try:
                    tx_hash = self.contract.functions.propose_output(
                        epoch, intershard_msg
                    ).transact({"from": self.w3.eth.accounts[self.eth_account_index]})
                except ValueError as err:
                    logging.error(f"[{self.global_id}] eth addr: {eth_addr}")
                    logging.error(f"[{self.global_id}] balance: {balance}")
                    raise ValueError(f"[{self.global_id}] {err}")
                tx_receipt = await wait_for_receipt(self.w3, tx_hash)
                rich_logs = self.contract.events.MpcOutput().processReceipt(tx_receipt)
                if rich_logs:
                    epoch = rich_logs[0]["args"]["epoch"]
                    output = rich_logs[0]["args"]["output"]
                    logging.info(f"[{self.global_id}] MPC OUTPUT[{epoch}] {output}")
            epoch += 1

    async def _mpc_initiate_loop(self):
        # Task 4. Initiate MPC epochs
        contract_concise = ConciseContract(self.contract)
        K = contract_concise.K()  # noqa: N806
        while True:
            # Step 4.a. Wait until there are k values then call initiate_mpc
            while True:
                inputs_ready = contract_concise.inputs_ready()
                if inputs_ready >= K:
                    break
                await asyncio.sleep(5)

            # Step 4.b. Call initiate_mpc
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
            tx_receipt = await wait_for_receipt(self.w3, tx_hash)
            rich_logs = self.contract.events.MpcEpochInitiated().processReceipt(
                tx_receipt
            )
            if rich_logs:
                epoch = rich_logs[0]["args"]["epoch"]
                logging.info(f"[{self.global_id}] MPC epoch initiated: {epoch}")
            else:
                logging.info(f"[{self.global_id}] initiate_mpc failed (redundant?)")
            await asyncio.sleep(10)
