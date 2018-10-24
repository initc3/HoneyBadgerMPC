from betterpairing import *
from PolyCommitNP import *
from helperfunctions import *
from HbAvssDealer import *
from HbAvssRecipient import *
from listrouter import *
import asyncio

def main():
    crs = [G1.rand(), G1.rand()]
    t = 2
    n = 3*t + 1
    participantids = list(range(1,n+1))
    dealerid = 0
    sid = 1
    (participantpubkeys, participantprivkeys) = ({}, {})
    for i in participantids:
        sk = ZR.rand()
        participantprivkeys[i] = sk
        participantpubkeys[i] = crs[0] ** sk
    pubparams = (t, n, crs, participantids, participantpubkeys, sid)
    
    async def _test():
        sends, recvs = simple_router(participantids + [dealerid])
        dealer = HbAvssDealer(pubparams, (42, dealerid), sends[dealerid], recvs[dealerid])
        threads = []
        #threads.append(HbAvssDealer(pubparams, (42, dealerid), sends[dealerid], recvs[dealerid]))
        recipients = []
        for i in participantids:
            recipients.append(HbAvssRecipient(pubparams, (i, participantprivkeys[i]), sends[i], recvs[i]))
        for r in recipients:
            threads.append(r.run())
        await asyncio.wait(threads)
        
    loop = asyncio.get_event_loop()
    loop.run_until_complete(_test())
    
    
    

if __name__ == "__main__":
    debug = True
    main()