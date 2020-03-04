import asyncio
import logging

from ethereum.tools._solidity import compile_code as compile_solidity
from ratl import RatelCompiler
from vyper.compiler import compile_code as compile_vyper

from web3 import HTTPProvider, Web3
from web3.exceptions import TransactionNotFound

SOLIDITY_LANG = "solidity"
RATEL_LANG = "ratel"
VYPER_LANG = "vyper"


def compile_ratel(
    contract_source, *, vyper_output_formats=("abi", "bytecode"), **kwargs
):
    compiler = RatelCompiler()
    return compiler.compile(
        contract_source, vyper_output_formats=vyper_output_formats, **kwargs
    )


compilers = {
    RATEL_LANG: compile_ratel,
    SOLIDITY_LANG: compile_solidity,
    VYPER_LANG: compile_vyper,
}


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


def compile_contract_source(filepath, *, lang, **kwargs):
    """Compiles the contract located in given file path.

    filepath : str
        File path to the contract.
    """
    with open(filepath, "r") as f:
        source = f.read()

    return compilers[lang](source, **kwargs)


def get_contract_interface(*, contract_name, contract_filepath):
    compiled_sol = compile_contract_source(contract_filepath, lang="solidity")
    try:
        contract_interface = compiled_sol[f"<stdin>:{contract_name}"]
    except KeyError:
        logging.error(f"Contract {contract_name} not found")
        raise

    return contract_interface


def get_contract_abi(*, contract_name, contract_filepath, lang, **kwargs):
    if lang == "solidity":
        ci = get_contract_interface(
            contract_name=contract_name, contract_filepath=contract_filepath
        )
        return ci["abi"]
    elif lang == VYPER_LANG:
        if "output_formats" not in kwargs:
            kwargs["output_formats"] = ("abi",)
        output = compile_contract_source(contract_filepath, lang=lang, **kwargs)
        return output["abi"]
    elif lang == RATEL_LANG:
        if "vyper_output_formats" not in kwargs:
            kwargs["vyper_output_formats"] = ("abi",)
        output = compile_contract_source(contract_filepath, lang=lang, **kwargs)
        return output["vyper"]["abi"]


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
    w3,
    *,
    deployer,
    contract_name,
    contract_filepath,
    contract_lang,
    compiler_kwargs=None,
    args=(),
    kwargs=None,
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
    contract_lang: str
        Language of the contract. Must be 'vyper' or 'solidity'.
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
    if compiler_kwargs is None:
        compiler_kwargs = {}
    compiled_code_output = compile_contract_source(
        contract_filepath, lang=contract_lang, **compiler_kwargs
    )
    # TODO simplify
    if contract_lang == SOLIDITY_LANG:
        contract_interface = compiled_code_output[f"<stdin>:{contract_name}"]
        abi = contract_interface["abi"]
        bytecode = contract_interface["bin"]
    elif contract_lang == VYPER_LANG:
        abi = compiled_code_output["abi"]
        bytecode = compiled_code_output["bytecode"]
    elif contract_lang == RATEL_LANG:
        abi = compiled_code_output["vyper"]["abi"]
        bytecode = compiled_code_output["vyper"]["bytecode"]

    contract_address = deploy_contract(
        w3, abi=abi, bytecode=bytecode, deployer=deployer, args=args, kwargs=kwargs,
    )

    return contract_address, abi


def get_contract_address(filepath):
    with open(filepath, "r") as f:
        line = f.readline()
    contract_address = line.strip()
    return contract_address


def fetch_contract(w3, *, address, abi=None, name=None, filepath=None, lang="vyper"):
    """Fetch a contract using the given web3 connection, and contract
    attributes.

    Parameters
    ----------
    address : str
        Ethereum address of the contract.
    abi: dict (optional)
        Contract ABI. Must be supplied if ``filepath`` is not provided.
    name : str (optional)
        Name of the contract. Must be provided if ``abi`` is not provided
        and if ``lang`` is "solidity".
    filepath : str (optional)
        File path to the source code of the contract. Must be supplied if ``abi``
        is not provided.
    lang: str
        Language of the contract. Must be 'vyper' or 'solidity'.
        Defaults to 'vyper'.

    Returns
    -------
    web3.contract.Contract
        The ``web3`` ``Contract`` object.
    """
    if not abi:
        abi = get_contract_abi(
            contract_name=name, contract_filepath=filepath, lang=lang
        )
    contract = w3.eth.contract(address=address, abi=abi)
    return contract


def compile_ratel_contract(filepath, *, vyper_output_formats=("abi", "bytecode")):
    with open(filepath) as f:
        contract_code = f.read()
    ratel_compiler = RatelCompiler()
    return ratel_compiler.compile(
        contract_code, vyper_output_formats=vyper_output_formats
    )


def _get_contract_context(eth_config, contract_address_filepath):
    context = {
        "address": get_contract_address(contract_address_filepath),
        "filepath": eth_config["contract_path"],
        "name": eth_config["contract_name"],
    }
    return context


def _create_w3(eth_config):
    eth_rpc_hostname = eth_config["rpc_host"]
    eth_rpc_port = eth_config["rpc_port"]
    w3_endpoint_uri = f"http://{eth_rpc_hostname}:{eth_rpc_port}"
    return Web3(HTTPProvider(w3_endpoint_uri))
