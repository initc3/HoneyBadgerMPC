"""Volume Matching Auction : buy and sell orders are matched only on volume while price is determined by reference to some external market."""

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

# from apps.utils import wait_for_receipt

from honeybadgermpc.preprocessing import PreProcessedElements
from honeybadgermpc.router import SimpleRouter


def compile_contract_source(filepath):
    """Compiles the contract located in given file path.

    filepath : str
        File path to the contract.
    """
    with open(filepath, "r") as f:
        source = f.read()
    return compile_source(source)


def deploy_contract(w3, *, abi, bytecode, deployer, args=(), kwargs=None):
    """Deploy the contract.

    Parameters
    ----------
    w3 :
        Web3-based connection to an Ethereum network.
    abi :
        ABI of the contract to deploy.
    bytecode :
        Bytecode of the contract to deploy.
    deployer : str
        Ethereum address of the deployer. The deployer is the one
        making the transaction to deploy the contract, meaning that
        the costs of the transaction to deploy the contract are consumed
        from the ``deployer`` address.
    args : tuple, optional
        Positional arguments to be passed to the contract constructor.
        Defaults to ``()``.
    kwargs : dict, optional
        Keyword arguments to be passed to the contract constructor.
        Defaults to ``{}``.

    Returns
    -------
    contract_address: str
        Contract address in hexadecimal format.

    Raises
    ------
    ValueError
        If the contract deployment failed.
    """
    if kwargs is None:
        kwargs = {}
    contract_class = w3.eth.contract(abi=abi, bytecode=bytecode)
    tx_hash = contract_class.constructor(*args, **kwargs).transact({"from": deployer})

    # Get tx receipt to get contract address
    tx_receipt = w3.eth.waitForTransactionReceipt(tx_hash)
    contract_address = tx_receipt["contractAddress"]

    if w3.eth.getCode(contract_address) == b"":
        err_msg = "code was empty 0x, constructor may have run out of gas"
        logging.critical(err_msg)
        raise ValueError(err_msg)
    return contract_address


def create_and_deploy_contract(
    w3, *, deployer, contract_name, contract_filepath, args=(), kwargs=None
):
    """Create and deploy the contract.

    Parameters
    ----------
    w3 :
        Web3-based connection to an Ethereum network.
    deployer : str
        Ethereum address of the deployer. The deployer is the one
        making the transaction to deploy the contract, meaning that
        the costs of the transaction to deploy the contract are consumed
        from the ``deployer`` address.
    contract_name : str
        Name of the contract to be created.
    contract_filepath : str
        Path of the Solidity contract file.
    args : tuple, optional
        Positional arguments to be passed to the contract constructor.
        Defaults to ``()``.
    kwargs : dict, optional
        Keyword arguments to be passed to the contract constructor.
        Defaults to ``None``.

    Returns
    -------
    contract_address: str
        Contract address in hexadecimal format.
    abi:
        Contract abi.
    """
    compiled_sol = compile_contract_source(contract_filepath)
    contract_interface = compiled_sol[f"<stdin>:{contract_name}"]
    abi = contract_interface["abi"]
    contract_address = deploy_contract(
        w3,
        abi=abi,
        bytecode=contract_interface["bin"],
        deployer=deployer,
        args=args,
        kwargs=kwargs,
    )
    return contract_address, abi


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


def run_eth(*, contract_name, contract_filepath, n=4, t=1):
    w3 = Web3(HTTPProvider())  # Connect to localhost:8545
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


def main(contract_name=None, contract_filepath=None, n=4, t=1):
    import time

    cmd = "ganache-cli -p 8545 --accounts 50 --blockTime 1 > acctKeys.json 2>&1"
    logging.info(f"Running {cmd}")
    with run_and_terminate_process(cmd, shell=True):
        time.sleep(5)
        run_eth(
            contract_name=contract_name, contract_filepath=contract_filepath, n=n, t=t
        )


if __name__ == "__main__":
    # Launch an ethereum test chain
    contract_name = "MpcCoordinator"
    contract_filename = "contract.sol"
    contract_filepath = Path(__file__).resolve().parent.joinpath(contract_filename)
    n, t = 4, 1
    main(contract_name=contract_name, contract_filepath=contract_filepath, n=4, t=1)
