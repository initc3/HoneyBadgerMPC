import asyncio
import random

order = q = 17


def random_element():
    return random.randint(0, order)


def simple_router(N):
    """
    Builds a set of connected channels
    @return (receives, sends)
    """
    # Create a mailbox for each party
    mbox = [asyncio.Queue() for _ in range(N)]

    def makeSend(i):
        def _send(j, o):
            # print('SEND %8s [%2d -> %2d]' % (o[0], i, j))
            # random delay
            asyncio.get_event_loop().call_later(
                random.random()*1, mbox[j].put_nowait, (i, o))
        return _send

    def makeRecv(j):
        async def _recv():
            (i, o) = await mbox[j].get()
            # print('RECV %8s [%2d -> %2d]' % (o[0], i, j))
            return (i, o)
        return _recv

    sends = {}
    receives = {}
    for i in range(N):
        sends[i] = makeSend(i)
        receives[i] = makeRecv(i)
    return (sends, receives)


class Runtime():
    def __init__(self, id, N, t, send, recv):
        assert type(n) in (int, long)   # noqa TODO n is undefined
        assert 3 <= k <= n  # noqa TODO fix: k is undefined
        self.N = N
        self.t = t
        self.id = id

        asyncio.get_event_loop().create_task(self._run)

    async def _run(self):
        while True:
            await   # noqa TODO fix: await ?; e.g.: await asyncio.sleep(1)

    def createshare(self, val):
        s = Share(self)
        s._val = val
        return s

    def _send():
        pass


class Share():
    def __init__(self, runtime):
        pass

    async def open(self, _):
        # reveal share

        # wait for shares
        pass


async def progtest(N, myid, send, recv):
    print('myid:', myid)
    for j in range(N):
        send(j, 'hi from ' + str(myid))
    for _ in range(N):
        (i, o) = await recv()
        print('[%2d->%2d]' % (i, myid), o)
    print('done')


def test():
    N = 10

    async def _test():
        sends, recvs = simple_router(N)
        towait = []
        for i in range(N):
            towait.append(progtest(N, i, sends[i], recvs[i]))
        await asyncio.wait(towait)

    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    loop.run_until_complete(_test())
    loop.close()


if __name__ == '__main__':
    try:
        __IPYTHON__
    except NameError:
        test()
