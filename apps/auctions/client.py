import asyncio
import logging

# import random

from web3.contract import ConciseContract

from apps.toolkit.client import Client as _Client
from apps.toolkit.utils import wait_for_receipt

from honeybadgermpc.utils.misc import print_exception_callback


class Client(_Client):
    def _fake_bids(self):
        # return (random.randint(-10, 10) for _ in range(32))
        return range(32)

    async def _run(self):
        contract_concise = ConciseContract(self.contract)
        # Client sends several batches of messages then quits
        for epoch in range(self.number_of_epoch):
            logging.info(f"[Client] Starting Epoch {epoch} ...")
            receipts = []
            # for i in range(self.msg_batch_size):
            for i, bid in enumerate(self._fake_bids()):
                # sender_id = i + 10
                sender = self.w3.eth.accounts[self.myid]
                # sender = self.w3.eth.accounts[sender_id]
                # m = f"Bid from {sender_id}:{sender} at epoch: {epoch}:{i})"
                logging.info(f"sender: {sender}")
                logging.info(f"bid: {bid}")
                # m = f"<Epoch: {epoch}, Bid: {bid}, Sender: {sender_id}>"
                m = bid
                task = asyncio.ensure_future(self.send_message(m, sender=sender))
                task.add_done_callback(print_exception_callback)
                receipts.append(task)
            receipts = await asyncio.gather(*receipts)

            while True:  # wait before sending next
                if contract_concise.outputs_ready() > epoch:
                    break
                await asyncio.sleep(5)

    async def send_message(self, m, *, sender=None):
        logging.info("sending message ...")
        # Submit a message to be unmasked
        contract_concise = ConciseContract(self.contract)

        if sender is None:
            sender = self.w3.eth.accounts[self.myid]

        # Step 1. Wait until there is input available, and enough triples
        while True:
            inputmasks_available = contract_concise.inputmasks_available()
            logging.info(f"inputmasks_available: {inputmasks_available}")
            if inputmasks_available >= 1:
                break
            await asyncio.sleep(5)

        # Step 2. Reserve the input mask
        logging.info("trying to reserve an input mask ...")
        tx_hash = self.contract.functions.reserve_inputmask().transact({"from": sender})
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
        # message = int.from_bytes(m.encode(), "big")
        message = m
        logging.info("masking the message ... <SECRET> {m} <SECRET>")
        logging.info(f"... <SECRET> with input mask {inputmask} <SECRET> ...")
        logging.info(f"type of inputmask: {type(inputmask)} ...")
        masked_message = message + inputmask
        masked_message_bytes = self.w3.toBytes(hexstr=hex(masked_message.value))
        masked_message_bytes = masked_message_bytes.rjust(32, b"\x00")

        # Step 4. Publish the masked input
        logging.info("publish the masked message to the public contract ...")
        tx_hash = self.contract.functions.submit_message(
            inputmask_idx, masked_message_bytes
        ).transact({"from": sender})
        tx_receipt = await wait_for_receipt(self.w3, tx_hash)
        rich_logs = self.contract.events.MessageSubmitted().processReceipt(tx_receipt)
        if rich_logs:
            idx = rich_logs[0]["args"]["idx"]
            inputmask_idx = rich_logs[0]["args"]["inputmask_idx"]
            masked_input = rich_logs[0]["args"]["masked_input"]
        else:
            raise ValueError
        logging.info(
            f"masked message {masked_input} has been published to the "
            f"public contract at address {self.contract.address} "
            f"and is queued at index {idx}"
        )
        logging.info(f"tx receipt hash is: {tx_receipt['transactionHash'].hex()}")


async def main(config_file):
    client = Client.from_toml_config(config_file)
    await client.join()


if __name__ == "__main__":
    import argparse
    from pathlib import Path

    PARENT_DIR = Path(__file__).resolve().parent
    default_config_path = PARENT_DIR.joinpath("client.toml")
    # default_client_home = Path.home().joinpath(".hbmpc")
    # default_contract_address_path = default_client_home.joinpath(
    #    "public/contract_address"
    # )
    parser = argparse.ArgumentParser(description="MPC client.")
    parser.add_argument(
        "-c",
        "--config-file",
        default=str(default_config_path),
        help=f"Configuration file to use. Defaults to '{default_config_path}'.",
    )
    args = parser.parse_args()

    # Launch a client
    asyncio.run(main(Path(args.config_file).expanduser()))
