from pytest import mark
import pytest
import asyncio
from honeybadgermpc.batch_reconstruction import batch_reconstruct
from honeybadgermpc.router import simple_router


def handle_async_exception(loop, ctx):
    print('handle_async_exception:', ctx)
    pytest.fail("Exception in async task: {0}".format(ctx['exception']))


@mark.asyncio
async def test():
    N = 4
    p = 73
    t = 1

    # loop = asyncio.get_event_loop()
    # loop.set_exception_handler(handle_async_exception)

    # Test with simple case: n = 4, t =1
    # After AVSS, poly1 = x + 2, poly2 = 3x + 4, secret1 = 2, secret2 = 4
    # Hard code the shared secret value as input into batch_reconstruction function
    # The final constructed polynomial should be p = 4x + 2
    shared_secrets = [(3,  7),
                      (4, 10),
                      (5, 13),
                      (6, 16)]

    # Test 1: Correct decoding with all four points
    sends, recvs = simple_router(N)
    towait = []
    for i in range(N):
        ss = shared_secrets[i]
        towait.append(batch_reconstruct(ss, p, t, N, i,
                                        sends[i], recvs[i], True))
    results = await asyncio.gather(*towait)
    for r in results:
        assert r == [2, 4]

    # Test 2: Correct decoding with up to 1 error
    sends, recvs = simple_router(N)
    towait = []
    for i in range(N):
        ss = shared_secrets[i]
        if i == 2:
            ss = (0, 0)  # add an error
        towait.append(batch_reconstruct(ss, p, t, N, i,
                                        sends[i], recvs[i], False))
    results = await asyncio.gather(*towait)
    for r in results:
        assert r == [2, 4]

    # Test 3: If there is an error and one crashed node, it will time out
    sends, recvs = simple_router(N)
    towait = []
    for i in range(N):
        ss = shared_secrets[i]
        if i == 2:
            continue  # skip this node
        if i == 3:
            ss = (0, 0)  # add an error
        towait.append(batch_reconstruct(ss, p, t, N, i,
                                        sends[i], recvs[i], False))
    with pytest.raises(asyncio.TimeoutError):
        results = await asyncio.wait_for(asyncio.gather(*towait), timeout=1)


if __name__ == '__main__':
    try:
        __IPYTHON__
    except NameError:
        test()
