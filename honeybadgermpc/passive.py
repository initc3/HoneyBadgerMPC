import asyncio
from asyncio import Future
from .field import GF, GFElement
from .polynomial import polynomialsOver
from .router import simple_router
import random
from .robust_reconstruction import robust_reconstruct
from .batch_reconstruction import batch_reconstruct
from collections import defaultdict


class NotEnoughShares(Exception):
    pass


class BatchReconstructionFailed(Exception):
    pass


zeros_files_prefix = 'sharedata/test_zeros'
triples_files_prefix = 'sharedata/test_triples'
random_files_prefix = 'sharedata/test_random'


class PassiveMpc(object):

    def __init__(self, sid, N, t, myid, send, recv, prog):
        # Parameters for passive secure MPC
        # Note: tolerates min(t,N-t) crash faults
        assert type(N) is int and type(t) is int
        assert t < N
        self.sid = sid
        self.N = N
        self.t = t
        self.myid = myid

        # send(j, o): sends object o to party j with (current sid)
        # recv(): returns (j, o) from party j
        self.send = send
        self.recv = recv

        # An Mpc program should only depend on common parameters,
        # and the values of opened shares. Opened shares will be
        # assigned an ID based on the order that share is encountered.
        # So the protocol must encounter the shares in the same order.
        self.prog = prog

        # A task representing the opened values
        # { shareid => Future (field list(field)) }
        self._openings = {}

        # Store opened shares until ready to reconstruct
        # playerid => { [shareid => Future share] }
        self._share_buffers = tuple(defaultdict(asyncio.Future)
                                    for _ in range(N))

        # Batch reconstruction is handled slightly differently,
        # We'll create a separate queue for received values
        # { shareid => Queue() }
        self._sharearray_buffers = defaultdict(asyncio.Queue)

        self.Share, self.ShareArray = shareInContext(self)

        # Preprocessing elements
        filename = f'{zeros_files_prefix}-{self.myid}.share'
        self._zeros = iter(self.read_shares(open(filename)))

        filename = f'{random_files_prefix}-{self.myid}.share'
        self._rands = iter(self.read_shares(open(filename)))

        filename = f'{triples_files_prefix}-{self.myid}.share'
        self._triples = iter(self.read_shares(open(filename)))

    # Access to preprocessing data
    def get_triple(self):
        a = next(self._triples)
        b = next(self._triples)
        ab = next(self._triples)
        return a, b, ab

    def get_rand(self):
        return next(self._rands)

    def get_zero(self):
        return next(self._zeros)

    def get_bit(self):
        return next(self._bits)

    async def open_share(self, share):
        # Choose the shareid based on the order this is called
        shareid = len(self._openings)

        # Broadcast share
        for j in range(self.N):
            # 'S' is for single shares
            self.send(j, ('S', shareid, share.v))

        # Set up the buffer of received shares
        share_buffer = [self._share_buffers[i][shareid] for i in range(self.N)]

        def point(i): return Field(i+1)
        opening = robust_reconstruct(
            share_buffer, Field, self.N, self.t, point)
        self._openings[shareid] = opening
        P, failures = await opening
        return P(Field(0))

    async def open_share_array(self, sharearray):
        # Choose the shareid based on the order this is called
        shareid = len(self._openings)

        def _send(j, o):
            (tag, share) = o
            self.send(j, (tag, shareid, share))
        _recv = self._sharearray_buffers[shareid].get
        opening = batch_reconstruct([s.v for s in sharearray._shares],
                                    Field.modulus, self.t, self.N,
                                    self.myid, _send, _recv, debug=True)
        self._openings[shareid] = opening
        return await opening

    async def _run(self):
        # Run receive loop as background task, until self.prog finishes
        # Cancel the background task, even if there's an exception
        bgtask = asyncio.create_task(self._recvloop())
        result = asyncio.create_task(self.prog(self))
        await asyncio.wait((bgtask, result), return_when=asyncio.FIRST_COMPLETED)

        if result.done():
            bgtask.cancel()
            return result.result()
        else:
            print('bgtask exception:', bgtask.exception())
            raise bgtask.exception()
            bgtask.cancel()
            return await result

    async def _recvloop(self):
        while True:
            (j, (tag, shareid, share)) = await self.recv()

            # Sort into single or batch
            if tag == 'S':
                assert type(share) is GFElement, "?"
                buf = self._share_buffers[j]

                # Assert there is not an R1 or R2 value either
                assert shareid not in self._sharearray_buffers

                # Assert that there is not an element already
                assert not buf[shareid].done(
                ), "Received a redundant share: %o" % shareid
                buf[shareid].set_result(share)

            elif tag in ('R1', 'R2'):
                assert type(share) is list

                # Assert there is not an 'S' value here
                assert shareid not in self._share_buffers[j]

                # Forward to the right queue
                self._sharearray_buffers[shareid].put_nowait((j, (tag, share)))

        return True

    # File I/O
    def read_shares(self, f):
        # Read shares from a file object
        lines = iter(f)
        # first line: field modulus
        modulus = int(next(lines))
        assert Field.modulus == modulus
        # second line: share degree
        degree = int(next(lines))   # noqa
        # third line: id
        myid = int(next(lines))     # noqa
        shares = []
        # remaining lines: shared values
        for line in lines:
            shares.append(self.Share(int(line)))
        return shares

    def write_shares(self, f, shares):
        write_shares(f, Field.modulus, self.myid,
                     [share.v for share in shares])


