from honeybadgermpc.betterpairing import G1, ZR
from honeybadgermpc.secretshare_hbavsslight import HbAvssDealer, HbAvssRecipient
from honeybadgermpc.router import simple_router
import asyncio
import cProfile


def main():
    # TODO: We need to generate the CRS once and hardcode it as a parameter
    crs = [G1.rand(), G1.rand()]
    t = 16
    n = 3*t + 1
    participantids = list(range(1, n+1))
    dealerid = 0
    sid = 1
    (participantpubkeys, participantprivkeys) = ({}, {})
    for i in participantids:
        sk = ZR.rand()
        participantprivkeys[i] = sk
        participantpubkeys[i] = crs[0] ** sk
    pubparams = (t, n, crs, participantids, participantpubkeys, dealerid, sid)

    async def _test():
        sends, recvs = simple_router(len(participantids) + 1)
        dealer = HbAvssDealer(pubparams, (42, dealerid),
                              sends[dealerid], recvs[dealerid])
        threads = [dealer.run()]
        recipients = []
        for i in participantids:
            recipients.append(HbAvssRecipient(
                pubparams, (i, participantprivkeys[i]), sends[i], recvs[i]))
        for r in recipients:
            threads.append(r.run())
        await asyncio.wait(threads)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(_test())


if __name__ == "__main__":
    debug = True
    # cProfile.run("main()")
    cProfile
    main()
