import asyncio
from .field import GF
from .polynomial import polynomials_over, EvalPoint, fnt_decode_step1
from .robust_reconstruction import attempt_reconstruct, robust_reconstruct
import logging
from collections import defaultdict
from asyncio import Queue
from math import ceil
from time import time


async def wait_for(aws, to_wait):
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


def subscribe_recv(recv):
    tag_table = defaultdict(Queue)
    taken = set()  # Replace this with a bloom filter?

    async def _recv_loop():
        while True:
            j, (tag, o) = await recv()
            tag_table[tag].put_nowait((j, o))

    def subscribe(tag):
        # take everything from the queue
        # further things sent directly
        assert tag not in taken
        taken.add(tag)
        return tag_table[tag].get

    _task = asyncio.create_task(_recv_loop())
    return _task, subscribe


def recv_each_party(recv, n):
    queues = [Queue() for _ in range(n)]

    async def _recv_loop():
        while True:
            j, o = await recv()
            queues[j].put_nowait(o)

    _task = asyncio.create_task(_recv_loop())
    return _task, [q.get for q in queues]


def wrap_send(tag, send):
    def _send(j, o):
        send(j, (tag, o))
    return _send


def to_chunks(data, chunk_size):
    res = []
    n_chunks = ceil(len(data) / chunk_size)
    logging.debug(f'toChunks: {chunk_size} {len(data)} {n_chunks}')
    for j in range(n_chunks):
        start = chunk_size * j
        stop = chunk_size * (j + 1)
        res.append(data[start:stop])
    return res


def attempt_reconstruct_batch(data, field, n, t, point):
    assert len(data) == n
    assert sum(f is not None for f in data) >= 2 * t + 1
    assert 2*t < n, "Robust reconstruct waits for at least n=2t+1 values"

    bs = [len(f) for f in data if f is not None]
    n_chunks = bs[0]
    assert all(b == n_chunks for b in bs)
    recons = []

    if point.use_fft:
        # Precompute data that can be reused for multiple chunks in a batch

        poly = polynomials_over(field)
        zs = [i for i in range(len(data)) if data[i] is not None]

        assert len(zs) >= t + 1
        zs = zs[:(t + 1)]
        as_, ais_ = fnt_decode_step1(poly, zs, point.omega2, point.order)
        precomputed_data = (zs, as_, ais_)
    else:
        precomputed_data = None

    for i in range(n_chunks):
        chunk = [d[i] if d is not None else None for d in data]
        try:
            p, failures = attempt_reconstruct(chunk, field, n, t, point,
                                              precomputed_data)
            recon = p.coeffs
            recon += [field(0)] * (t + 1 - len(recon))
            recons += recon
        except ValueError as e:
            if str(e) in ("Wrong degree", "no divisors found", "Did not coincide"):
                # TODO: return partial success, keep tracking of failures
                return None
            raise
    return recons


def with_at_most_non_none(data, k):
    """
    Returns an sequence made from `data`, except with at most `k` are
    non-None
    """
    how_many = 0
    for x in data:
        if how_many >= k:
            yield None
        else:
            if x is not None:
                how_many += 1
            yield x


