import asyncio

from web3.exceptions import TransactionNotFound


async def wait_for_receipt(w3, tx_hash):
    while True:
        try:
            tx_receipt = w3.eth.getTransactionReceipt(tx_hash)
        except TransactionNotFound:
            tx_receipt = None
        if tx_receipt is not None:
            break
        await asyncio.sleep(5)
    return tx_receipt
