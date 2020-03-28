import asyncio
import logging

from ethereum.tools._solidity import compile_code as compile_source

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


def compile_contract_source(filepath):
    """Compiles the contract located in given file path.

    filepath : str
        File path to the contract.
    """
    with open(filepath, "r") as f:
        source = f.read()
    return compile_source(source)


def get_contract_interface(*, contract_name, contract_filepath):
    compiled_sol = compile_contract_source(contract_filepath)
    try:
        contract_interface = compiled_sol[f"<stdin>:{contract_name}"]
    except KeyError:
        logging.error(f"Contract {contract_name} not found")
        raise

    return contract_interface


def get_contract_abi(*, contract_name, contract_filepath):
    ci = get_contract_interface(
        contract_name=contract_name, contract_filepath=contract_filepath
    )
    return ci["abi"]


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


def get_contract_address(filepath):
    with open(filepath, "r") as f:
        line = f.readline()
    contract_address = line.strip()
    return contract_address


def fetch_contract(w3, *, address, name, filepath):
    """Fetch a contract using the given web3 connection, and contract
    attributes.

    Parameters
    ----------
    address : str
        Ethereum address of the contract.
    name : str
        Name of the contract.
    filepath : str
        File path to the source code of the contract.

    Returns
    -------
    web3.contract.Contract
        The ``web3`` ``Contract`` object.
    """
    abi = get_contract_abi(contract_name=name, contract_filepath=filepath)
    contract = w3.eth.contract(address=address, abi=abi)
    return contract
