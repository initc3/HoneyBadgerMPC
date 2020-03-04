import argparse
import logging
import pprint
from pathlib import Path

import toml

from web3 import HTTPProvider, Web3

from apps.sdk.utils import create_and_deploy_contract

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
    w3,
    *,
    contract_name,
    contract_filepath,
    contract_lang,
    compiler_kwargs=None,
    n=4,
    t=1,
    deployer_addr,
    mpc_addrs,
):
    contract_address, abi = create_and_deploy_contract(
        w3,
        deployer=deployer_addr,
        contract_name=contract_name,
        contract_filepath=contract_filepath,
        contract_lang=contract_lang,
        compiler_kwargs=compiler_kwargs,
        args=(mpc_addrs, t),
    )
    return contract_address


if __name__ == "__main__":
    # TODO figure out why logging does not show up in the output
    # NOTE appears to be a configuration issue with respect to the
    # level as `.warning()` works.
    logger.info("Deploying contract ...")
    print("Deploying contract ...")

    # default_config_path = PARENT_DIR.joinpath("public-data/config.toml")
    default_config_path = Path.home().joinpath(".coordinator/config.toml")
    parser = argparse.ArgumentParser(description="Setup phase.")
    parser.add_argument(
        "-c",
        "--config-file",
        default=str(default_config_path),
        help=f"Configuration file to use. Defaults to '{default_config_path}'.",
    )
    default_coordinator_home = Path.home().joinpath(".coordinator")
    parser.add_argument(
        "--coordinator-home",
        type=str,
        help=(
            "Home directory to store configurations, public and private data. "
            "If not provided, will fall back on value specified in config file. "
            f"If absent from config file will default to {default_coordinator_home}."
        ),
    )
    default_contract_address_path = default_coordinator_home.joinpath(
        "public/contract_address"
    )
    parser.add_argument(
        "--contract-address-path",
        type=str,
        help=(
            "File path to write the contract address to. If not provided, "
            " will fall back on value specified in config file. If absent "
            f"from config file will default to {default_contract_address_path}."
        ),
    )
    args = parser.parse_args()
    config_file = args.config_file
    config = toml.load(config_file)
    print(config)

    coordinator_home = args.coordinator_home or config.get(
        "home", default_coordinator_home
    )
    contract_address_path = args.contract_address_path or config["contract"].get(
        "address_path", default_contract_address_path
    )
    n = config["n"]
    t = config["t"]
    contract_name = config["contract"]["name"]
    contract_path = Path(config["contract"]["path"]).expanduser()
    contract_lang = config["contract"]["lang"]
    eth_rpc_hostname = config["eth"]["rpc_host"]
    eth_rpc_port = config["eth"]["rpc_port"]
    w3_endpoint_uri = f"http://{eth_rpc_hostname}:{eth_rpc_port}"
    w3 = Web3(HTTPProvider(w3_endpoint_uri))

    deployer_addr = w3.eth.accounts[49]
    mpc_addrs = []
    for s in config["peers"]:
        mpc_addr = w3.eth.accounts[s["id"]]
        s["eth_address"] = mpc_addr
        mpc_addrs.append(mpc_addr)

    if contract_lang == "vyper":
        compiler_kwargs = {"output_formats": ("abi", "bytecode")}
    else:
        compiler_kwargs = {}

    contract_address = deploy_contract(
        w3,
        contract_name=contract_name,
        contract_filepath=contract_path,
        contract_lang=contract_lang,
        compiler_kwargs=compiler_kwargs,
        n=n,
        t=t,
        deployer_addr=deployer_addr,
        mpc_addrs=mpc_addrs,
    )
    config["deployer_address"] = deployer_addr
    config["contract"]["address"] = contract_address
    logger.info(f"Contract deployed at address: {contract_address}")
    print(f"Contract deployed at address: {contract_address}")

    with open(config_file, "w") as f:
        toml.dump(config, f)
    with open(contract_address_path, "w") as f:
        f.write(contract_address)

    logger.info(f"Wrote contract address to file: {contract_address_path}")
    print(f"Wrote contract address to file: {contract_address_path}")
    print(f"\nUpdated common config file: {config_file}\n")
    pprint.pprint(config)
