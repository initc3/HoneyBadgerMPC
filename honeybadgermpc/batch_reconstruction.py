import asyncio
from .field import GF
from .polynomial import EvalPoint
import logging
from asyncio import Queue
import time
from .reed_solomon import (
    Algorithm,
    EncoderFactory,
    DecoderFactory,
    RobustDecoderFactory,
)
from .reed_solomon import IncrementalDecoder
import random
from honeybadgermpc.utils.misc import (
    chunk_data,
    flatten_lists,
    transpose_lists,
    subscribe_recv,
)


async def fetch_one(awaitables):
    """ Given a list of awaitables, run them concurrently and
    return them in the order they complete

    args:
        awaitables: List of tasks to run concurrently

    output:
        Yields tuples of the form (idx, result) in the order that the tasks finish
    """
    mapping = {elem: idx for (idx, elem) in enumerate(awaitables)}
    pending = set(awaitables)
    while len(pending) > 0:
        done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
        for d in done:
            yield (mapping[d], await d)


async def incremental_decode(
    receivers, encoder, decoder, robust_decoder, batch_size, t, degree, n
):
    inc_decoder = IncrementalDecoder(
        encoder,
        decoder,
        robust_decoder,
        degree=degree,
        batch_size=batch_size,
        max_errors=t,
    )

    async for idx, d in fetch_one(receivers):
        inc_decoder.add(idx, d)
        if inc_decoder.done():
            result, _ = inc_decoder.get_results()
            return result

    return None


def recv_each_party(recv, n):
    """ Given a recv function and number of parties,
    creates a set of queues for each party, and forwards
    any recv event to the respective queue for each party

    args:
        recv: async function that eventually returns a received object
        n: number of nodes

    output:
        tuple of a background task to forward elements to the correct queue,
        and a list of recv functions that corresponds to each node.
    """
    queues = [Queue() for _ in range(n)]

    async def _recv_loop():
        while True:
            j, o = await recv()
            queues[j].put_nowait(o)

    _task = asyncio.create_task(_recv_loop())
    return _task, [q.get for q in queues]


async def batch_reconstruct(
    secret_shares,
    p,
    t,
    n,
    myid,
    send,
    recv,
    config=None,
    use_omega_powers=False,
    debug=False,
    degree=None,
):
    """
    args:
      shared_secrets: an array of points representing shared secrets S1 - SB
      p: field modulus
      t: faults tolerated
      n: total number of nodes n >= 3t+1
      myid: id of the specific node running batch_reconstruction function
      degree: degree of polynomial to decode (defaults to t)

    output:
      the reconstructed array of B shares

    Communication takes place over two rounds,
      objects sent/received of the form('R1', shares) or ('R2', shares)
      up to one of each for each party

    Reconstruction takes places in chunks of t+1 values
    """
    bench_logger = logging.LoggerAdapter(
        logging.getLogger("benchmark_logger"), {"node_id": myid}
    )

    if degree is None:
        degree = t

    secret_shares = [v.value for v in secret_shares]

    # (optional) Induce faults
    if config is not None and config.induce_faults:
        logging.debug("[FAULT][BatchReconstruction] Sending random shares.")
        secret_shares = [random.randint(0, p - 1) for _ in range(len(secret_shares))]

    # Prepare recv loops for this batch reconstruction
    subscribe_task, subscribe = subscribe_recv(recv)
    del recv  # ILC enforces this in type system, no duplication of reads

    task_r1, recvs_r1 = recv_each_party(subscribe("R1"), n)
    data_r1 = [asyncio.create_task(recv()) for recv in recvs_r1]

    task_r2, recvs_r2 = recv_each_party(subscribe("R2"), n)
    data_r2 = [asyncio.create_task(recv()) for recv in recvs_r2]
    del subscribe  # ILC should determine we can garbage collect after this

    # Set up encoding and decoding algorithms
    fp = GF(p)
    decoding_algorithm = Algorithm.GAO if config is None else config.decoding_algorithm

    point = EvalPoint(fp, n, use_omega_powers=use_omega_powers)
    enc = EncoderFactory.get(
        point, Algorithm.FFT if use_omega_powers else Algorithm.VANDERMONDE
    )
    dec = DecoderFactory.get(
        point, Algorithm.FFT if use_omega_powers else Algorithm.VANDERMONDE
    )
    robust_dec = RobustDecoderFactory.get(t, point, algorithm=decoding_algorithm)

    # Prepare data for step 1
    round1_chunks = chunk_data(secret_shares, degree + 1)
    num_chunks = len(round1_chunks)

    # Step 1: Compute the polynomial P1, then send the elements
    start_time = time.time()

    encoded = enc.encode(round1_chunks)
    to_send = transpose_lists(encoded)
    for dest, message in enumerate(to_send):
        send(dest, ("R1", message))

    end_time = time.time()
    bench_logger.info(f"[BatchReconstruct] P1 Send: {end_time - start_time}")

    # Step 2: Attempt to reconstruct P1
    start_time = time.time()
    try:
        recons_r2 = await incremental_decode(
            data_r1, enc, dec, robust_dec, num_chunks, t, degree, n
        )
    except asyncio.CancelledError:
        # Cancel all created tasks
        for task in [task_r1, task_r2, subscribe_task, *data_r1, *data_r2]:
            task.cancel()

    if recons_r2 is None:
        logging.error("[BatchReconstruct] P1 reconstruction failed!")
        return None

    end_time = time.time()
    bench_logger.info(f"[BatchReconstruct] P1 Reconstruct: {end_time - start_time}")

    # Step 3: Send R2 points
    start_time = time.time()

    # Evaluate all chunks at x=0, then broadcast
    message = [chunk[0] for chunk in recons_r2]
    for dest in range(n):
        send(dest, ("R2", message))

    end_time = time.time()
    bench_logger.info(f"[BatchReconstruct] P2 Send: {end_time - start_time}")

    # Step 4: Attempt to reconstruct R2
    start_time = time.time()
    try:
        recons_p = await incremental_decode(
            data_r2, enc, dec, robust_dec, num_chunks, t, degree, n
        )
    except asyncio.CancelledError:
        # Cancel all created tasks
        for task in [task_r1, task_r2, subscribe_task, *data_r1, *data_r2]:
            task.cancel()

    if recons_p is None:
        logging.error("[BatchReconstruct] P2 reconstruction failed!")
        return None

    end_time = time.time()
    bench_logger.info(f"[BatchReconstruct] P2 Reconstruct: {end_time - start_time}")

    # Cancel all created tasks
    for task in [task_r1, task_r2, subscribe_task, *data_r1, *data_r2]:
        task.cancel()

    result = flatten_lists(recons_p)
    assert len(result) >= len(secret_shares)

    # Get back result as GFElement type
    return list(map(fp, result[: len(secret_shares)]))
