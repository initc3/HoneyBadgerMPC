import asyncio
import logging
import subprocess
from contextlib import contextmanager
from pathlib import Path

from ethereum.tools._solidity import compile_code as compile_source

from web3 import HTTPProvider, Web3
from web3.contract import ConciseContract

from apps.masks.client import Client
from apps.masks.server import Server
from apps.utils import wait_for_receipt

from honeybadgermpc.preprocessing import PreProcessedElements
from honeybadgermpc.router import SimpleRouter


async def main_loop(w3, *, contract_name, contract_filepath):
    pp_elements = PreProcessedElements()
    # deletes sharedata/ if present
    pp_elements.clear_preprocessing()

    # Step 1.
    # Create the coordinator contract and web3 interface to it
    compiled_sol = compile_source(
        open(contract_filepath).read()
    )  # Compiled source code
    contract_interface = compiled_sol[f"<stdin>:{contract_name}"]
    contract_class = w3.eth.contract(
        abi=contract_interface["abi"], bytecode=contract_interface["bin"]
    )
    # tx_hash = contract_class.constructor(w3.eth.accounts[:7],2).transact(
    #   {'from':w3.eth.accounts[0]})  # n=7, t=2

    tx_hash = contract_class.constructor(w3.eth.accounts[:4], 1).transact(
        {"from": w3.eth.accounts[0]}
    )  # n=4, t=1

    # Get tx receipt to get contract address
    tx_receipt = await wait_for_receipt(w3, tx_hash)
    contract_address = tx_receipt["contractAddress"]

    if w3.eth.getCode(contract_address) == b"":
        logging.critical("code was empty 0x, constructor may have run out of gas")
        raise ValueError

    # Contract instance in concise mode
    abi = contract_interface["abi"]
    contract = w3.eth.contract(address=contract_address, abi=abi)
    contract_concise = ConciseContract(contract)

    # Call read only methods to check
    n = contract_concise.n()

    # Step 2: Create the servers
    router = SimpleRouter(n)
    sends, recvs = router.sends, router.recvs
    servers = [Server("sid", i, sends[i], recvs[i], w3, contract) for i in range(n)]

    # Step 3. Create the client
    # TODO communicate with server instead of fetching from list of servers
    async def req_mask(i, idx):
        # client requests input mask {idx} from server {i}
        return servers[i]._inputmasks[idx]

    client = Client("sid", "client", None, None, w3, contract, req_mask)

    # Step 4. Wait for conclusion
    for i, server in enumerate(servers):
        await server.join()
    await client.join()


@contextmanager
def run_and_terminate_process(*args, **kwargs):
    try:
        p = subprocess.Popen(*args, **kwargs)
        yield p
    finally:
        logging.info(f"Killing ganache-cli {p.pid}")
        p.terminate()  # send sigterm, or ...
        p.kill()  # send sigkill
        p.wait()
        logging.info("done")


def run_eth(*, contract_name, contract_filepath):
    w3 = Web3(HTTPProvider())  # Connect to localhost:8545
    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()

    try:
        logging.info("entering loop")
        loop.run_until_complete(
            asyncio.gather(
                main_loop(
                    w3, contract_name=contract_name, contract_filepath=contract_filepath
                )
            )
        )
    finally:
        logging.info("closing")
        loop.close()


def main(contract_name=None, contract_filepath=None):
    import time

    cmd = "ganache-cli -p 8545 -a 50 -b 1 > acctKeys.json 2>&1"
    logging.info(f"Running {cmd}")
    with run_and_terminate_process(cmd, shell=True):
        time.sleep(5)
        run_eth(contract_name=contract_name, contract_filepath=contract_filepath)


if __name__ == "__main__":
    # Launch an ethereum test chain
    contract_name = "MpcCoordinator"
    contract_filename = "contract.sol"
    contract_filepath = Path(__file__).resolve().parent.joinpath(contract_filename)
    main(contract_name=contract_name, contract_filepath=contract_filepath)
