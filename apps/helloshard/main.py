import asyncio
import logging
import subprocess
from contextlib import contextmanager
from pathlib import Path

from ethereum.tools._solidity import compile_code as compile_source

from web3 import HTTPProvider, Web3
from web3.contract import ConciseContract

from apps.helloshard.client import Client
from apps.helloshard.server import Server
from apps.utils import wait_for_receipt

from honeybadgermpc.preprocessing import PreProcessedElements
from honeybadgermpc.router import SimpleRouter


async def main_loop(w3, *, contract_name, contract_filepath):
    # system config parameters
    n = 4
    t = 1
    k = 1000  # number of intershard masks to generate
    pp_elements = PreProcessedElements()
    # deletes sharedata/ if present
    pp_elements.clear_preprocessing()
    pp_elements.generate_intershard_masks(k, n, t, shard_1_id=0, shard_2_id=1)
    intershard_masks = pp_elements._intershard_masks

    # Step 1.
    # Create the coordinator contract and web3 interface to it
    compiled_sol = compile_source(
        open(contract_filepath).read()
    )  # Compiled source code
    contract_interface = compiled_sol[f"<stdin>:{contract_name}"]
    contract_class = w3.eth.contract(
        abi=contract_interface["abi"], bytecode=contract_interface["bin"]
    )

    # 2 shards: n=4, t=1 for each shard
    shard_1_accounts = w3.eth.accounts[:4]
    shard_2_accounts = w3.eth.accounts[4:8]
    tx_hash = contract_class.constructor(
        shard_1_accounts, shard_2_accounts, 1
    ).transact({"from": w3.eth.accounts[0]})

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

    # Call read only methods to check, and check that n in contract is as expected
    assert contract_concise.n() == n

    # Step 2: Create the servers
    servers = []
    for shard_id in (0, 1):
        is_gateway_shard = True if shard_id == 0 else False
        router = SimpleRouter(n)
        sends, recvs = router.sends, router.recvs
        for i in range(n):
            servers.append(
                Server(
                    "sid",
                    i,
                    sends[i],
                    recvs[i],
                    w3,
                    contract,
                    shard_id=shard_id,
                    intershardmask_shares=intershard_masks.cache[
                        (f"{i}-{shard_id}", n, t)
                    ],
                    is_gateway_shard=is_gateway_shard,
                )
            )

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


def test_asynchromix(contract_name=None, contract_filepath=None):
    import time

    # cmd = 'testrpc -a 50 2>&1 | tee -a acctKeys.json'
    # with run_and_terminate_process(cmd, shell=True,
    # stdout=sys.stdout, stderr=sys.stderr) as proc:
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
    test_asynchromix(contract_name=contract_name, contract_filepath=contract_filepath)
