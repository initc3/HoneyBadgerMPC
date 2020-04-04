import argparse
import asyncio
import logging
from collections import namedtuple
from pathlib import Path

from aiohttp import ClientSession

from web3 import HTTPProvider, Web3
from web3.contract import ConciseContract

from apps.masks.config import CONTRACT_ADDRESS_FILEPATH
from apps.utils import fetch_contract, get_contract_address, wait_for_receipt

from honeybadgermpc.elliptic_curve import Subgroup
from honeybadgermpc.field import GF
from honeybadgermpc.polynomial import EvalPoint, polynomials_over
from honeybadgermpc.utils.misc import print_exception_callback

PARENT_DIR = Path(__file__).resolve().parent
field = GF(Subgroup.BLS12_381)
Server = namedtuple("Server", ("id", "host", "port"))


class Client:
    """An MPC client that sends "masked" messages to an Ethereum contract."""

    def __init__(self, sid, myid, w3, req_mask, *, contract_context, mpc_network):
        """
        Parameters
        ----------
        sid: int
            Session id.
        myid: int
            Client id.
        w3:
            Connection instance to an Ethereum node.
        req_mask:
            Function used to request an input mask from a server.
        contract_context: dict
            Contract attributes needed to interact with the contract
            using web3. Should contain the address, name and source code
            file path.
        mpc_network : list or tuple or set
            List or tuple or set of MPC servers, where each element is a
            dictionary of server attributes: "id", "host", and "port".
        """
        self.sid = sid
        self.myid = myid
        self._contract_context = contract_context
        self.contract = fetch_contract(w3, **contract_context)
        self.w3 = w3
        self.req_mask = req_mask
        self.mpc_network = [Server(**server_attrs) for server_attrs in mpc_network]
        self._task = asyncio.create_task(self._run())
        self._task.add_done_callback(print_exception_callback)

    @classmethod
    def from_config(cls, config):
        eth_config = config["eth"]

        # contract
        contract_context = {
            "address": get_contract_address(CONTRACT_ADDRESS_FILEPATH),
            "filepath": PARENT_DIR.joinpath(eth_config["contract_filename"]),
            "name": eth_config["contract_name"],
        }

        # web3
        eth_rpc_hostname = eth_config["rpc_host"]
        eth_rpc_port = eth_config["rpc_port"]
        w3_endpoint_uri = f"http://{eth_rpc_hostname}:{eth_rpc_port}"
        w3 = Web3(HTTPProvider(w3_endpoint_uri))

        # mpc network
        mpc_network = config["servers"]

        return cls(
            config["session_id"],
            config["id"],
            w3,
            None,  # TODO remove or pass callable for GET /inputmasks/{id}
            contract_context=contract_context,
            mpc_network=mpc_network,
        )

    async def _run(self):
        contract_concise = ConciseContract(self.contract)
        # Client sends several batches of messages then quits
        # for epoch in range(1000):
        for epoch in range(3):
            logging.info(f"[Client] Starting Epoch {epoch}")
            receipts = []
            m = f"Hello! (Epoch: {epoch})"
            task = asyncio.ensure_future(self.send_message(m))
            task.add_done_callback(print_exception_callback)
            receipts.append(task)
            receipts = await asyncio.gather(*receipts)

            while True:  # wait before sending next
                if contract_concise.outputs_ready() > epoch:
                    break
                await asyncio.sleep(5)

    async def _request_mask_share(self, server, mask_idx):
        logging.info(
            f"query server {server.host}:{server.port} "
            f"for its share of input mask with id {mask_idx}"
        )
        url = f"http://{server.host}:{server.port}/inputmasks/{mask_idx}"
        async with ClientSession() as session:
            async with session.get(url) as resp:
                json_response = await resp.json()
        return json_response["inputmask"]

    def _request_mask_shares(self, mpc_network, mask_idx):
        shares = []
        for server in mpc_network:
            share = self._request_mask_share(server, mask_idx)
            shares.append(share)
        return shares

    def _req_masks(self, server_ids, mask_idx):
        shares = []
        for server_id in server_ids:
            share = self.req_mask(server_id, mask_idx)
            shares.append(share)
        return shares

    async def _get_inputmask(self, idx):
        # Private reconstruct
        contract_concise = ConciseContract(self.contract)
        n = contract_concise.n()
        poly = polynomials_over(field)
        eval_point = EvalPoint(field, n, use_omega_powers=False)
        # shares = self._req_masks(range(n), idx)
        shares = self._request_mask_shares(self.mpc_network, idx)
        shares = await asyncio.gather(*shares)
        logging.info(
            f"{len(shares)} of input mask shares have"
            "been received from the MPC servers"
        )
        logging.info(
            "privately reconstruct the input mask from the received shares ..."
        )
        shares = [(eval_point(i), share) for i, share in enumerate(shares)]
        mask = poly.interpolate_at(shares, 0)
        return mask

    async def join(self):
        await self._task

    async def send_message(self, m):
        logging.info("sending message ...")
        # Submit a message to be unmasked
        contract_concise = ConciseContract(self.contract)

        # Step 1. Wait until there is input available, and enough triples
        while True:
            inputmasks_available = contract_concise.inputmasks_available()
            logging.info(f"inputmasks_available: {inputmasks_available}")
            if inputmasks_available >= 1:
                break
            await asyncio.sleep(5)

        # Step 2. Reserve the input mask
        logging.info("trying to reserve an input mask ...")
        tx_hash = self.contract.functions.reserve_inputmask().transact(
            {"from": self.w3.eth.accounts[0]}
        )
        tx_receipt = await wait_for_receipt(self.w3, tx_hash)
        rich_logs = self.contract.events.InputMaskClaimed().processReceipt(tx_receipt)
        if rich_logs:
            inputmask_idx = rich_logs[0]["args"]["inputmask_idx"]
        else:
            raise ValueError
        logging.info(f"input mask (id: {inputmask_idx}) reserved")
        logging.info(f"tx receipt hash is: {tx_receipt['transactionHash'].hex()}")

        # Step 3. Fetch the input mask from the servers
        logging.info("query the MPC servers for their share of the input mask ...")
        inputmask = await self._get_inputmask(inputmask_idx)
        logging.info("input mask has been privately reconstructed")
        message = int.from_bytes(m.encode(), "big")
        logging.info("masking the message ...")
        masked_message = message + inputmask
        masked_message_bytes = self.w3.toBytes(hexstr=hex(masked_message.value))
        masked_message_bytes = masked_message_bytes.rjust(32, b"\x00")

        # Step 4. Publish the masked input
        logging.info("publish the masked message to the public contract ...")
        tx_hash = self.contract.functions.submit_message(
            inputmask_idx, masked_message_bytes
        ).transact({"from": self.w3.eth.accounts[0]})
        tx_receipt = await wait_for_receipt(self.w3, tx_hash)
        logging.info(
            f"masked message has been published to the "
            f"public contract at address {self.contract.address}"
        )
        logging.info(f"tx receipt hash is: {tx_receipt['transactionHash'].hex()}")


async def main(config):
    client = Client.from_config(config)
    await client.join()


if __name__ == "__main__":
    import toml

    # arg parsing
    default_config_path = PARENT_DIR.joinpath("client.toml")
    parser = argparse.ArgumentParser(description="MPC client.")
    parser.add_argument(
        "-c",
        "--config-file",
        default=str(default_config_path),
        help=f"Configuration file to use. Defaults to '{default_config_path}'.",
    )
    args = parser.parse_args()
    config_file = args.config_file
    config = toml.load(config_file)
    print(config)

    # Launch a client
    asyncio.run(main(config))
