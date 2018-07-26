import asyncio
import random
from .field import GF
from .polynomial import polynomialsOver

"""
Ideal functionality for Asynchronous Verifiable Secret Sharing (AVSS or SecretShare)

The functionality definition for AVSS is very simple:
- One party, the Dealer, may optionally provide input
- If input is provided, then it is guaranteed to eventually arrive at each node

This module also defines an Ideal Protocol. The Ideal Protocol matches the interface of AVSS protocol construction, meaning that there is an instance created for each party. However, the instances of Ideal Protocol (with the same `sid`) all share a singleton Functionality.
"""

# Fix the field for now
Field = GF(0x73eda753299d7d483339d80809a1d80553bda402fffe5bfeffffffff00000001)
Poly = polynomialsOver(Field)

class SecretShare_Functionality(object):
    def __init__(self, sid, N, f, inputFromDealer=None):
        self.sid = sid
        self.N = N
        self.f = f
        if inputFromDealer is None: inputFromDealer = asyncio.Future()
        self.inputFromDealer = inputFromDealer
        self.outputs = [asyncio.Future() for _ in range(N)]

        # Create output promises, even though we don't have input yet
        self._task = asyncio.ensure_future(self._run())

    async def _run(self):
        v = await self.inputFromDealer
        # TODO: allow v to be arbitrary strings, or a parameter?
        assert type(v) is Field
        poly = Poly.random(self.f, y0=v)
        for i in range(self.N):
            # TODO: this needs to be made into an "eventually send"
            # TODO: the adversary should be able to choose the polynomial,
            #       as long as it is the correct degree and v0
            share = poly(i+1)
            await asyncio.sleep(random.random()*0.5)
            self.outputs[i].set_result(share)

def SecretShare_IdealProtocol(N, f):
    class SecretShare_IdealProtocol(object):
        _instances = {} # mapping from (sid,myid) to functionality shared state
    
        def __init__(self, sid, Dealer, myid):
            self.sid = sid
            self.Dealer = Dealer
            # Create the ideal functionality if not already present
            if sid not in SecretShare_IdealProtocol._instances:
                SecretShare_IdealProtocol._instances[sid] = \
                SecretShare_Functionality(sid,N,f,inputFromDealer=asyncio.Future())
            F_SecretShare = SecretShare_IdealProtocol._instances[sid]

            # If dealer, then provide input
            if myid == Dealer: self.inputFromDealer = F_SecretShare.inputFromDealer
            else: self.inputFromDealer = None

            # A future representing the output is available
            self.output = F_SecretShare.outputs[myid]
    return SecretShare_IdealProtocol

async def test1(sid='sid', N=4, f=1, Dealer=0):
    # Create ideal protocol for all the parties
    SecretShare = SecretShare_IdealProtocol(N,f)
    parties = [SecretShare(sid,Dealer,i) for i in range(N)]

    # Output (promises) are available, but not resolved yet
    for i in range(N):
        print(i, parties[i].output)

    # Show the shared functionality
    print(parties[0]._instances[sid])

    # Provide input
    v = Field(random.randint(0,Field.modulus-1))
    print("Dealer's input:", v)
    parties[Dealer].inputFromDealer.set_result(v)

    # Now can await output from each AVSS protocol
    for i in range(N):
        await parties[i].output
        print(i, parties[i].output)

    # Reconstructed
    rec = Poly.interpolate_at([(i+1,parties[i].output.result()) for i in range(f+1)])
    print("Reconstruction:", rec)
        
if __name__ == '__main__':
    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    loop.set_debug(True)
    try:
        # Run some test cases
        loop.run_until_complete(test1())
    finally:
        loop.close()

