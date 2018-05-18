from acs_functionality import CommonSubset_Functionality
"""
Implementation of Asynchronous Common Subset using an EVM blockchain
"""

import web3

# TODO: compile solidity file commonsubset.sol

def CommonSubsetProtocol(chain, N, f):
    
    class CommonSubset_BlockchainProtocol(object):
        def __init__(self, sid, myid):
            # Accept one value as input (a uint256)
            self.input = Future()
            # Output is a vecture of uint256
            self.output = Future()

            self._task = asyncio.ensure_future(self._run())

            # TODO: use web3 to look up the contract using `sid` as the key
            # self._contract = ...

        async def _run(self):
            v = await self.input
            # Use web3 to send a transaction
            # TODO: self._contract.input(v)

    return CommonSubsetProtocol

class ACS_Functionality(object):
    def __init__(self, sid, N, f):
        self.sid = sid
        self.N = N
        self.f = f
        self.inputs = [asyncio.Future() for _ in range(N)]
        self.outputs = [asyncio.Future() for _ in range(N)]

