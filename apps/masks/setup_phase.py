import argparse
import logging
import pprint
from pathlib import Path

import toml

from web3 import HTTPProvider, Web3

from apps.masks.config import CONTRACT_ADDRESS_FILEPATH
from apps.utils import create_and_deploy_contract

PARENT_DIR = Path(__file__).resolve().parent

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def set_eth_addrs(config_dict, config_filepath):
    """Set eth addresses for the contract deployer, the MPC servers and
    the client and update the given config file.

    Parameters
    ----------
    config_dict : dict
        Configuration dict to update with eth addresses.
    config_filepath : str
        Toml file path to the configuration to update.
    """
    raise NotImplementedError


def deploy_contract(
    w3, *, contract_name, contract_filepath, n=4, t=1, deployer_addr, mpc_addrs
):
    contract_address, abi = create_and_deploy_contract(
        w3,
        deployer=deployer_addr,
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

    default_config_path = PARENT_DIR.joinpath("public-data/config.toml")
    parser = argparse.ArgumentParser(description="Setup phase.")
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

    n = config["n"]
    t = config["t"]
    eth_config = config["eth"]
    contract_name = eth_config["contract_name"]
    contract_filename = eth_config["contract_filename"]
    contract_filepath = PARENT_DIR.joinpath(contract_filename)
    eth_rpc_hostname = eth_config["rpc_host"]
    eth_rpc_port = eth_config["rpc_port"]
    w3_endpoint_uri = f"http://{eth_rpc_hostname}:{eth_rpc_port}"
    w3 = Web3(HTTPProvider(w3_endpoint_uri))

    deployer_addr = w3.eth.accounts[49]
    mpc_addrs = []
    for s in config["servers"]:
        mpc_addr = w3.eth.accounts[s["id"]]
        s["eth_address"] = mpc_addr
        mpc_addrs.append(mpc_addr)

    contract_address = deploy_contract(
        w3,
        contract_name=contract_name,
        contract_filepath=contract_filepath,
        n=n,
        t=t,
        deployer_addr=deployer_addr,
        mpc_addrs=mpc_addrs,
    )
    config["deployer_address"] = deployer_addr
    config["eth"]["contract_address"] = contract_address
    logger.info(f"Contract deployed at address: {contract_address}")
    print(f"Contract deployed at address: {contract_address}")

    with open(config_file, "w") as f:
        toml.dump(config, f)
    with open(CONTRACT_ADDRESS_FILEPATH, "w") as f:
        f.write(contract_address)

    logger.info(f"Wrote contract address to file: {CONTRACT_ADDRESS_FILEPATH}")
    print(f"Wrote contract address to file: {CONTRACT_ADDRESS_FILEPATH}")
    print(f"\nUpdated common config file: {config_file}\n")
    pprint.pprint(config)
