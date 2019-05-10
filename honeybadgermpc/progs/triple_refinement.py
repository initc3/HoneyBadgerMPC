import time
import logging
import asyncio
from itertools import chain
from honeybadgermpc.config import HbmpcConfig
from honeybadgermpc.ipc import ProcessProgramRunner
from honeybadgermpc.preprocessing import AWSPreProcessedElements
from honeybadgermpc.ntl.helpers import vandermonde_batch_evaluate
from honeybadgermpc.ntl.helpers import vandermonde_batch_interpolate


async def batch_beaver(context, a_, b_, x_, y_, z_):
    assert len(a_) == len(b_) == len(x_) == len(y_) == len(z_)
    a, b, x, y = list(map(context.ShareArray, [a_, b_, x_, y_]))

    use_power_of_omega = False
    f, g = await asyncio.gather(*[
        (a - x).open(use_power_of_omega), (b - y).open(use_power_of_omega)])
    c = [(d*e).value + (d*q).v.value + (e*p).v.value + pq
         for (p, q, pq, d, e) in zip(x_, y_, z_, f, g)]
    return c


async def refine_triples(context, m, a_batches, b_batches, c_batches):
    """This method takes dirty triples and refines them.

    Arguments:
        context {Mpc} -- MPC context.
        a_dirty {list[Share]} -- Shares of first part of the triples.
        b_dirty {list[Share]} -- Shares of second part of the triples.
        c_dirty {list[Share]} -- Shares of first*second part of the triples.

    Returns:
        list[Share] -- Shares of first part of the refined triples.
        list[Share] -- Shares of second part of the refined triples.
        list[Share] -- Shares of first*second part of the refined triples.
    """

    num_batches = len(a_batches)
    assert len(a_batches) == len(b_batches) == len(c_batches) == num_batches
    assert all(len(batch) == m for batch in a_batches)
    assert all(len(batch) == m for batch in b_batches)
    assert all(len(batch) == m for batch in c_batches)
    n, t = context.N, context.t
    d = (m-1)//2  # d = 2*m + 1
    modulus = context.field.modulus
    assert m >= n-t and m <= n

    # Use the first `d+1` points to define the d-degree polynomials A() and B()
    a, b, c = [None]*num_batches, [None]*num_batches, [None]*num_batches
    for i in range(num_batches):
        a[i], b[i], c[i] = a_batches[i][:d+1], b_batches[i][:d+1], c_batches[i][:d+1]
    coeffs = vandermonde_batch_interpolate(list(range(d+1)), a+b, modulus)
    assert all(len(batch) == d+1 for batch in coeffs)
    assert len(coeffs) == 2*num_batches

    # Evaluate A() and B() at `d` more points
    rest = vandermonde_batch_evaluate(
        list(range(d+1, 2*d+1)), coeffs, modulus)
    assert all(len(batch) == d for batch in rest)
    assert len(rest) == 2*num_batches

    # Multiply these newly evaluated `d` points on A() and B() to
    # obtain `d` more points on C() using batch beaver multiplication
    x, y, z = [], [], []
    for i in range(num_batches):
        x += a_batches[i][d+1:2*d+1]
        y += b_batches[i][d+1:2*d+1]
        z += c_batches[i][d+1:2*d+1]

    a_rest = list(chain.from_iterable(rest[:num_batches]))
    b_rest = list(chain.from_iterable(rest[num_batches:]))
    assert len(x) == len(y) == len(z) == len(a_rest) == len(b_rest) == num_batches*d
    c_rest = await batch_beaver(context, a_rest, b_rest, x, y, z)
    assert len(c_rest) == num_batches*d

    # The initial `d+1` points and the `d` points computed in the last step make a
    # total of `2d+1` points which can now be used to completely define C() which
    # is a 2d degree polynomial
    # c = [batch[:d+1] for batch in c_batches]
    c_rest = [c_rest[i:i+d] for i in range(0, len(c_rest), d)]
    assert all(len(batch) == d for batch in c_rest)
    assert all(len(batch) == d+1 for batch in c)
    c_all = [x+y for x, y in zip(c, c_rest)]
    assert all(len(batch) == 2*d+1 for batch in c_all)

    c_coeffs = vandermonde_batch_interpolate(list(range(2*d+1)), c_all, modulus)
    assert len(c_coeffs) == num_batches
    assert all(len(batch) == 2*d+1 for batch in c_coeffs)

    # The total number of triples which can be extracted securely
    k = d+1-t

    # Evaluate the polynomial at `k` new points
    shares = vandermonde_batch_evaluate(
        list(range(n+1, n+1+k)), coeffs + c_coeffs, modulus)
    assert all(len(batch) == k for batch in shares)
    p, q, pq = shares[:num_batches], shares[num_batches:2 *
                                            num_batches], shares[2*num_batches:]
    assert len(p) == len(q) == len(pq) == num_batches
    return p, q, pq


async def _prog(context, a, b, ab):
    logger = logging.LoggerAdapter(logging.getLogger(
        "benchmark_logger"), {"node_id": context.myid})
    start_time = time.time()
    await refine_triples(context, context.N, a, b, ab)
    end_time = time.time()
    logger.info("Finished in: %f seconds.", end_time-start_time)


async def _run(peers, n, t, my_id):
    seed = HbmpcConfig.extras.get("seed", 0)
    b = HbmpcConfig.extras.get("batch_size", max(n, 62000//n))
    logging.info("Batch size: %d", b)
    pp_elements = AWSPreProcessedElements(n, t, my_id, seed, use_power_of_omega=False)
    a_batches, b_batches, ab_batches = [], [], []
    start_time = time.time()
    for _ in range(b):
        a, b, ab = [], [], []
        for p, q, pq in pp_elements.get_triple(n):
            a.append(p.value)
            b.append(q.value)
            ab.append(pq.value)
        a_batches.append(a)
        b_batches.append(b)
        ab_batches.append(ab)
    end_time = time.time()
    logging.info("Preprocessing done in %f.", end_time-start_time)
    async with ProcessProgramRunner(peers, n, t, my_id) as runner:
        await runner.execute("0", _prog, a=a_batches, b=b_batches, ab=ab_batches)


if __name__ == "__main__":
    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    loop.run_until_complete(_run(
        HbmpcConfig.peers, HbmpcConfig.N, HbmpcConfig.t, HbmpcConfig.my_id))
