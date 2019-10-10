import asyncio
from honeybadgermpc.ntl import vandermonde_batch_evaluate
from honeybadgermpc.ntl import vandermonde_batch_interpolate


async def batch_beaver(context, a_, b_, x_, y_, z_):
    assert len(a_) == len(b_) == len(x_) == len(y_) == len(z_)
    a, b, x, y = list(map(context.ShareArray, [a_, b_, x_, y_]))

    f, g = await asyncio.gather(*[(a - x).open(), (b - y).open()])
    c = [
        (d * e).value + (d * q).value + (e * p).value + pq
        for (p, q, pq, d, e) in zip(x_, y_, z_, f, g)
    ]
    return c


async def refine_triples(context, a_dirty, b_dirty, c_dirty):
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

    assert len(a_dirty) == len(b_dirty) == len(c_dirty)
    n, t = context.N, context.t
    m = len(a_dirty)
    d = (m - 1) // 2  # d = 2*m + 1
    modulus = context.field.modulus
    assert m >= n - t and m <= n

    # Use the first `d+1` points to define the d-degree polynomials A() and B()
    a, b = a_dirty[: d + 1], b_dirty[: d + 1]
    a_coeffs = vandermonde_batch_interpolate(list(range(d + 1)), [a], modulus)[0]
    b_coeffs = vandermonde_batch_interpolate(list(range(d + 1)), [b], modulus)[0]
    assert len(a_coeffs) == len(b_coeffs) == d + 1

    # Evaluate A() and B() at `d` more points
    a_rest = vandermonde_batch_evaluate(
        list(range(d + 1, 2 * d + 1)), [a_coeffs], modulus
    )[0]
    b_rest = vandermonde_batch_evaluate(
        list(range(d + 1, 2 * d + 1)), [b_coeffs], modulus
    )[0]
    assert len(a_rest) == len(b_rest) == d

    # Multiply these newly evaluated `d` points on A() and B() to
    # obtain `d` more points on C() using batch beaver multiplication
    x, y, z = (
        a_dirty[d + 1 : 2 * d + 1],
        b_dirty[d + 1 : 2 * d + 1],
        c_dirty[d + 1 : 2 * d + 1],
    )
    assert len(x) == len(y) == len(z)
    c_rest = await batch_beaver(context, a_rest, b_rest, x, y, z)
    assert len(c_rest) == d

    # The initial `d+1` points and the `d` points computed in the last step make a
    # total of `2d+1` points which can now be used to completely define C() which
    # is a 2d degree polynomial
    c = c_dirty[: d + 1]
    c_coeffs = vandermonde_batch_interpolate(
        list(range(2 * d + 1)), [c + c_rest], modulus
    )[0]
    assert len(c_coeffs) == 2 * d + 1

    # The total number of triples which can be extracted securely
    k = d + 1 - t

    # Evaluate the polynomial at `k` new points
    p = vandermonde_batch_evaluate(list(range(n + 1, n + 1 + k)), [a_coeffs], modulus)[
        0
    ]
    q = vandermonde_batch_evaluate(list(range(n + 1, n + 1 + k)), [b_coeffs], modulus)[
        0
    ]
    pq = vandermonde_batch_evaluate(list(range(n + 1, n + 1 + k)), [c_coeffs], modulus)[
        0
    ]

    assert len(p) == len(q) == len(pq) == k
    return p, q, pq
