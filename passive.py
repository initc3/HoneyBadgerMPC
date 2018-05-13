import asyncio
from field import GF
from polynomial import polynomialsOver
from collections import deque
from router import simple_router
import random

class NotEnoughShares(Exception): pass
    
class NetworkContext(object):

    def __init__(self, sid, N, t, myid, send, recv):
        # send(j, o): sends object o to party j with (current sid)
        # recv(): returns (j, o) from party j
        assert type(N) is int and type(t) is int
        #assert 3*t < N

        self.sid = sid
        self.N = N
        self.t = t
        self.myid = myid
        self.send = send
        self.recv = recv

        # A Viff program should only depend on common parameters,
        # and the values of opened shares. Opened shares will
        # returned in the order that share is encountered

        # Store deferreds representing SharedValues
        self._openings = []

        # Store opened shares until ready to reconstruct
        # shareid => { [playerid => share] }        
        self._share_buffers = tuple( [] for _ in range(N) )

    def _reconstruct(self, shareid):
        # Are there enough shares to reconstruct?
        shares = [(i+1,self._share_buffers[i][shareid])
                  for i in range(self.N)
                  if len(self._share_buffers[i]) > shareid]
        if len(shares) < self.t+1: raise NotEnoughShares

        # print('[%d] reconstruct %s' % (self.myid, shareid,))

        # TODO refer to lagrange
        s = Poly.interpolate_at(shares)

        # Set the result on the future representing this share
        self._openings[shareid].set_result(s)

    def openSVal(self, sval):
        # Is this already present
        opening = asyncio.Future()
        shareid = len(self._openings)
        self._openings.append(opening)

        # Broadcast share
        for j in range(self.N):
            self.send(j, (shareid, sval.v))

        # Reconstruct if we already had enough shares
        try: self._reconstruct(shareid)
        except NotEnoughShares: pass

        # Return future
        return opening
    
    async def _run(self):
        while True:
            (j, (shareid, share)) = await self.recv()
            buf = self._share_buffers[j]
            
            # Shareid is redundant, but confirm it is one greater
            assert shareid == len(buf)
            buf.append(share)

            # Reconstruct if we now have enough shares,
            # and if the opening has been asked for
            if len(self._openings) > shareid:
                try: self._reconstruct(shareid)
                except NotEnoughShares: pass
            
        return True

    # File I/O
    def read_shares(self, f):
        # Read shares from a file object
        lines = iter(f)
        # first line: field modulus
        modulus = int(next(lines)) 
        assert Field.modulus == modulus
        # second line: share degree
        degree = int(next(lines))
        # third line: id
        myid = int(next(lines))
        shares = []
        # remaining lines: shared values
        for line in lines:
            shares.append(Share(self, int(line)))
        return shares

    def write_shares(self, f, shares):
        write_shares(f, Field.modulus, self.myid,
                     [share.v for share in shares])

    # Create a share directly from the local element
    def share_from_element(self, v):
        return Share(self, v)

def write_shares(f, modulus, degree, myid, shares):
    print(modulus, file=f)
    print(degree, file=f)
    print(myid, file=f)
    for share in shares:
        print(share.value, file=f)

###############
# Share class 
###############

class Share(object):
    def __init__(self, context, v, id=None):
        self.context = context

        # v is the local value of the share
        if type(v) is int: v = Field(v)
        assert type(v) is Field
        self.v = v

        #print('share created: {%d}' % (v,))

    # Publicly reconstruct a shared value
    def open(self): return self.context.openSVal(self)
       
    # Linear combinations of shares can be performed directly
    # TODO: add type check
    # @typecheck(Share)
    def __add__(self, other): return Share(self.context, self.v + other.v)
    def __sub__(self, other): return Share(self.context, self.v - other.v)
    def __radd__(self, other): return Share(self.context, self.v + other.v)
    def __rsub__(self, other): return Share(self.context, -self.v + other.v)
    # @typecheck(int,field)
    def __rmul__(self, other): return Share(self.context, self.v * other)

    def __str__(self): return '{%d}'% (self.v)


# Create a fake network with N instances of the program
async def runProgramInNetwork(program, N, t):
    loop = asyncio.get_event_loop()
    sends,recvs = simple_router(N)

    tasks = []
    bgtasks = []
    for i in range(N):
        context = NetworkContext('sid', N, t, i, sends[i], recvs[i])
        bgtasks.append(loop.create_task(context._run()))
        tasks.append(program(context))

    await asyncio.gather(*tasks)
    for task in bgtasks: task.cancel()

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
        a = Field(random.randint(0,Field.modulus-1))
        b = Field(random.randint(0,Field.modulus-1))
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
        polys.append(Poly.random(t, random.randint(0,Field.modulus-1)))
    write_polys(prefix, Field.modulus, N, t, polys)

###############
# Test programs
###############
async def test_prog1(context):

    a = context.share_from_element(1)
    b = context.share_from_element(2)

    x = context.share_from_element(5)
    y = context.share_from_element(10)
    xy = context.share_from_element(15)

    D = (a - x).open()
    E = (b - y).open()

    d,e = await asyncio.gather(D,E)

    print("Finished", a,b,d,e)

# Read zeros from file, open them
async def test_prog2(context):

    filename = 'sharedata/test_zeros-%d.share' % (context.myid,)
    shares = context.read_shares(open(filename))

    print('[%d] read %d shares' % (context.myid, len(shares)))
    a = await shares[0].open()
    print(context.myid, "Finished", a)
    

# Run some test cases
if __name__ == '__main__':
    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    loop.set_debug(True)
    try:
        loop.run_until_complete(runProgramInNetwork(test_prog2, 3, 2))
    finally:
        loop.close()
