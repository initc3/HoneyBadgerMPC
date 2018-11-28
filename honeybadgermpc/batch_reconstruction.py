import asyncio
from .field import GF
from .polynomial import polynomialsOver
from .robust_reconstruction import attempt_reconstruct, robust_reconstruct
from .logger import BenchmarkLogger
from collections import defaultdict
from asyncio import Queue
from math import ceil
from time import time


async def waitFor(aws, to_wait):
    # waits for at least number `to_wait` out of the aws
    # coroutines to finish, returning None for all the ones
    # not finished yet
    aws = list(map(asyncio.ensure_future, aws))
    done, pending = set(), set(aws)
    while len(done) < to_wait:
        _d, pending = await asyncio.wait(pending,
                                         return_when=asyncio.FIRST_COMPLETED)
        done |= _d
    result = [await d if d in done else None for d in aws]
    return result


def subscribeRecv(recv):
    tagTable = defaultdict(Queue)
    taken = set()  # Replace this with a bloom filter?

    async def _recvLoop():
        while True:
            j, (tag, o) = await recv()
            tagTable[tag].put_nowait((j, o))

    def subscribe(tag):
        # take everything from the queue
        # further things sent directly
        assert tag not in taken
        taken.add(tag)
        return tagTable[tag].get

    _task = asyncio.create_task(_recvLoop())
    return _task, subscribe


def recvEachParty(recv, n):
    queues = [Queue() for _ in range(n)]

    async def _recvLoop():
        while True:
            j, o = await recv()
            queues[j].put_nowait(o)

    _task = asyncio.create_task(_recvLoop())
    return _task, [q.get for q in queues]


def wrapSend(tag, send):
    def _send(j, o):
        send(j, (tag, o))
    return _send


def toChunks(data, chunkSize):
    res = []
    n_chunks = ceil(len(data) / chunkSize)
    # print('toChunks:', chunkSize, len(data), n_chunks)
    for j in range(n_chunks):
        start = chunkSize * j
        stop = chunkSize * (j + 1)
        res.append(data[start:stop])
    return res


def attempt_reconstruct_batch(data, field, n, t, point):
    assert len(data) == n
    assert sum(f is not None for f in data) >= 2 * t + 1
    assert 2*t < n, "Robust reconstruct waits for at least n=2t+1 values"

    Bs = [len(f) for f in data if f is not None]
    n_chunks = Bs[0]
    assert all(b == n_chunks for b in Bs)
    recons = []
    for i in range(n_chunks):
        chunk = [d[i] if d is not None else None for d in data]
        try:
            P, failures = attempt_reconstruct(chunk, field, n, t, point)
            recon = P.coeffs
            recon += [field(0)] * (t + 1 - len(recon))
            recons += recon
        except ValueError as e:
            if str(e) in ("Wrong degree", "no divisors found"):
                # TODO: return partial success, keep tracking of failures
                return None
            raise
    return recons


def withAtMostNonNone(data, k):
    """
    Returns an sequence made from `data`, except with at most `k` are
    non-None
    """
    howMany = 0
    for x in data:
        if howMany >= k:
            yield None
        else:
            if x is not None:
                howMany += 1
            yield x