async def batch_reconstruct(elem_batches, p, t, n, myid, send, recv, debug=False,
                            use_fft=False):
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
    fp = field = GF.get(p)
    poly = polynomials_over(fp)
    bench_logger = logging.LoggerAdapter(
        logging.getLogger("benchmark_logger"), {"node_id": myid})

    point = EvalPoint(fp, n, use_fft=use_fft)

    _task_sub, subscribe = subscribe_recv(recv)
    del recv  # ILC enforces this in type system, no duplication of reads
    _task_r1, q_r1 = recv_each_party(subscribe('R1'), n)
    _task_r2, q_r2 = recv_each_party(subscribe('R2'), n)
    data_r1 = [asyncio.create_task(recv()) for recv in q_r1]
    data_r2 = [asyncio.create_task(recv()) for recv in q_r2]
    del subscribe  # ILC should determine we can garbage collect after this

    def send_batch(data, send, point):
        logging.debug(f'sendBatch data: {data}')
        to_send = [[] for _ in range(n)]
        for chunk in to_chunks(data, t + 1):
            f_poly = poly(chunk)
            for j in range(n):
                to_send[j].append(f_poly(point(j)).value)  # send just the int value
        logging.debug(f'batch to send: {to_send}')
        for j in range(n):
            send(j, to_send[j])

    # Step 1: Compute the polynomial, then send
    #  Evaluate and send f(j,i) for each other participating party Pj
    send_batch(elem_batches, wrap_send('R1', send), point)

    # Step 2: Attempt to reconstruct P1
    # Wait for between 2t+1 values and N values
    # trying to reconstruct each time
    for n_available in range(2 * t + 1, n + 1):
        data = await wait_for(data_r1, n_available)
        data = tuple(with_at_most_non_none(data, n_available))
        logging.debug(f'data R1: {data} nAvailable: {n_available}')
        data = tuple([None if d is None else tuple(map(fp, d)) for d in data])
        stime = time()
        recons_r2 = attempt_reconstruct_batch(data, field, n, t, point)
        if recons_r2 is None:
            # TODO: return partial success, so we can skip these next turn
            continue
        bench_logger.info(f"[BatchReconstruct] P1: {time() - stime}")
        break
    assert n_available <= n, "reconstruction failed"
    logging.debug(f'reconsR2: {recons_r2}')
    assert len(recons_r2) >= len(elem_batches)
    recons_r2 = recons_r2[:len(elem_batches)]

    # Step 3: Send R2 points
    send_batch(recons_r2, wrap_send('R2', send), lambda _: point.zero())

    # Step 4: Attempt to reconstruct R2
    for n_available in range(n_available, n + 1):
        data = await wait_for(data_r2, n_available)
        data = tuple(with_at_most_non_none(data, n_available))
        data = tuple([None if d is None else tuple(map(fp, d)) for d in data])
        logging.debug(f'data R2: {data} nAvailable: {n_available}')
        stime = time()
        recons_p = attempt_reconstruct_batch(data, field, n, t, point)
        if recons_p is None:
            # TODO: return partial success, so we can skip these next turn
            continue
        bench_logger.info(f"[BatchReconstruct] P2: {time() - stime}")
        break
    assert n_available <= n, "reconstruction failed"
    assert len(recons_p) >= len(elem_batches)
    recons_p = recons_p[:len(elem_batches)]

    _task_r1.cancel()
    _task_r2.cancel()
    _task_sub.cancel()
    for q in data_r1:
        q.cancel()
    for q in data_r2:
        q.cancel()

    return recons_p


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
        logging.info("my id %d" % myid)
        logging.info(shared_secrets)

    fp = GF.get(p)
    poly = polynomials_over(fp)

    point = EvalPoint(fp, n, use_fft=False)

    # Reconstruct a batch of exactly t+1 secrets
    assert len(shared_secrets) == t+1

    # We'll wait to receive between 2t+1 shares
    round1_shares = [asyncio.Future() for _ in range(n)]
    round2_shares = [asyncio.Future() for _ in range(n)]

    async def _recv_loop():
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
    bgtask = loop.create_task(_recv_loop())

    try:
        # Round 1:
        # construct the first polynomial f(x,i) = [S1]ti + [S2]ti x + … [St+1]ti xt
        f_poly = poly(shared_secrets)

        #  Evaluate and send f(j,i) for each other participating party Pj
        for j in range(n):
            send(j, ('R1', f_poly(point(j))))

        # Robustly reconstruct f(i,X)
        p1, failures_detected = await robust_reconstruct(round1_shares, fp, n, t, point)
        if debug:
            logging.info(f"I am {myid} and evil nodes are {failures_detected}")

        # Round 2:
        # Evaluate and send f(i,0) to each other party
        for j in range(n):
            send(j, ('R2', p1(point.zero())))

        # Robustly reconstruct f(X,0)
        p2, failures_detected = await robust_reconstruct(round2_shares, fp, n, t, point)

        logging.debug(f"I am {myid} and the secret polynomial is {p2}")
        return p2.coeffs

    finally:
        bgtask.cancel()
