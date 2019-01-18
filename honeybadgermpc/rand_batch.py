import asyncio
import random
import logging
from .field import GF
from .polynomial import polynomials_over, get_omega
from .elliptic_curve import Subgroup

# Fix the field for now
Field = GF.get(Subgroup.BLS12_381)
Poly = polynomials_over(Field)

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


class ShareRandomProtocol(object):
    def __init__(self, b, n, f, sid, myid, avss, acs):
        self.B = b  # batch size
        self.N = n
        self.f = f
        self.sid = sid
        self.myid = myid
        self.AVSS = avss
        self.ACS = acs
        self.output = asyncio.Future()

        # Create B*N AVSSs, one for each party
        ssid = '(%s,%%d,%%d)' % (self.sid,)
        self._avss = [avss(ssid % (i, j), dealer=i, myid=myid)
                      for i in range(n) for j in range(b)]

        logging.info(n)

        # Create one ACS
        self._acs = acs(sid, myid=myid)

        async def _run():
            # Provide random input to my own AVSS
            for j in range(b):
                v = Field(random.randint(0, Field.modulus))
                self._avss[myid*b+j].inputFromDealer.set_result(v)

            # Wait to observe B of the AVSS for each of N-t parties complete
            pending = set([a.output for a in self._avss])
            ready = set()
            while True:
                done, pending = await asyncio.wait(pending,
                                                   return_when=asyncio.FIRST_COMPLETED)
                ready.update(done)
                vec = [all(a.output.done() for a in self._avss[i*b:(i+1)*b])
                       for i in range(n)]
                if sum(vec) >= n - f:
                    break

            # Then provide input to ACS
            logging.info(f'vec: {vec}')
            self._acs.input.set_result(vec)

            # Wait for ACS then proceed using the Rands indicated
            vecs = await self._acs.output

            # Which AVSS's are associated with f+1 values in the ACS?
            score = [0]*n
            for i in range(n):
                if vecs[i] is None:
                    continue
                for j in range(n):
                    if vecs[i][j]:
                        score[j] += 1
            logging.info(f'vecs with t+1 inputs: {score}')

            # Print statistics about how much output to expect
            def nearest_power_of_two(x): return 2**(x-1).bit_length()   # Round up
            valid = [score[i] >= f+1 for i in range(n)]
            logging.info(f"N': {sum(valid)}")
            logging.info(f"Parties B*N' {sum(valid)*b}")
            d = nearest_power_of_two(sum(valid)*b)
            logging.info(f"D (nearest pow-of-2, round up): {d}")
            logging.info(f"Recoverable: {(sum(valid)-f)*b}")

            # Wait for the appropriate AVSS to finish
            input_shares = []
            for i in range(n):
                if score[i] >= f+1:
                    _shares = [a.output for a in self._avss[i*b:(i+1)*b]]
                    input_shares += await asyncio.gather(*_shares)

            logging.info(f'input_shares: {len(input_shares)}')
            input_shares = input_shares + ([Field(0)] * (d-len(input_shares)))

            # Interpolate all the committed shares
            omega = get_omega(Field, 2*d, seed=0)
            outputs = Poly.interp_extrap(input_shares[:d], omega)
            output_shares = outputs[1:2*((sum(valid)-f)*b):2]   # Pick the odd shares
            logging.info(f'output_shares: {len(output_shares)}')

            self.output.set_result(output_shares)

        self._task = asyncio.ensure_future(_run())


# For testing use AVSS and ACS ideal protocols
from .secretshare_functionality import secret_share_ideal_protocol    # noqa E402
from .commonsubset_functionality import common_subset_ideal_protocol  # noqa E402


async def _test_rand(sid='sid', n=4, f=1):
    SecretShare = secret_share_ideal_protocol(n, f)
    CommonSubset = common_subset_ideal_protocol(n, f)

    B = 11
    rands = []
    # for i in range(N): # If set to N-1 (simulate crashed party, it gets stuck)
    for i in range(n):
        # Optionally fail to active the last one of them
        rands.append(ShareRandomProtocol(B, n, f, sid, i, SecretShare, CommonSubset))

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
