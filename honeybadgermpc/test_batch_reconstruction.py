import asyncio
import random
# from honeybadgermpc.wb_interpolate import decoding_message_with_none_elements
from honeybadgermpc.field import GF
from honeybadgermpc.polynomial import polynomialsOver
from honeybadgermpc.batch_reconstruction import batch_reconstruction

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
            await  asyncio.sleep(1) # noqa TODO fix: await ?; e.g.: await asyncio.sleep(1)

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


async def progtest(shared, N, myid, send, recv):
    print('myid:', myid)
    print(shared)
    Fp = GF(p)
    Poly = polynomialsOver(Fp)
    tmp_poly = Poly(shared)

    for i in range(N):
        send(i, [Fp(i+1), tmp_poly(Fp(i+1))])

    tmp_gathered_results = []
    for j in range(N):
        (i, o) = await recv()
        print('[%2d->%2d]' % (i, myid), o)
        tmp_gathered_results.append(o)
        print("haha")
        if j >= (2*t + 1):
            print("{} is in first interpolation".format(myid))
            # interpolate with error correction to get f(j,y)
            # Solved, P1 = decoding_message_with_none_elements(t, tmp_gathered_results, p)
            # if Solved:
            #     break

    print(tmp_gathered_results)
    print('done')


# async def batch_reconstruction(shared_secrets, p, t, n, myid, send, recv):
#     print("my id %d" % myid)
#     print(shared_secrets)
#     # construct the first polynomial f(x,i) = [S1]ti + [S2]ti x + … [St+1]ti xt
#     Fp = GF(p)
#     Poly = polynomialsOver(Fp)
#     tmp_poly = Poly(shared_secrets)

#     # Evaluate and send f(j,i) for each other participating party Pj
#     for i in range(n):
#         send(i, [Fp(myid+1), tmp_poly(Fp(i+1))])

#     # Interpolate the polynomial, but we don't need to wait for getting all the values, we can start with 2t+1 values
#     tmp_gathered_results = []
#     for j in range(n):
#         # TODO: can we assume that if received, the values are non-none?
#         (i, o) = await recv()
#         print("{} gets {} from {}".format(myid, o, i))
#         tmp_gathered_results.append(o)
#         if j >= (2*t + 1):
#             print("{} is in first interpolation".format(myid))
#             # print(tmp_gathered_results)
#             # interpolate with error correction to get f(j,y)
#             Solved, P1 = decoding_message_with_none_elements(t, tmp_gathered_results, p)
#             if Solved:
#                 break

#     # Evaluate and send f(j,y) for each other participating party Pj
#     for i in range(n):
#         send(i, [myid + 1, P1.coeffs[0]])

#     # Interpolate the polynomial to get f(x,0)
#     tmp_gathered_results2 = []
#     for j in range(n):
#         # TODO: can we assume that here the received values are non-none?
#         (i, o) = await recv()
#         print("{} gets {} from {}".format(myid, o, i))
#         tmp_gathered_results2.append(o)
#         if j >= (2*t + 1):
#             # interpolate with error correction to get f(x,0)
#             print("{} is in second interpolation".format(myid))
#             Solved, P2 = decoding_message_with_none_elements(t, tmp_gathered_results2, p)
#             if Solved:
#                 break

#     # return the result
#     if Solved:
#         return Solved, P2
#     else:
#         return Solved, None


def test():
    N = 4
    p = 73
    t = 1

    async def _test():
        # Test with simple case: n = 4, t =1
        # After AVSS, poly1 = x + 2, poly2 = 3x + 4, secret1 = 2, secret2 = 4
        # Hard code the shared secret value as input into batch_reconstruction function
        # The final constructed polynomial should be p = 4x + 2
        sends, recvs = simple_router(N)
        towait = []
        for i in range(N):
            if i == 0:
                shared_secrets = [3, 7]
            if i == 1:
                shared_secrets = [4, 10]
            if i == 2:
                shared_secrets = [5, 13]
            if i == 3:
                shared_secrets = [6, 16]
            towait.append(batch_reconstruction(shared_secrets, p, t, N, i, sends[i], recvs[i]))
        await asyncio.wait(towait)

    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    loop.run_until_complete(_test())
    loop.close()


def test_with_none_values():
    # test with corrupted or none values
    #
    return


if __name__ == '__main__':
    try:
        __IPYTHON__
    except NameError:
        test()
