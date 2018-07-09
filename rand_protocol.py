import asyncio
import random

# For testing, use the Ideal Protocol for AVSS and ACS
from secretshare_functionality import SecretShare_IdealProtocol
from commonsubset_functionality import CommonSubset_IdealProtocol
from secretshare_functionality import Field


#########################
# Naive ShareRandom 
#########################

# (this is a counter example for a bad design!)

class NaiveShareRandomProtocol(object):
    def __init__(self, N, f, sid, myid, AVSS, ACS):
        self.N = N
        self.f = f
        self.sid = sid
        self.myid = myid
        self.AVSS = AVSS
        self.ACS = ACS
        self.output = asyncio.Future()

        ssid = '(%s,%%d)' % (self.sid,)
        # Follow an AVSS for each party
        self.avss = [AVSS(ssid%i, Dealer=i, myid=myid)
                     for i in range(N)]
        async def _run():
            # Provide random input to my own AVSS
            v = Field(random.randint(0,10000))
            self.avss[myid].inputFromDealer.set_result(v)

            # Wait for output from *every* AVSS (this is the problem)
            results = await asyncio.gather(*(self.avss[i].output for i in range(N)))
            output = sum(results)

            # Return results
            self.output.set_result(output)

        self._task = asyncio.ensure_future(_run())

async def _test_naive(sid='sid',N=4,f=1):
    SecretShare = SecretShare_IdealProtocol(N,f)
    rands = []
    # for i in range(N): # If set to N-1 (simulate crashed party, it gets stuck)
    for i in range(N):
        # Optionally fail to active the last one of them
        rands.append(NaiveShareRandomProtocol(N,f,sid,i,SecretShare,None))

    print('_test_naive: awaiting results...')
    results = await asyncio.gather(*(rand.output for rand in rands))
    print('_test_naive:', results)
        
def test_naive():
    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    loop.set_debug(True)
    try: loop.run_until_complete(_test_naive())
    finally: loop.close()

#######################################
# Correct ShareRandom with AVSS and ACS
#######################################
class ShareSingle_Protocol(object):
    def __init__(self, N, f, sid, myid, AVSS, ACS):
        self.N = N
        self.f = f
        self.sid = sid
        self.myid = myid
        self.AVSS = AVSS
        self.ACS = ACS
        self.output = asyncio.Future()

        # Create an AVSS, one for each party
        ssid = '(%s,%%d)' % (self.sid,)
        self._avss = [AVSS(ssid%i, Dealer=i, myid=myid)
                      for i in range(N)]

        # Create one ACS
        self._acs = ACS(sid, myid=myid)

        async def _run():
            # Provide random input to my own AVSS
            v = Field(random.randint(0,10000))
            self._avss[myid].inputFromDealer.set_result(v)
    
            # Wait to observe N-t of the AVSS complete, then provide input to ACS
            pending = set([a.output for a in self._avss])
            ready = set()
            while len(ready) < N - f:
                done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                ready.update(done)

            # Then provide input to ACS
            vec = [True if a.output.done() else False
                   for i,a in enumerate(self._avss)]
            self._acs.input.set_result(vec)

            # Wait for ACS then proceed using the Rands indicated
            vecs = await self._acs.output

            # Which AVSS's are associated with f+1 values in the ACS?
            score = [0]*N
            for i in range(N):
                if vecs[i] is None: continue
                for j in range(N):
                    if vecs[i][j]: score[j] += 1
            print(score)

            # Add up the committed shares
            output = 0
            for i in range(N):
                if score[i] >= f+1:
                    output += await self._avss[i].output

            print('vecs with t+1 inputs:', score)
            print('Done')
            self.output.set_result(output)
            
        self._task = asyncio.ensure_future(_run())


async def _test_rand(sid='sid',N=4,f=1):
    SecretShare = SecretShare_IdealProtocol(N,f)
    CommonSubset = CommonSubset_IdealProtocol(N,f)

    rands = []
    # for i in range(N): # If set to N-1 (simulate crashed party, it gets stuck)
    for i in range(N-1):
        # Optionally fail to active the last one of them
        rands.append(ShareSingle_Protocol(N,f,sid,i,SecretShare,CommonSubset))

    print('_test_rand: awaiting results...')
    results = await asyncio.gather(*(rand.output for rand in rands))
    print('_test_rand:', results)
    for a in SecretShare._instances.values():
        a._task.cancel()
        
def test_rand():
    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    loop.set_debug(True)
    try: loop.run_until_complete(_test_rand())
    finally: loop.close()

if __name__ == '__main__':
    test_naive()
    test_rand()
