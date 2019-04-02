from honeybadgermpc.polynomial import get_omega
import asyncio
import itertools


def rename_and_unpack_inputs(a_, b_, c_, d, m):
    n = m // 2  # number of triples

    def pad(arr, k): return arr + [0]*(d-len(arr))
    a, b, c = pad(a_[:n], d), pad(b_[:n], d), pad(c_[:n], d)
    x, y, z = pad(a_[n:], d), pad(b_[n:], d), pad(c_[n:], d)

    return a, b, c, x, y, z


def get_extrapolated_values(poly, a, b, d, omega):
    a_ = poly.interp_extrap_cpp(poly.interp_extrap_cpp(a, omega**2), omega)
    b_ = poly.interp_extrap_cpp(poly.interp_extrap_cpp(b, omega**2), omega)
    return a_[2::4], b_[2::4], a_[1::2], b_[1::2]


async def batch_beaver(context, a_, b_, x_, y_, z_):
    assert len(a_) == len(b_) == len(x_) == len(y_) == len(z_)
    a, b, x, y = list(map(context.ShareArray, [a_, b_, x_, y_]))

    f, g = await asyncio.gather(*[(a - x).open(), (b - y).open()])
    c = [(d*e).value + (d*q).v.value + (e*p).v.value + pq for (p, q, pq, d, e) in zip(x_, y_, z_, f, g)]
    return c


async def refine_triples(context, a_dirty, b_dirty, c_dirty):
    """This method takes dirty triples and refines them.

    Arguments:
        context {PassiveMpc} -- MPC context.
        a_dirty {list[Share]} -- Shares of first part of the triples.
        b_dirty {list[Share]} -- Shares of second part of the triples.
        c_dirty {list[Share]} -- Shares of first*second part of the triples.

    Returns:
        list[Share] -- Shares of first part of the refined triples.
        list[Share] -- Shares of second part of the refined triples.
        list[Share] -- Shares of first*second part of the refined triples.
    """

    assert len(a_dirty) == len(b_dirty) == len(c_dirty)
    m = len(a_dirty)
    d = m // 2 if m & m-1 == 0 else 2**(m-2).bit_length()
    zeroes = d - m
    omega = get_omega(context.field, 4*d, 2)
    a, b, c, x, y, z = rename_and_unpack_inputs(a_dirty, b_dirty, c_dirty, d, m)
    a_rest, b_rest, p, q = get_extrapolated_values(context.poly, a, b, d, omega)
    c_rest = await batch_beaver(context, a_rest, b_rest, x, y, z)
    c = list(itertools.chain(*zip(c, c_rest)))
    c_all = context.poly.interp_extrap(c, omega)
    pq = c_all[1::2]
    num_valid_triples = d - context.t + 1 - zeroes
    p_shares = map(context.Share, p[:num_valid_triples])
    q_shares = map(context.Share, q[:num_valid_triples])
    pq_shares = map(context.Share, pq[:num_valid_triples])
    return p_shares, q_shares, pq_shares
