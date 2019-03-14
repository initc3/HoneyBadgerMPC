import asyncio
from .field import GF
from .polynomial import EvalPoint
import logging
from collections import defaultdict
from asyncio import Queue
from math import ceil
import time
from .reed_solomon import Algorithm, EncoderFactory, DecoderFactory, RobustDecoderFactory
from .reed_solomon import IncrementalDecoder
import random


async def fetch_one(aws):
    aws_to_idx = {aws[i]: i for i in range(len(aws))}
    pending = set(aws)
    while len(pending) > 0:
        done, pending = await asyncio.wait(pending,
                                           return_when=asyncio.FIRST_COMPLETED)
        for d in done:
            yield (aws_to_idx[d], await d)


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


def wrap_send(tag, send):
    def _send(j, o):
        send(j, (tag, o))

    return _send


def recv_each_party(recv, n):
    queues = [Queue() for _ in range(n)]

    async def _recv_loop():
        while True:
            j, o = await recv()
            queues[j].put_nowait(o)

    _task = asyncio.create_task(_recv_loop())
    return _task, [q.get for q in queues]


def to_chunks(data, chunk_size, default=0):
    """Chunkize data into `chunk_size` length pieces

    If len(data) is not a multiple of chunk_size, then the default value is appended
    to the last chunk to make sure the chunk is of size `chunk_size`
    """
    res = []
    n_chunks = ceil(len(data) / chunk_size)
    for j in range(n_chunks):
        start = chunk_size * j
        stop = chunk_size * (j + 1)
        chunk = data[start:stop]
        if len(chunk) < chunk_size:
            chunk += [default] * (chunk_size - len(chunk))
        res.append(chunk)
    return res


def merge_lists(lists):
    result = []
    for l in lists:
        result += l
    return result


def list_transpose(lst):
    """Transpose of list of lists"""
    return [[lst[j][i] for j in range(len(lst))] for i in range(len(lst[0]))]


async def incremental_decode(receivers, encoder, decoder, robust_decoder, batch_size, t,
                             n):
    inc_decoder = IncrementalDecoder(encoder, decoder, robust_decoder,
                                     degree=t, batch_size=batch_size,
                                     max_errors=t)

    async for idx, d in fetch_one(receivers):
        inc_decoder.add(idx, d)
        if inc_decoder.done():
            result, _ = inc_decoder.get_results()
            return result
    return None


async def batch_reconstruct(secret_shares, p, t, n, myid, send, recv, config=None,
                            use_fft=False, debug=False):
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

    fp = GF.get(p)
    secret_shares = [v.value for v in secret_shares]
    round1_chunks = to_chunks(secret_shares, t + 1)
    num_chunks = len(round1_chunks)

    if config is not None and config.induce_faults:
        logging.debug("[FAULT][BatchReconstruction] Sending random shares.")
        secret_shares = [random.randint(0, p - 1) for _ in range(len(secret_shares))]

    point = EvalPoint(fp, n, use_fft=use_fft)
    bench_logger = logging.LoggerAdapter(logging.getLogger("benchmark_logger"),
                                         {"node_id": myid})
    subscribe_task, subscribe = subscribe_recv(recv)
    del recv  # ILC enforces this in type system, no duplication of reads

    task_r1, q_r1 = recv_each_party(subscribe('R1'), n)
    task_r2, q_r2 = recv_each_party(subscribe('R2'), n)
    data_r1 = [asyncio.create_task(recv()) for recv in q_r1]
    data_r2 = [asyncio.create_task(recv()) for recv in q_r2]
    del subscribe  # ILC should determine we can garbage collect after this

    enc = EncoderFactory.get(point, Algorithm.FFT if use_fft else Algorithm.VANDERMONDE)
    dec = DecoderFactory.get(point, Algorithm.FFT if use_fft else Algorithm.VANDERMONDE)
    decoding_algorithm = Algorithm.GAO
    if config is not None:
        decoding_algorithm = config.decoding_algorithm
    robust_dec = RobustDecoderFactory.get(t, point, algorithm=decoding_algorithm)

    # Step 1: Compute the polynomial, then send
    start_time = time.time()
    encoded = enc.encode(round1_chunks)
    to_send = list_transpose(encoded)
    for j in range(n):
        send(j, ('R1', to_send[j]))
    end_time = time.time()
    bench_logger.info(f"[BatchReconstruct] P1 Send: {end_time - start_time}")

    # Step 2: Attempt to reconstruct P1
    start_time = time.time()
    recons_r2 = await incremental_decode(data_r1, enc, dec, robust_dec,
                                         num_chunks, t, n)
    if recons_r2 is None:
        logging.error("[BatchReconstruct] P1 reconstruction failed!")
        return None

    end_time = time.time()
    bench_logger.info(f"[BatchReconstruct] P1 Reconstruct: {end_time - start_time}")

    # Step 3: Send R2 points
    # These are simply evaluations at x=0 or just the constant term
    start_time = time.time()
    to_send = [chunk[0] for chunk in recons_r2]
    for j in range(n):
        send(j, ('R2', to_send))
    end_time = time.time()
    bench_logger.info(f"[BatchReconstruct] P2 Send: {end_time - start_time}")

    # Step 4: Attempt to reconstruct R2
    start_time = time.time()
    recons_p = await incremental_decode(data_r2, enc, dec, robust_dec,
                                        num_chunks, t, n)
    if recons_p is None:
        logging.error("[BatchReconstruct] P2 reconstruction failed!")
        return None

    end_time = time.time()
    bench_logger.info(f"[BatchReconstruct] P2 Reconstruct: {end_time - start_time}")

    task_r1.cancel()
    task_r2.cancel()
    subscribe_task.cancel()
    for q in data_r1:
        q.cancel()
    for q in data_r2:
        q.cancel()

    result = merge_lists(recons_p)
    assert len(result) >= len(secret_shares)

    # Get back result as GFElement type
    return list(map(fp, result[:len(secret_shares)]))
