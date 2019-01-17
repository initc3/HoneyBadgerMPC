import asyncio
import random
import logging
from .field import GF
from .polynomial import polynomialsOver, get_omega
from .elliptic_curve import Subgroup

# Fix the field for now
Field = GF.get(Subgroup.BLS12_381)
Poly = polynomialsOver(Field)

#######################################
# Batch Share Random using AVSS and ACS
#######################################
#
# Each party contributes B shares
# Use ACS as a synchronization point once at least N-f complete
# Let N' be the number of parties whose shares are included
# Let D be the nearest power of 2 >= N'B
# Interpolate a degree-(D-1) polynomial using D points, padding w/ zeros
# Interpolate the polynomial at D additional points
# Output (N'-f)B of the poins


class ShareRandom_Protocol(object):
    def __init__(self, B, N, f, sid, myid, AVSS, ACS):
        self.B = B  # batch size
        self.N = N
        self.f = f
        self.sid = sid
        self.myid = myid
        self.AVSS = AVSS
        self.ACS = ACS
        self.output = asyncio.Future()

        # Create B*N AVSSs, one for each party
        ssid = '(%s,%%d,%%d)' % (self.sid,)
        self._avss = [AVSS(ssid % (i, j), Dealer=i, myid=myid)
                      for i in range(N) for j in range(B)]

        logging.info(N)

        # Create one ACS
        self._acs = ACS(sid, myid=myid)

        async def _run():
            # Provide random input to my own AVSS
            for j in range(B):
                v = Field(random.randint(0, Field.modulus))
                self._avss[myid*B+j].inputFromDealer.set_result(v)

            # Wait to observe B of the AVSS for each of N-t parties complete
            pending = set([a.output for a in self._avss])
            ready = set()
            while True:
                done, pending = await asyncio.wait(pending,
                                                   return_when=asyncio.FIRST_COMPLETED)
                ready.update(done)
                vec = [all(a.output.done() for a in self._avss[i*B:(i+1)*B])
                       for i in range(N)]
                if sum(vec) >= N - f:
                    break

            # Then provide input to ACS
            logging.info(f'vec: {vec}')
            self._acs.input.set_result(vec)

            # Wait for ACS then proceed using the Rands indicated
            vecs = await self._acs.output

            # Which AVSS's are associated with f+1 values in the ACS?
            score = [0]*N
            for i in range(N):
                if vecs[i] is None:
                    continue
                for j in range(N):
                    if vecs[i][j]:
                        score[j] += 1
            logging.info(f'vecs with t+1 inputs: {score}')

            # Print statistics about how much output to expect
            def nearest_power_of_two(x): return 2**(x-1).bit_length()   # Round up
            valid = [score[i] >= f+1 for i in range(N)]
            logging.info(f"N': {sum(valid)}")
            logging.info(f"Parties B*N' {sum(valid)*B}")
            D = nearest_power_of_two(sum(valid)*B)
            logging.info(f"D (nearest pow-of-2, round up): {D}")
            logging.info(f"Recoverable: {(sum(valid)-f)*B}")

            # Wait for the appropriate AVSS to finish
            input_shares = []
            for i in range(N):
                if score[i] >= f+1:
                    _shares = [a.output for a in self._avss[i*B:(i+1)*B]]
                    input_shares += await asyncio.gather(*_shares)

            logging.info(f'input_shares: {len(input_shares)}')
            input_shares = input_shares + ([Field(0)] * (D-len(input_shares)))

            # Interpolate all the committed shares
            omega = get_omega(Field, 2*D, seed=0)
            outputs = Poly.interp_extrap(input_shares[:D], omega)
            output_shares = outputs[1:2*((sum(valid)-f)*B):2]   # Pick the odd shares
            logging.info(f'output_shares: {len(output_shares)}')

            self.output.set_result(output_shares)

        self._task = asyncio.ensure_future(_run())


# For testing use AVSS and ACS ideal protocols
from .secretshare_functionality import SecretShare_IdealProtocol    # noqa E402
from .commonsubset_functionality import CommonSubset_IdealProtocol  # noqa E402


async def _test_rand(sid='sid', N=4, f=1):
    SecretShare = SecretShare_IdealProtocol(N, f)
    CommonSubset = CommonSubset_IdealProtocol(N, f)

    B = 11
    rands = []
    # for i in range(N): # If set to N-1 (simulate crashed party, it gets stuck)
    for i in range(N):
        # Optionally fail to active the last one of them
        rands.append(ShareRandom_Protocol(B, N, f, sid, i, SecretShare, CommonSubset))

    logging.info('_test_rand: awaiting results...')
    results = await asyncio.gather(*(rand.output for rand in rands))

    # Check reconstructions are valid
    for i in range(len(results[0])):
        shares = [(j+1, r[i]) for j, r in enumerate(results)]
        t1 = Poly.interpolate_at(shares[:f+1])
        t2 = Poly.interpolate_at(shares[-(f+1):])
        assert t1 == t2

    logging.info('Done!')
    for a in SecretShare._instances.values():
        a._task.cancel()


def test_rand():
    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    loop.set_debug(True)
    try:
        loop.run_until_complete(_test_rand())
    finally:
        loop.close()


if __name__ == '__main__':
    test_rand()
