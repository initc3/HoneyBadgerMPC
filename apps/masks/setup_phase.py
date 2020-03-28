import logging
from pathlib import Path

from web3 import HTTPProvider, Web3

from apps.masks.config import CONTRACT_ADDRESS_FILEPATH
from apps.utils import create_and_deploy_contract

PARENT_DIR = Path(__file__).resolve().parent

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def deploy_contract(
    *, contract_name, contract_filepath, n=4, t=1, eth_rpc_hostname, eth_rpc_port
):
    w3_endpoint_uri = f"http://{eth_rpc_hostname}:{eth_rpc_port}"
    w3 = Web3(HTTPProvider(w3_endpoint_uri))
    deployer = w3.eth.accounts[49]
    mpc_addrs = w3.eth.accounts[:n]
    contract_address, abi = create_and_deploy_contract(
        w3,
        deployer=deployer,
        contract_name=contract_name,
        contract_filepath=contract_filepath,
        args=(mpc_addrs, t),
    )
    return contract_address


if __name__ == "__main__":
    # TODO figure out why logging does not show up in the output
    # NOTE appears to be a configuration issue with respect to the
    # level as `.warning()` works.
    logger.info(f"Deploying contract ...")
    print(f"Deploying contract ...")
    contract_name = "MpcCoordinator"
    contract_filename = "contract.sol"
    contract_filepath = PARENT_DIR.joinpath(contract_filename)
    eth_rpc_hostname = "blockchain"
    eth_rpc_port = 8545
    n, t = 4, 1
    contract_address = deploy_contract(
        contract_name=contract_name,
        contract_filepath=contract_filepath,
        t=1,
        eth_rpc_hostname=eth_rpc_hostname,
        eth_rpc_port=eth_rpc_port,
    )
    logger.info(f"Contract deployed at address: {contract_address}")
    print(f"Contract deployed at address: {contract_address}")
    with open(CONTRACT_ADDRESS_FILEPATH, "w") as f:
        f.write(contract_address)
    logger.info(f"Wrote contract address to file: {CONTRACT_ADDRESS_FILEPATH}")
    print(f"Wrote contract address to file: {CONTRACT_ADDRESS_FILEPATH}")
    import time

    time.sleep(10)
