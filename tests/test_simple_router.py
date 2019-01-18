import asyncio

from pytest import mark


async def progtest(n, myid, send, recv):
    print('myid:', myid)
    my_mailbox = []
    for j in range(n):
        send(j, 'hi from ' + str(myid))
    for _ in range(n):
        (i, o) = await recv()
        print('[%2d->%2d]' % (i, myid), o)
        my_mailbox.append((i, o))
    print('done')
    return my_mailbox


@mark.asyncio
async def test_simple_router(simple_router):
    N = 10
    sends, recvs = simple_router(N)
    towait = []
    for i in range(N):
        towait.append(progtest(N, i, sends[i], recvs[i]))
    done, pending = await asyncio.wait(towait)
    assert not pending
    assert len(done) == N
    assert all([(i, f'hi from {i}') in task.result() for task in done])
