"""Volume Matching Auction : buy and sell orders are matched only on volume while price is determined by reference to some external market."""

import asyncio
import logging
import subprocess
from contextlib import contextmanager
from pathlib import Path

from web3 import HTTPProvider, Web3
from web3.contract import ConciseContract

from apps.masks.client import Client
from apps.masks.server import Server
from apps.utils import create_and_deploy_contract

from honeybadgermpc.preprocessing import PreProcessedElements
from honeybadgermpc.router import SimpleRouter


async def main_loop(w3, *, contract_address, abi):
    pp_elements = PreProcessedElements()
    # deletes sharedata/ if present
    pp_elements.clear_preprocessing()

    # Contract instance in concise mode
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


def run_eth(
    *, contract_name, contract_filepath, n=4, t=1, eth_rpc_hostname, eth_rpc_port,
):
    w3_endpoint_uri = f"http://{eth_rpc_hostname}:{eth_rpc_port}"
    w3 = Web3(HTTPProvider(w3_endpoint_uri))  # Connect to localhost:8545
    deployer = w3.eth.accounts[49]
    mpc_addrs = w3.eth.accounts[:n]
    contract_address, abi = create_and_deploy_contract(
        w3,
        deployer=deployer,
        contract_name=contract_name,
        contract_filepath=contract_filepath,
        args=(mpc_addrs, t),
    )

    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()

    try:
        logging.info("entering loop")
        loop.run_until_complete(
            asyncio.gather(main_loop(w3, contract_address=contract_address, abi=abi))
        )
    finally:
        logging.info("closing")
        loop.close()


def main(
    contract_name=None,
    contract_filepath=None,
    n=4,
    t=1,
    eth_rpc_hostname="localhost",
    eth_rpc_port=8545,
):
    import time

    # cmd = "ganache-cli -p 8545 --accounts 50 --blockTime 1 > acctKeys.json 2>&1"
    # logging.info(f"Running {cmd}")
    # with run_and_terminate_process(cmd, shell=True):
    time.sleep(5)
    run_eth(
        contract_name=contract_name,
        contract_filepath=contract_filepath,
        n=n,
        t=t,
        eth_rpc_hostname=eth_rpc_hostname,
        eth_rpc_port=eth_rpc_port,
    )


if __name__ == "__main__":
    # Launch an ethereum test chain
    contract_name = "MpcCoordinator"
    contract_filename = "contract.sol"
    contract_filepath = Path(__file__).resolve().parent.joinpath(contract_filename)
    n, t = 4, 1
    main(
        contract_name=contract_name,
        contract_filepath=contract_filepath,
        n=4,
        t=1,
        eth_rpc_hostname="ganache",
        eth_rpc_port=8545,
    )