def write_shares(f, modulus, degree, myid, shares):
    print(modulus, file=f)
    print(degree, file=f)
    print(myid, file=f)
    for share in shares:
        print(share.value, file=f)

###############
# Share class
###############


def shareInContext(context):

    def _binopField(fut, other, op):
        assert type(other) in [ShareFuture, GFElementFuture, Share, GFElement]
        if isinstance(other, ShareFuture) or isinstance(other, Share):
            res = ShareFuture()
        elif isinstance(other, GFElement) or isinstance(other, GFElementFuture):
            res = GFElementFuture()

        if isinstance(other, Future):
            def cb(_): return res.set_result(op(fut.result(), other.result()))
            asyncio.gather(fut, other).add_done_callback(cb)
        else:
            def cb(_): return res.set_result(op(fut.result(), other))
            fut.add_done_callback(cb)
        return res

    class GFElementFuture(Future):
        def __add__(self, other): return _binopField(
            self, other, lambda a, b: a + b)

        def __sub__(self, other): return _binopField(
            self, other, lambda a, b: a - b)

        def __mul__(self, other): return _binopField(
            self, other, lambda a, b: a * b)

    class Share(object):
        def __init__(self, v):
            # v is the local value of the share
            if type(v) is int:
                v = Field(v)
            assert type(v) is GFElement
            self.v = v

        # Publicly reconstruct a shared value
        def open(self):
            res = GFElementFuture()

            def cb(f): return res.set_result(f.result())
            opening = asyncio.ensure_future(context.open_share(self))
            # context._newopening.put_nowait(opening)
            opening.add_done_callback(cb)
            return res

        # Linear combinations of shares can be computed directly
        # TODO: add type checks for the operators
        # @typecheck(Share)
        def __add__(self, other):
            if isinstance(other, GFElement):
                return Share(self.v + other)
            elif isinstance(other, Share):
                return Share(self.v + other.v)

        def __sub__(self, other): return Share(self.v - other.v)
        __radd__ = __add__

        def __rsub__(self, other): return Share(-self.v + other.v)

        # @typecheck(int,field)
        def __rmul__(self, other): return Share(self.v * other)

        # @typecheck(Share)
        # TODO
        def __mul__(self, other): raise NotImplementedError

        def __str__(self): return '{%d}' % (self.v)

    def _binopShare(fut, other, op):
        assert type(other) in [ShareFuture, GFElementFuture, Share, GFElement]
        res = ShareFuture()
        if isinstance(other, Future):
            def cb(_): return res.set_result(op(fut.result(), other.result()))
            asyncio.gather(fut, other).add_done_callback(cb)
        else:
            def cb(_): return res.set_result(op(fut.result(), other))
            fut.add_done_callback(cb)
        return res

    class ShareFuture(Future):
        def __add__(self, other): return _binopShare(
            self, other, lambda a, b: a + b)

        def __sub__(self, other): return _binopShare(
            self, other, lambda a, b: a - b)

        def __mul__(self, other): return _binopShare(
            self, other, lambda a, b: a * b)

        def open(self):
            res = GFElementFuture()

            def cb2(sh): return res.set_result(sh.result())

            def cb1(_): return self.result().open().add_done_callback(cb2)
            self.add_done_callback(cb1)
            return res

    class ShareArray(object):
        def __init__(self, shares):
            # Initialized with a list of share objects
            for share in shares:
                assert type(share) is Share
            self._shares = shares

        def open(self):
            # TODO: make a list of GFElementFutures?
            # res = GFElementFuture()
            res = Future()

            def cb(f): return res.set_result(f.result())
            opening = asyncio.create_task(context.open_share_array(self))
            # context._newopening.put_nowait(opening)
            opening.add_done_callback(cb)
            return res

        def __add__(self, other): raise NotImplemented

        def __sub__(self, other):
            assert len(self._shares) == len(other._shares)
            return ShareArray([(a-b) for (a, b) in zip(self._shares, other._shares)])

    return Share, ShareArray


# Share = shareInContext(None)


# Create a fake network with N instances of the program
async def runProgramAsTasks(program, N, t):
    assert 2*t + 1 <= N  # Necessary for robust reconstruction
    sends, recvs = simple_router(N)

    tasks = []
    # bgtasks = []
    for i in range(N):
        context = PassiveMpc('sid', N, t, i, sends[i], recvs[i], program)
        tasks.append(asyncio.create_task(context._run()))

    try:
        results = await asyncio.gather(*tasks)
    finally:
        for t in tasks:
            t.cancel()
    return results


#######################
# Generating test files
#######################

# Fix the field for now
Field = GF.get(
    0x73eda753299d7d483339d80809a1d80553bda402fffe5bfeffffffff00000001)
