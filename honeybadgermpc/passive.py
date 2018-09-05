import asyncio
from asyncio import Future
from .field import GF, GFElement
from .polynomial import polynomialsOver
from .router import simple_router
import random
import os

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
            assert shareid == len(buf), "shareid: %d, len: %d" % (shareid, len(buf))
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
            context.open_share(self).add_done_callback(cb)
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

        def __radd__(self, other): return Share(self.v + other.v)

        def __rsub__(self, other): return Share(-self.v + other.v)

        # @typecheck(int,field)
        def __rmul__(self, other): return Share(self.v * other)

        # @typecheck(Share)
        # TODO
        def __mul__(self, other): raise NotImplemented

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

        def open(self) -> GFElementFuture:
            res = GFElementFuture()

            def cb2(sh): return res.set_result(sh.result())

            def cb1(_): return self.result().open().add_done_callback(cb2)
            self.add_done_callback(cb1)
            return res

    return Share

# Share = shareInContext(None)


# Create a fake network with N instances of the program
async def runProgramAsTasks(program, N, t):
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
Field = GF.get(0x73eda753299d7d483339d80809a1d80553bda402fffe5bfeffffffff00000001)
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

    D = await (x - a).open()
    E = await (y - b).open()

    # This is a random share of x*y
    xy = context.Share(D*E) + D*b + E*a + ab

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

async def powermix_phase1(context):

    k = 32
    batch = 1
    inputs = [[0 for _ in range(k)] for _ in range(batch)]
    inputs_debug = [[0 for _ in range(k)] for _ in range(batch)]
    p = 115792089237316195423570985008687907853269984665640564039457584007913129640423
    Zp = GF(p)
    a_minus_b = [[0 for _ in range(k)] for _ in range(batch)]
    precomputed_powers = [[0 for _ in range(k)] for _ in range(k)]

    def load_input_from_file(k,p,batch):
        for batchiter in range(1, batch + 1):
            filename = "party" + str(context.myid+1) + "_butterfly_online_batch" + str(batchiter)

            FD = open(filename, "r")
            line = FD.readline()
            #if int(line) != k:
            #    print "k dismatch!! k in file is %d"%(int(line))
            line = FD.readline()
            #if int(line) != p:
            #    print "prime dismatch!! prime in file is %d"%(int(line))
            Zp = GF(p)

            line = FD.readline()
            i = 0
            while line and i < k:
                #print i
                inputs[batchiter-1][i] = context.Share(int(line))
                line = FD.readline()
                i = i + 1

    load_input_from_file(k,p,batch)

    def load_share_from_file(k,p,row):
        #TODO:
        #filename = "precompute-party%d-%d.share" % (self.runtime.num_players, self.runtime.threshold, self.k, self.runtime.id,cnt)
        filename = "precompute-party%d.share" % (context.myid+1)
        FD = open(filename, "r")
        line = FD.readline()
        # if int(line) != p:
        #     print "p dismatch!! p in file is %d"%(int(line))
        line = FD.readline()
        # if int(line) != k:
        #     print "k dismatch!! k in file is %d"%(int(line))


        line = FD.readline()
        i = 0
        while line and i < k:
            #print i
            precomputed_powers[row][i] = context.Share(int(line))

            line = FD.readline()
            i = i + 1


    for i in range(k):
        load_share_from_file(k,p,i)

    for b in range(batch):
            for i in range(k):
                a_minus_b[b][i] = await (inputs[b][i] - precomputed_powers[i][0]).open()


    def create_output(batch):
        print( "a-b calculation finished" )

        path = "party" + str(context.myid+1) + "-powermixing-online-phase1-output"
        folder = os.path.exists(path)
        if not folder:
            os.makedirs(path)
        for b in range(batch):
            for i in range(k):
                filename = "party" + str(context.myid+1) + "-powermixing-online-phase1-output/powermixing-online-phase1-output" + str(i+1) + "-batch" + str(b+1)

                FD = open(filename, "w")

                content =  str(p) + "\n" + str(inputs[b][i])[1:-1] + "\n" + str(a_minus_b[b][i])[1:-1] + "\n" + str(k) + "\n"

                for share in precomputed_powers[i]:
                    content = content + str(share)[1:-1] + "\n"
                FD.write(content)
                FD.close()
        print("output to file finished")
    create_output(batch)


async def powermix_phase3(context):

    k = 32
    batch = 1
    inputs = [[0 for _ in range(k)] for _ in range(batch)]
    p = 115792089237316195423570985008687907853269984665640564039457584007913129640423
    Zp = GF(p)
    open_value= [[0 for _ in range(k)] for _ in range(batch)]

    def load_input_from_file(k,p,b):
        for batch in range(b):
            filename = "powers.sum" + str(context.myid+1) + "_batch" + str(batch+1)

            FD = open(filename, "r")
            line = FD.readline()
            #if int(line) != p:
            #    print "p dismatch!! p in file is %d"%(int(line))
            line = FD.readline()
            # if int(line) != k:
            #     print "k dismatch!! k in file is %d"%(int(line))


            line = FD.readline()
            i = 0
            while line and i < k:
                #print i
                inputs[batch][i] = context.Share(int(line))

                line = FD.readline()
                i = i + 1
    load_input_from_file(k,p,batch)

    for b in range(batch):
        for i in range(k):
            open_value[b][i] = await (inputs[b][i]).open()

    def create_output(batch):

        print("value open finished")

        for b in range(batch):
            filename = "party" + str(context.myid+1) + "-powermixing-online-phase3-output-batch" + str(b+1)

            FD = open(filename, "w")

            content =  str(p) + "\n" + str(k) + "\n"

            for share in open_value[b]:
                content = content + str(share)[1:-1] + "\n"
            FD.write(content)
            FD.close()
            print("file outputs finished")
    create_output(batch)
# Run some test cases
if __name__ == '__main__':
    #print('Generating random shares of zero in sharedata/')
    #print(os.getcwd())
    #generate_test_zeros('sharedata/test_zeros', 1000, 3, 2)
    #print('Generating random shares of triples in sharedata/')
    #generate_test_triples('sharedata/test_triples', 1000, 3, 2)

    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    loop.set_debug(True)
    try:
        loop.run_until_complete(runProgramAsTasks(test_prog1, 3, 2))
        loop.run_until_complete(runProgramAsTasks(test_prog2, 3, 2))
    finally:
        loop.close()
