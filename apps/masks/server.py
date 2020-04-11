import asyncio
import logging
import time
from pathlib import Path

from aiohttp import web

import toml

from web3.contract import ConciseContract

from apps.utils import fetch_contract, wait_for_receipt

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
    """MPC server class to ..."""

    def __init__(
        self,
        sid,
        myid,
        send,
        recv,
        w3,
        *,
        contract_context,
        http_host="0.0.0.0",
        http_port=8080,
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
        self._contract_context = contract_context
        self.contract = fetch_contract(w3, **contract_context)
        self.w3 = w3
        self._init_tasks()
        self._subscribe_task, subscribe = subscribe_recv(recv)
        self._http_host = http_host
        self._http_port = http_port

        def _get_send_recv(tag):
            return wrap_send(tag, send), subscribe(tag)

        self.get_send_recv = _get_send_recv
        self._inputmasks = []

    def _init_tasks(self):
        self._task1 = asyncio.ensure_future(self._offline_inputmasks_loop())
        self._task1.add_done_callback(print_exception_callback)
        self._task2 = asyncio.ensure_future(self._client_request_loop())
        self._task2.add_done_callback(print_exception_callback)
        self._task3 = asyncio.ensure_future(self._mpc_loop())
        self._task3.add_done_callback(print_exception_callback)
        self._task4 = asyncio.ensure_future(self._mpc_initiate_loop())
        self._task4.add_done_callback(print_exception_callback)
        # self._http_server = asyncio.create_task(self._client_request_loop())
        # self._http_server.add_done_callback(print_exception_callback)

    @classmethod
    def from_dict_config(cls, config, *, send, recv):
        """Create a ``Server`` class instance from a config dict.

        Parameters
        ----------
        config : dict
            The configuration to create the ``Server`` instance.
        send:
            Function used to send messages.
        recv:
            Function used to receive messages.
        """
        from web3 import HTTPProvider, Web3
        from apps.masks.config import CONTRACT_ADDRESS_FILEPATH
        from apps.utils import get_contract_address

        eth_config = config["eth"]
        # contract
        contract_context = {
            "address": get_contract_address(CONTRACT_ADDRESS_FILEPATH),
            "filepath": eth_config["contract_path"],
            "name": eth_config["contract_name"],
        }

        # web3
        eth_rpc_hostname = eth_config["rpc_host"]
        eth_rpc_port = eth_config["rpc_port"]
        w3_endpoint_uri = f"http://{eth_rpc_hostname}:{eth_rpc_port}"
        w3 = Web3(HTTPProvider(w3_endpoint_uri))

        return cls(
            config["session_id"],
            config["id"],
            send,
            recv,
            w3,
            contract_context=contract_context,
            http_host=config["host"],
            http_port=config["port"],
        )

    @classmethod
    def from_toml_config(cls, config_path, *, send, recv):
        """Create a ``Server`` class instance from a config TOML file.

        Parameters
        ----------
        config_path : str
            The path to the TOML configuration file to create the
            ``Server`` instance.
        send:
            Function used to send messages.
        recv:
            Function used to receive messages.
        """
        config = toml.load(config_path)
        # TODO extract resolving of relative path into utils
        context_path = Path(config_path).resolve().parent.joinpath(config["context"])
        config["eth"]["contract_path"] = context_path.joinpath(
            config["eth"]["contract_path"]
        )
        return cls.from_dict_config(config, send=send, recv=recv)

    async def join(self):
        await self._task1
        await self._task2
        await self._task3
        await self._task4
        await self._subscribe_task
        # await self._http_server
        await self._client_request_loop()

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
        ).transact({"from": self.w3.eth.accounts[self.myid]})

        # Wait for the tx receipt
        tx_receipt = await wait_for_receipt(self.w3, tx_hash)
        return tx_receipt

    async def _offline_inputmasks_loop(self):
        contract_concise = ConciseContract(self.contract)
        n = contract_concise.n()
        t = contract_concise.t()
        preproc_round = 0
        k = 1
        while True:
            # Step 1. I) Wait until needed
            while True:
                inputmasks_available = contract_concise.inputmasks_available()
                totalmasks = contract_concise.preprocess()
                # Policy: try to maintain a buffer of 10 input masks
                target = 10
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
            logging.debug(f"[{self.myid}] Randousha finished in {end_time-start_time}")
            logging.debug(f"len(rs_t): {len(rs_t)}")
            logging.debug(f"rs_t: {rs_t}")
            self._inputmasks += rs_t

            # Step 1. III) Submit an updated report
            await self._preprocess_report()

            # Increment the preprocessing round and continue
            preproc_round += 1

    ##################################
    # Web server for input mask shares
    ##################################

    async def _client_request_loop(self):
        """ Task 2. Handling client input

        .. todo:: if a client requests a share, check if it is
            authorized and if so send it along

        """
        routes = web.RouteTableDef()

        @routes.get("/inputmasks/{idx}")
        async def _handler(request):
            idx = int(request.match_info.get("idx"))
            inputmask = self._inputmasks[idx]
            data = {
                "inputmask": inputmask,
                "server_id": self.myid,
                "server_port": self._http_port,
            }
            return web.json_response(data)

        app = web.Application()
        app.add_routes(routes)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host=self._http_host, port=self._http_port)
        await site.start()
        print(f"======= Serving on http://{self._http_host}:{self._http_port}/ ======")
        # pause here for very long time by serving HTTP requests and
        # waiting for keyboard interruption
        await asyncio.sleep(100 * 3600)

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

            # 3.b. Collect the input
            # Get the public input (masked message)
            masked_message_bytes, inputmask_idx = contract_concise.input_queue(epoch)
            masked_message = field(int.from_bytes(masked_message_bytes, "big"))
            inputmask = self._inputmasks[inputmask_idx]  # Get the input mask
            msg_field_elem = masked_message - inputmask

            # 3.d. Call the MPC program
            async def prog(ctx):
                logging.info(f"[{ctx.myid}] Running MPC network")
                msg_share = ctx.Share(msg_field_elem)
                opened_value = await msg_share.open()
                msg = opened_value.value.to_bytes(32, "big").decode().strip("\x00")
                return msg

            send, recv = self.get_send_recv(f"mpc:{epoch}")
            logging.info(f"[{self.myid}] MPC initiated:{epoch}")

            config = {}
            ctx = Mpc(f"mpc:{epoch}", n, t, self.myid, send, recv, prog, config)
            result = await ctx._run()
            logging.info(f"[{self.myid}] MPC complete {result}")

            # 3.e. Output the published messages to contract
            tx_hash = self.contract.functions.propose_output(epoch, result).transact(
                {"from": self.w3.eth.accounts[self.myid]}
            )
            tx_receipt = await wait_for_receipt(self.w3, tx_hash)
            rich_logs = self.contract.events.MpcOutput().processReceipt(tx_receipt)
            if rich_logs:
                epoch = rich_logs[0]["args"]["epoch"]
                output = rich_logs[0]["args"]["output"]
                logging.info(f"[{self.myid}] MPC OUTPUT[{epoch}] {output}")

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
                logging.info(f"[{self.myid}] MPC epoch initiated: {epoch}")
            else:
                logging.info(f"[{self.myid}] initiate_mpc failed (redundant?)")
            await asyncio.sleep(10)