Poly = polynomialsOver(Field)


def write_polys(prefix, modulus, N, t, polys):
    for i in range(N):
        shares = [f(i+1) for f in polys]
        with open('%s-%d.share' % (prefix, i), 'w') as f:
            write_shares(f, modulus, t, i, shares)


def generate_test_triples(prefix, k, N, t):
    # Generate k triples, store in files of form "prefix-%d.share"
    polys = []
    for j in range(k):
        a = Field(random.randint(0, Field.modulus-1))
        b = Field(random.randint(0, Field.modulus-1))
        c = a*b
        polys.append(Poly.random(t, a))
        polys.append(Poly.random(t, b))
        polys.append(Poly.random(t, c))
    write_polys(prefix, Field.modulus, N, t, polys)


def generate_test_zeros(prefix, k, N, t):
    polys = []
    for j in range(k):
        polys.append(Poly.random(t, 0))
    write_polys(prefix, Field.modulus, N, t, polys)


def generate_test_randoms(prefix, k, N, t):
    polys = []
    for j in range(k):
        polys.append(Poly.random(t))
    write_polys(prefix, Field.modulus, N, t, polys)


###############
# Test programs
###############

async def test_batchopening(context):

    # Demonstrates use of ShareArray batch interface
    xs = [context.get_zero() + context.Share(i) for i in range(100)]
    xs = context.ShareArray(xs)
    Xs = await xs.open()
    for i, x in enumerate(Xs):
        assert x.v == i
    print("[%d] Finished batch opening" % (context.myid,))


async def test_batchbeaver(context):

    # Demonstrates use of ShareArray batch interface
    xs = [context.get_zero() + context.Share(i) for i in range(100)]
    ys = [context.get_zero() + context.Share(i+10) for i in range(100)]
    xs = context.ShareArray(xs)
    ys = context.ShareArray(ys)

    As, Bs, ABs = [], [], []
    for i in range(100):
        A, B, AB = context.get_triple()
        As.append(A)
        Bs.append(B)
        ABs.append(AB)
    As = context.ShareArray(As)
    Bs = context.ShareArray(Bs)
    ABs = context.ShareArray(ABs)

    Ds = await (xs - As).open()
    Es = await (ys - Bs).open()

    for i, (x, y, a, b, ab, D, E) in enumerate(
            zip(xs._shares, ys._shares,
                As._shares, Bs._shares, ABs._shares, Ds, Es)):
        xy = context.Share(D*E) + D*b + E*a + ab
        assert (await xy.open()) == i * (i + 10)

    print("[%d] Finished batch beaver" % (context.myid,))


async def beaver_mult(context, x, y, a, b, ab):
    D = await (x - a).open()
    E = await (y - b).open()

    # This is a random share of x*y
    xy = context.Share(D*E) + D*b + E*a + ab

    return context.Share(await xy.open())


async def test_prog1(context):

    # Example of Beaver multiplication
    x = context.get_zero() + context.Share(10)
    # x = context.Share(10)
    y = context.get_zero() + context.Share(15)
    # y = context.Share(15)

    a, b, ab = context.get_triple()
    # assert await a.open() * await b.open() == await ab.open()

    D = (x - a).open()
    E = (y - b).open()
    await D
    await E

    # This is a random share of x*y
    print('type(D):', type(D))
    print('type(b):', type(b))
    xy = D*E + D*b + E*a + ab

    print('type(x):', type(x))
    print('type(y):', type(y))
    print('type(xy):', type(xy))
    X, Y, XY = await x.open(), await y.open(), await xy.open()
    assert X * Y == XY

    print("[%d] Finished" % (context.myid,), X, Y, XY)


async def test_prog2(context):

    shares = [context.get_zero() for _ in range(1000)]
    for share in shares[:100]:
        s = await share.open()
        assert s == 0
    print('[%d] Finished' % (context.myid,))

    # Batch version
    arr = context.ShareArray(shares[:100])
    for s in await arr.open():
        assert s == 0, s
    print('[%d] Finished batch' % (context.myid,))


def handle_async_exception(loop, ctx):
    print('handle_async_exception:', ctx)


# Run some test cases
if __name__ == '__main__':
    print('Generating random shares of zero in sharedata/')
    generate_test_zeros('sharedata/test_zeros', 1000, 3, 1)
    print('Generating random shares in sharedata/')
    generate_test_randoms('sharedata/test_random', 1000, 3, 1)
    print('Generating random shares of triples in sharedata/')
    generate_test_triples('sharedata/test_triples', 1000, 3, 1)

    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    # loop.set_exception_handler(handle_async_exception)
    # loop.set_debug(True)
    try:
        print("Start")
        loop.run_until_complete(runProgramAsTasks(test_prog1, 3, 1))
        loop.run_until_complete(runProgramAsTasks(test_prog2, 3, 1))
        loop.run_until_complete(runProgramAsTasks(test_batchbeaver, 3, 1))
        loop.run_until_complete(runProgramAsTasks(test_batchopening, 3, 1))
    finally:
        loop.close()
