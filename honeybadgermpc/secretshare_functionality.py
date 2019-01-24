import asyncio
import random
import logging
from .field import GF, GFElement
from .polynomial import polynomials_over
from .elliptic_curve import Subgroup

"""
Ideal functionality for Asynchronous Verifiable Secret Sharing (AVSS or SecretShare)

The functionality definition for AVSS is very simple:
- One party, the Dealer, may optionally provide input
- If input is provided, then it is guaranteed to eventually arrive at each node

This module also defines an Ideal Protocol. The Ideal Protocol matches the interface
of AVSS protocol construction, meaning that there is an instance created for each
party. However, the instances of Ideal Protocol (with the same `sid`) all share a
singleton Functionality.
"""

# Fix the field for now
Field = GF.get(Subgroup.BLS12_381)
Poly = polynomials_over(Field)


class SecretShareFunctionality(object):
    def __init__(self, sid, n, f, input_from_dealer=None):
        self.sid = sid
        self.N = n
        self.f = f
        if input_from_dealer is None:
            input_from_dealer = asyncio.Future()
        self.inputFromDealer = input_from_dealer
        self.outputs = [asyncio.Future() for _ in range(n)]

        # Create output promises, even though we don't have input yet
        self._task = asyncio.ensure_future(self._run())

    async def _run(self):
        v = await self.inputFromDealer
        # TODO: allow v to be arbitrary strings, or a parameter?
        assert type(v) is GFElement
        poly = Poly.random(self.f, y0=v)
        for i in range(self.N):
            # TODO: this needs to be made into an "eventually send"
            # TODO: the adversary should be able to choose the polynomial,
            #       as long as it is the correct degree and v0
            share = poly(i+1)
            await asyncio.sleep(random.random()*0.5)
            self.outputs[i].set_result(share)


def secret_share_ideal_protocol(n, f):
    class SecretShareIdealProtocol(object):
        _instances = {}     # mapping from (sid,myid) to functionality shared state

        def __init__(self, sid, dealer, myid):
            self.sid = sid
            self.Dealer = dealer
            # Create the ideal functionality if not already present
            if sid not in SecretShareIdealProtocol._instances:
                SecretShareIdealProtocol._instances[sid] = \
                    SecretShareFunctionality(
                        sid, n, f, input_from_dealer=asyncio.Future())
            func_secret_share = SecretShareIdealProtocol._instances[sid]

            # If dealer, then provide input
            if myid == dealer:
                self.inputFromDealer = func_secret_share.inputFromDealer
            else:
                self.inputFromDealer = None

            # A future representing the output is available
            self.output = func_secret_share.outputs[myid]
    return SecretShareIdealProtocol


async def test1(sid='sid', n=4, f=1, Dealer=0):
    # Create ideal protocol for all the parties
    SecretShare = secret_share_ideal_protocol(n, f)
    parties = [SecretShare(sid, Dealer, i) for i in range(n)]

    # Output (promises) are available, but not resolved yet
    for i in range(n):
        logging.info(f"{i} {parties[i].output}")

    # Show the shared functionality
    logging.info(parties[0]._instances[sid])

    # Provide input
    v = Field(random.randint(0, Field.modulus-1))
    logging.info(f"Dealer's input: {v}")
    parties[Dealer].inputFromDealer.set_result(v)

    # Now can await output from each AVSS protocol
    for i in range(n):
        await parties[i].output
        logging.info(f"{i} {parties[i].output}")

    # Reconstructed
    rec = Poly.interpolate_at([(i+1, parties[i].output.result()) for i in range(f+1)])
    logging.info(f"Reconstruction: {rec}")


if __name__ == '__main__':
    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    loop.set_debug(True)
    try:
        # Run some test cases
        loop.run_until_complete(test1())
    finally:
        loop.close()
