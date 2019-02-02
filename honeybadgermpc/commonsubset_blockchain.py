"""
Implementation of Asynchronous Common Subset using an EVM blockchain
"""
import asyncio
from contextlib import contextmanager
import subprocess
import logging
from ethereum.tools._solidity import compile_code as compile_source
from web3.contract import ConciseContract


# TODO: compile solidity file commonsubset.sol

def common_subset_protocol(w3, contract, n, f):

    class CommonSubsetBlockchainProtocol(object):
        def __init__(self, sid, myid):
            self.sid = sid
            self.myid = myid
            # Accept one value as input (a uint256)
            self.input = asyncio.Future()
            # Output is a vecture of uint256
            self.output = asyncio.Future()

            self._task = asyncio.ensure_future(self._run())
            # TODO: use web3 to look up the contract using `sid` as the key
            # self._contract = ...

        async def _run(self):
            v = await self.input
            logging.info(
                '[%d] Invoking CommonSubset contract.input(%d)' % (self.myid, v))
            contract.input(v, transact={'from': w3.eth.accounts[self.myid]})

            # TODO: alternative to polling?
            while True:
                logging.info("[%d] deadline:%d, blockno:%d" % (
                    self.myid, contract.deadline(), w3.eth.blockNumber))
                if contract.isComplete():
                    break
                await asyncio.sleep(3)
            count = contract.count()    # noqa XXX count is unused
            outs = [contract.values(i) for i in range(n)]
            logging.info(f'CommonSubset output ready {contract.count()} {outs}')
            self.output.set_result(outs)

    return CommonSubsetBlockchainProtocol


def handle_event(event):
    # print('event:',event)
    # and whatever
    pass


async def main_loop(w3):
    # Compiled source code
    compiled_sol = compile_source(open('commonsubset.sol').read())
    contract_interface = compiled_sol['<stdin>:CommonSubset']
    contract = w3.eth.contract(abi=contract_interface['abi'],
                               bytecode=contract_interface['bin'])
    tx_hash = contract.constructor(
        w3.eth.accounts[:7], 2).transact({'from': w3.eth.accounts[0], 'gas': 820000})

    # tx_hash = contract.deploy(transaction={'from': w3.eth.accounts[0], 'gas': 410000})

    # Get tx receipt to get contract address
    while True:
        tx_receipt = w3.eth.getTransactionReceipt(tx_hash)
        if tx_receipt is not None:
            break
        await asyncio.sleep(1)
    contract_address = tx_receipt['contractAddress']

    # Contract instance in concise mode
    abi = contract_interface['abi']
    contract_instance = w3.eth.contract(
        address=contract_address, abi=abi, ContractFactoryClass=ConciseContract)

    logging.info(tx_receipt)
    logging.info(f'N {contract_instance.N()}')
    logging.info(f'f {contract_instance.f()}')
    logging.info(f'players(0) {contract_instance.players(0)}')
    logging.info(f'players(6) {contract_instance.players(6)}')
    # logging.info(f'players(7) {contract_instance.players(7)}')

    common_subset = common_subset_protocol(w3, contract_instance, 7, 2)
    prots = [common_subset('sid', i) for i in range(5)]
    outputs = [prot.output for prot in prots]
    for i, prot in enumerate(prots):
        prot.input.set_result(i+17)
    await asyncio.gather(*outputs)
    for prot in prots:
        prot._task.cancel()
    logging.info('done')


async def log_loop(event_filter, poll_interval):
    while True:
        for event in event_filter.get_new_entries():
            handle_event(event)
        await asyncio.sleep(poll_interval)


@contextmanager
def run_and_terminate_process(*args, **kwargs):
    try:
        p = subprocess.Popen(*args, **kwargs)
        yield p
    finally:
        logging.info(f"Killing ethereumjs-testrpc {p.pid}")
        p.terminate()   # send sigterm, or ...
        p.kill()      # send sigkill
        p.wait()
        logging.info('done')


def run_eth():
    from web3 import Web3, HTTPProvider
    w3 = Web3(HTTPProvider())   # Connect to localhost:8545
    block_filter = w3.eth.filter('latest')  # noqa XXX variable not used
    tx_filter = w3.eth.filter('pending')    # noqa XXX variable not used
    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    try:
        logging.info('entering loop')
        loop.run_until_complete(
            asyncio.gather(
                main_loop(w3),
                ))
    finally:
        logging.info('closing')
        loop.close()


def main():
    import time
    # with run_and_terminate_process(
    #   'testrpc -a 50 2>&1 | tee -a acctKeys.json', shell=True,
    #                   stdout=sys.stdout, stderr=sys.stderr) as proc:
    cmd = "testrpc -a 50 -b 1 > acctKeys.json 2>&1"
    logging.info(f"Running {cmd}")
    with run_and_terminate_process(cmd, shell=True) as proc:    # noqa XXX proc not used
        time.sleep(2)
        run_eth()


if __name__ == '__main__':
    # Launch an ethereum test chain
    main()
