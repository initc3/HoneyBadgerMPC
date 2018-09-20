import asyncio
from asyncio import Future
from .field import GF
from .polynomial import polynomialsOver
from .router import simple_router
import random


class NotEnoughShares(Exception):
    pass


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

        # Store deferreds representing SharedValues
        self._openings = []

        # Store opened shares until ready to reconstruct
        # shareid => { [playerid => share] }
        self._share_buffers = tuple([] for _ in range(N))

        self.Share = shareInContext(self)

    def _reconstruct(self, shareid):
        # Are there enough shares to reconstruct?
        shares = [(i+1, self._share_buffers[i][shareid])
                  for i in range(self.N)
                  if len(self._share_buffers[i]) > shareid]
        if len(shares) < self.t+1:
            raise NotEnoughShares

        # print('[%d] reconstruct %s' % (self.myid, shareid,))

        if not self._openings[shareid].done():
            s = Poly.interpolate_at(shares)
            # Set the result on the future representing this share
            self._openings[shareid].set_result(s)

    def open_share(self, share):
        opening = asyncio.Future()
        shareid = len(self._openings)
        self._openings.append(opening)

        # Broadcast share
        for j in range(self.N):
            self.send(j, (shareid, share.v))

        # Reconstruct if we already had enough shares
        try:
            self._reconstruct(shareid)
        except NotEnoughShares:
            pass

        # Return future
        return opening

    async def _run(self):
        # Run receive loop as background task, until self.prog finishes
        loop = asyncio.get_event_loop()
        bgtask = loop.create_task(self._recvloop())

        def handle_result(future):
            if not future.cancelled() and future.exception():
                # Stop the loop otherwise the loop continues to await for the prog to
                # finish which will never happen since the recvloop has terminated.
                loop.stop()
                future.result()
        bgtask.add_done_callback(handle_result)
        res = await self.prog(self)
        bgtask.cancel()
        return res

    async def _recvloop(self):
        while True:
            (j, (shareid, share)) = await self.recv()
            buf = self._share_buffers[j]

            # Shareid is redundant, but confirm it is one greater
            assert shareid == len(buf)
            buf.append(share)

            # Reconstruct if we now have enough shares,
            # and if the opening has been asked for
            if len(self._openings) > shareid:
                try:
                    self._reconstruct(shareid)
                except NotEnoughShares:
                    pass

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
        assert type(other) in [ShareFuture, FieldFuture, Share, Field]
        if isinstance(other, ShareFuture) or isinstance(other, Share):
            res = ShareFuture()
        elif isinstance(other, Field) or isinstance(other, FieldFuture):
            res = FieldFuture()

        if isinstance(other, Future):
            def cb(_): return res.set_result(op(fut.result(), other.result()))
            asyncio.gather(fut, other).add_done_callback(cb)
        else:
            def cb(_): return res.set_result(op(fut.result(), other))
            fut.add_done_callback(cb)
        return res

    class FieldFuture(Future):
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
            assert type(v) is Field
            self.v = v

        # Publicly reconstruct a shared value
        def open(self):
            res = FieldFuture()

            def cb(f): return res.set_result(f.result())
            context.open_share(self).add_done_callback(cb)
            return res

        # Linear combinations of shares can be computed directly
        # TODO: add type checks for the operators
        # @typecheck(Share)
        def __add__(self, other):
            if isinstance(other, Field):
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
        def __mul__(self, other): raise NotImplemented

        def __str__(self): return '{%d}' % (self.v)

    def _binopShare(fut, other, op):
        assert type(other) in [ShareFuture, FieldFuture, Share, Field]
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

        def open(self) -> FieldFuture:
            res = FieldFuture()

            def cb2(sh): return res.set_result(sh.result())

            def cb1(_): return self.result().open().add_done_callback(cb2)
            self.add_done_callback(cb1)
            return res

    return Share

# Share = shareInContext(None)


# Create a fake network with N instances of the program
async def runProgramInNetwork(program, N, t):
    loop = asyncio.get_event_loop()
    sends, recvs = simple_router(N)

    tasks = []
    # bgtasks = []
    for i in range(N):
        context = PassiveMpc('sid', N, t, i, sends[i], recvs[i], program)
        tasks.append(loop.create_task(context._run()))

    results = await asyncio.gather(*tasks)
    return results

#######################
# Generating test files
#######################

# Fix the field for now
Field = GF(0x73eda753299d7d483339d80809a1d80553bda402fffe5bfeffffffff00000001)
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
        polys.append(Poly.random(t, random.randint(0, Field.modulus-1)))
    write_polys(prefix, Field.modulus, N, t, polys)


###############
# Test programs
###############
async def test_prog1(context):

    filename = 'sharedata/test_zeros-%d.share' % (context.myid,)
    zeros = context.read_shares(open(filename))

    filename = 'sharedata/test_triples-%d.share' % (context.myid,)
    triples = context.read_shares(open(filename))

    # Example of Beaver multiplication
    x = zeros[0] + context.Share(10)
    y = zeros[1] + context.Share(15)

    a, b, ab = triples[:3]
    # assert await a.open() * await b.open() == await ab.open()

    D = (x - a).open()
    E = (y - b).open()

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


# Read zeros from file, open them
async def test_prog2(context):

    filename = 'sharedata/test_zeros-%d.share' % (context.myid,)
    shares = context.read_shares(open(filename))

    print('[%d] read %d shares' % (context.myid, len(shares)))

    for share in shares[:100]:
        s = await share.open()
        assert s == 0
    print('[%d] Finished' % (context.myid,))


# Run some test cases
if __name__ == '__main__':
    print('Generating random shares of zero in sharedata/')
    generate_test_zeros('sharedata/test_zeros', 1000, 3, 2)
    print('Generating random shares of triples in sharedata/')
    generate_test_triples('sharedata/test_triples', 1000, 3, 2)

    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    loop.set_debug(True)
    try:
        loop.run_until_complete(runProgramInNetwork(test_prog1, 3, 2))
        loop.run_until_complete(runProgramInNetwork(test_prog2, 3, 2))
    finally:
        loop.close()
