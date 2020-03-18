import asyncio
import logging

from web3.contract import ConciseContract

from apps.utils import wait_for_receipt

from honeybadgermpc.elliptic_curve import Subgroup
from honeybadgermpc.field import GF
from honeybadgermpc.polynomial import EvalPoint, polynomials_over
from honeybadgermpc.utils.misc import print_exception_callback

field = GF(Subgroup.BLS12_381)


class Client:
    """An MPC client that sends "masked" messages to an Ethereum contract."""

    def __init__(self, sid, myid, send, recv, w3, contract, req_mask):
        """
        Parameters
        ----------
        sid: int
            Session id.
        myid: int
            Client id.
        send:
            Function used to send messages. Not used?
        recv:
            Function used to receive messages. Not used?
        w3:
            Connection instance to an Ethereum node.
        contract:
            Contract instance on the Ethereum blockchain.
        req_mask:
            Function used to request an input mask from a server.
        """
        self.sid = sid
        self.myid = myid
        self.contract = contract
        self.w3 = w3
        self.req_mask = req_mask
        self._task = asyncio.ensure_future(self._run())
        self._task.add_done_callback(print_exception_callback)

    async def _run(self):
        contract_concise = ConciseContract(self.contract)
        await asyncio.sleep(60)  # give the servers a head start
        # Client sends several batches of messages then quits
        for epoch in range(3):
            logging.info(f"[Client] Starting Epoch {epoch}")
            receipts = []
            m = f"Hello Shard! (Epoch: {epoch})"
            task = asyncio.ensure_future(self.send_message(m))
            task.add_done_callback(print_exception_callback)
            receipts.append(task)
            receipts = await asyncio.gather(*receipts)

            while True:  # wait before sending next
                # if contract_concise.intershard_msg_ready() > epoch:
                if contract_concise.outputs_ready() > epoch:
                    break
                await asyncio.sleep(5)

    async def _get_inputmask(self, idx):
        # Private reconstruct
        contract_concise = ConciseContract(self.contract)
        n = contract_concise.n()
        poly = polynomials_over(field)
        eval_point = EvalPoint(field, n, use_omega_powers=False)
        shares = []
        for i in range(n):
            share = self.req_mask(i, idx)
            shares.append(share)
        shares = await asyncio.gather(*shares)
        shares = [(eval_point(i), share) for i, share in enumerate(shares)]
        mask = poly.interpolate_at(shares, 0)
        return mask

    async def join(self):
        await self._task

    async def send_message(self, m):
        # Submit a message to be unmasked
        contract_concise = ConciseContract(self.contract)

        # Step 1. Wait until there is input available, and enough triples
        while True:
            inputmasks_available = contract_concise.inputmasks_available()
            # logging.infof'inputmasks_available: {inputmasks_available}')
            if inputmasks_available >= 1:
                break
            await asyncio.sleep(5)

        # Step 2. Reserve the input mask
        tx_hash = self.contract.functions.reserve_inputmask().transact(
            {"from": self.w3.eth.accounts[0]}
        )
        tx_receipt = await wait_for_receipt(self.w3, tx_hash)
        rich_logs = self.contract.events.InputMaskClaimed().processReceipt(tx_receipt)
        if rich_logs:
            inputmask_idx = rich_logs[0]["args"]["inputmask_idx"]
        else:
            raise ValueError

        # Step 3. Fetch the input mask from the servers
        inputmask = await self._get_inputmask(inputmask_idx)
        message = int.from_bytes(m.encode(), "big")
        masked_message = message + inputmask
        masked_message_bytes = self.w3.toBytes(hexstr=hex(masked_message.value))
        masked_message_bytes = masked_message_bytes.rjust(32, b"\x00")

        # Step 4. Publish the masked input
        tx_hash = self.contract.functions.submit_message(
            inputmask_idx, masked_message_bytes
        ).transact({"from": self.w3.eth.accounts[0]})
        tx_receipt = await wait_for_receipt(self.w3, tx_hash)
