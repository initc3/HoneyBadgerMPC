"""MPC server code.

**Questions**
How are crash faults supposed to be handled? Currently, if a server comes
back it will be in an inconsistent state. For instance, its input masks list
will be empty, likely differing from the contract.

Also, the epoch count will be reset to 0 if a server restarts. Not clear
what this may cause, besides the server attempting to unmask messages that
have already been unmasked ...
"""
import asyncio
import logging
import pickle
from functools import partial
from pathlib import Path

import toml

from web3.contract import ConciseContract

from apps.toolkit.utils import fetch_contract, wait_for_receipt

from honeybadgermpc.elliptic_curve import Subgroup
from honeybadgermpc.field import GF
from honeybadgermpc.mpc import Mpc
from honeybadgermpc.utils.misc import (
    _get_send_recv,
    print_exception_callback,
    subscribe_recv,
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
        contract=None,
        contract_context=None,
        sharestore=None,
        channel=None,
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
        if not contract:
            self.contract = fetch_contract(w3, **contract_context)
        else:
            self.contract = contract
        self.w3 = w3
        self._init_tasks()
        if channel:
            self.get_send_recv = channel
        else:
            self._subscribe_task, subscribe = subscribe_recv(recv)
            self.get_send_recv = partial(_get_send_recv, send=send, subscribe=subscribe)
        self.sharestore = sharestore

    def _create_task(self, coro, *, name=None):
        task = asyncio.ensure_future(coro)
        task.add_done_callback(print_exception_callback)
        return task

    def _init_tasks(self):
        self._mpc = self._create_task(self._mpc_loop())
        self._mpc_init = self._create_task(self._mpc_initiate_loop())

    async def join(self):
        await self._mpc
        await self._mpc_init
        # await self._subscribe_task

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
            logging.info(f"masked_message_bytes: {masked_message_bytes}")
            logging.info(f"inputmask_idx: {inputmask_idx}")
            masked_message = field(int.from_bytes(masked_message_bytes, "big"))
            logging.info(f"masked_message: {masked_message}")
            try:
                _inputmasks = self.sharestore[b"inputmasks"]
            except KeyError:
                inputmasks = []
            else:
                inputmasks = pickle.loads(_inputmasks)
            try:
                inputmask = inputmasks[inputmask_idx]  # Get the input mask
            except IndexError:
                logging.error(f"No input mask at index {inputmask_idx}")
                raise
            msg_field_elem = masked_message - inputmask

            # 3.d. Call the MPC program
            async def prog(ctx):
                logging.info(f"[{ctx.myid}] Running MPC network")
                msg_share = ctx.Share(msg_field_elem)
                opened_value = await msg_share.open()
                opened_value_bytes = opened_value.value.to_bytes(32, "big")
                logging.info(f"opened_value in bytes: {opened_value_bytes}")
                msg = opened_value_bytes.decode().strip("\x00")
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
                logging.info(40 * "*")
                logging.info(f"[{self.myid}] MPC OUTPUT[{epoch}] {output}")
                logging.info(40 * "*")

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

    @classmethod
    def from_dict_config(cls, config, *, send, recv, sharestore=None):
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
        from apps.toolkit.utils import get_contract_address

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
            sharestore=sharestore,
        )

    @classmethod
    def from_toml_config(cls, config_path, *, send, recv, sharestore=None):
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
        return cls.from_dict_config(config, send=send, recv=recv, sharestore=sharestore)
