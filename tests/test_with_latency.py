import asyncio
import logging
from pytest import mark


def simple_router(n, latency=1.0):
    """
    Builds a set of connected channels
    @return (receives, sends)
    """
    # Create a mailbox for each party
    mbox = [asyncio.Queue() for _ in range(n)]

    def make_send(i):
        def _send(j, o):
            logging.debug('SEND %8s [%2d -> %2d]' % (o, i, j))
            asyncio.get_event_loop().call_later(latency, mbox[j].put_nowait,(i,o))
            # mbox[j].put_nowait((i, o))

        return _send

    def make_recv(j):
        async def _recv():
            (i, o) = await mbox[j].get()
            logging.debug('RECV %8s [%2d -> %2d]' % (o, i, j))
            return (i, o)

        return _recv

    sends = {}
    receives = {}
    for i in range(n):
        sends[i] = make_send(i)
        receives[i] = make_recv(i)
    return (sends, receives)


from honeybadgermpc.mpc import ProgramRunner, Mpc
class TaskProgramRunnerWithLatency(ProgramRunner):
    def __init__(self, n, t):
        self.N, self.t, self.pid = n, t, 0
        self.tasks = []
        self.loop = asyncio.get_event_loop()

    def add(self, program, **kwargs):
        sends, recvs = simple_router(self.N)
        for i in range(self.N):
            context = Mpc(
                'sid', self.N, self.t, i, self.pid, sends[i], recvs[i], program, **kwargs
            )
            self.tasks.append(self.loop.create_task(context._run()))
        self.pid += 1

    async def join(self):
        return await asyncio.gather(*self.tasks)


@mark.asyncio
@mark.usefixtures('zeros_shares_files', 'triples_shares_files')
async def test_operation_with_latency(zeros_files_prefix, triples_files_prefix):
    N, t = 3, 1
    x_secret, y_secret = 10, 15

    async def _prog(context):
        filename = f'{zeros_files_prefix}-{context.myid}.share'
        zeros = context.read_shares(open(filename))
        filename = f'{triples_files_prefix}-{context.myid}.share'
        triples = context.read_shares(open(filename))

        # Example of Beaver multiplication
        x = zeros[0] + context.Share(x_secret)
        y = zeros[1] + context.Share(y_secret)

        a, b, ab = triples[:3]
        # assert await a.open() * await b.open() == await ab.open()

        # Round 1
        D = (x - a).open()
        E = (y - b).open()

        # This is a random share of x*y
        xy = D*E + D*b + E*a + ab

        # X, Y, XY = await x.open(), await y.open(), await xy.open()
        # assert X * Y == XY

        # Round 2
        XY = await xy.open()
        #print("[%d] Finished" % (context.myid,), X, Y, XY)
        return XY

    import time
    start_time = time.time()
    # logging.info("Start time: %.2f" % start_time)
    programRunner = TaskProgramRunnerWithLatency(N, t)
    programRunner.add(_prog)
    results = await programRunner.join()
    logging.info("Elapsed time: %.2f" % (time.time() - start_time,))
    assert len(results) == N
    # assert all(res == x_secret * y_secret for res in results)