async def batch_reconstruct(elem_batches, p, t, n, myid, send, recv, debug=False):
    """
    args:
      shared_secrets: an array of points representing shared secrets S1 - SB
      p: field modulus
      t: degree t polynomial
      n: total number of nodes n >= 3t+1
      myid: id of the specific node running batch_reconstruction function

    output:
      the reconstructed array of B shares

    Communication takes place over two rounds,
      objects sent/received of the form ('R1', shares) or ('R2', shares)
      up to one of each for each party

    Reconstruction takes places in chunks of t+1 values
    """
    Fp = field = GF.get(p)
    Poly = polynomialsOver(Fp)
    benchLogger = BenchmarkLogger.get(myid)

    def point(i): return Fp(i+1)  # TODO: make it use omega

    _taskSub, subscribe = subscribeRecv(recv)
    del recv  # ILC enforces this in type system, no duplication of reads
    _taskR1, qR1 = recvEachParty(subscribe('R1'), n)
    _taskR2, qR2 = recvEachParty(subscribe('R2'), n)
    dataR1 = [asyncio.create_task(recv()) for recv in qR1]
    dataR2 = [asyncio.create_task(recv()) for recv in qR2]
    del subscribe  # ILC should determine we can garbage collect after this

    def sendBatch(data, send, point):
        # print('sendBatch data:', data)
        toSend = [[] for _ in range(n)]
        for chunk in toChunks(data, t + 1):
            f_poly = Poly(chunk)
            for j in range(n):
                toSend[j].append(f_poly(point(j)).value)  # send just the int value
        # print('batch to send:', toSend)
        for j in range(n):
            send(j, toSend[j])

    # Step 1: Compute the polynomial, then send
    #  Evaluate and send f(j,i) for each other participating party Pj
    sendBatch(elem_batches, wrapSend('R1', send), point)

    # Step 2: Attempt to reconstruct P1
    # Wait for between 2t+1 values and N values
    # trying to reconstruct each time
    for nAvailable in range(2 * t + 1, n + 1):
        data = await waitFor(dataR1, nAvailable)
        data = tuple(withAtMostNonNone(data, nAvailable))
        # print('data R1:', data, 'nAvailable:', nAvailable)
        data = tuple([None if d is None else tuple(map(Fp, d)) for d in data])
        stime = time()
        reconsR2 = attempt_reconstruct_batch(data, field, n, t, point)
        if reconsR2 is None:
            # TODO: return partial success, so we can skip these next turn
            continue
        benchLogger.info(f"[BatchReconstruct] P1: {time() - stime}")
        break
    assert nAvailable <= n, "reconstruction failed"
    # print('reconsR2:', reconsR2)
    assert len(reconsR2) >= len(elem_batches)
    reconsR2 = reconsR2[:len(elem_batches)]

    # Step 3: Send R2 points
    sendBatch(reconsR2, wrapSend('R2', send), lambda _: Fp(0))

    # Step 4: Attempt to reconstruct R2
    for nAvailable in range(nAvailable, n + 1):
        data = await waitFor(dataR2, nAvailable)
        data = tuple(withAtMostNonNone(data, nAvailable))
        data = tuple([None if d is None else tuple(map(Fp, d)) for d in data])
        # print('data R2:', data, 'nAvailable:', nAvailable)
        stime = time()
        reconsP = attempt_reconstruct_batch(data, field, n, t, point)
        if reconsP is None:
            # TODO: return partial success, so we can skip these next turn
            continue
        benchLogger.info(f"[BatchReconstruct] P2: {time() - stime}")
        break
    assert nAvailable <= n, "reconstruction failed"
    assert len(reconsP) >= len(elem_batches)
    reconsP = reconsP[:len(elem_batches)]

    _taskR1.cancel()
    _taskR2.cancel()
    _taskSub.cancel()
    for q in dataR1:
        q.cancel()
    for q in dataR2:
        q.cancel()

    return reconsP


async def batch_reconstruct_one(shared_secrets, p, t, n, myid, send, recv, debug):
    """
    args:
      shared_secrets: an array of points representing shared secrets S1 - St+1
      p: prime number used in the field
      t: degree t polynomial
      n: total number of nodes n=3t+1
      myid: id of the specific node running batch_reconstruction function

    output:
      the reconstructed array of t+1 shares

    Communication takes place over two rounds,
      objects sent/received of the form ('R1', share) or ('R2', share)
      up to one of each for each party
    """

    if debug:
        print("my id %d" % myid)
        print(shared_secrets)

    Fp = GF.get(p)
    Poly = polynomialsOver(Fp)

    def point(i): return Fp(i+1)  # TODO: make it use omega

    # Reconstruct a batch of exactly t+1 secrets
    assert len(shared_secrets) == t+1

    # We'll wait to receive between 2t+1 shares
    round1_shares = [asyncio.Future() for _ in range(n)]
    round2_shares = [asyncio.Future() for _ in range(n)]

    async def _recvloop():
        while True:
            (j, (r, o)) = await recv()
            if r == 'R1':
                assert(not round1_shares[j].done())
                round1_shares[j].set_result(o)
            elif r == 'R2':
                assert(not round2_shares[j].done())
                round2_shares[j].set_result(o)
            else:
                assert False, f"invalid round tag: {r}"

    # Run receive loop as background task, until self.prog finishes
    loop = asyncio.get_event_loop()
    bgtask = loop.create_task(_recvloop())

    try:
        # Round 1:
        # construct the first polynomial f(x,i) = [S1]ti + [S2]ti x + … [St+1]ti xt
        f_poly = Poly(shared_secrets)

        #  Evaluate and send f(j,i) for each other participating party Pj
        for j in range(n):
            send(j, ('R1', f_poly(point(j))))

        # Robustly reconstruct f(i,X)
        P1, failures_detected = await robust_reconstruct(round1_shares, Fp, n, t, point)
        if debug:
            print(f"I am {myid} and evil nodes are {failures_detected}")

        # Round 2:
        # Evaluate and send f(i,0) to each other party
        for j in range(n):
            send(j, ('R2', P1(Fp(0))))

        # Robustly reconstruct f(X,0)
        P2, failures_detected = await robust_reconstruct(round2_shares, Fp, n, t, point)

        # print(f"I am {myid} and the secret polynomial is {P2}")
        return P2.coeffs

    finally:
        bgtask.cancel()
