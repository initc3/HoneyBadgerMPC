from .mpc import Poly, Field
from .polynomial import get_omega
import asyncio
import itertools


def rename_and_unpack_inputs(a_, b_, c_, d, m):
    n = m // 2  # number of triples

    def pad(arr, k): return arr + [Field(0)]*(d-len(arr))
    a, b, c = pad(a_[:n], d), pad(b_[:n], d), pad(c_[:n], d)
    x, y, z = pad(a_[n:], d), pad(b_[n:], d), pad(c_[n:], d)

    return a, b, c, x, y, z


def get_extrapolated_values(a, b, d, omega):
    a_ = Poly.interp_extrap(Poly.interp_extrap(a, omega**2), omega)
    b_ = Poly.interp_extrap(Poly.interp_extrap(b, omega**2), omega)
    return a_[2::4], b_[2::4], a_[1::2], b_[1::2]


async def batch_beaver(context, a, b, x, y, z):
    # TODO: Replace this with a batch implementation instead of having a loop
    c = []
    assert len(a) == len(b) == len(x) == len(y) == len(z)
    for _a, _b, _x, _y, _z in zip(a, b, x, y, z):
        d, e = context.Share(_a - _x).open(), context.Share(_b - _y).open()
        c.append(d*e + d*_y + e*_x + _z)
    return await asyncio.gather(*c)


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
    omega = get_omega(Field, 4*d, 2)
    a, b, c, x, y, z = rename_and_unpack_inputs(a_dirty, b_dirty, c_dirty, d, m)
    a_rest, b_rest, p, q = get_extrapolated_values(a, b, d, omega)
    c_rest = await batch_beaver(context, a_rest, b_rest, x, y, z)
    c = list(itertools.chain(*zip(c, c_rest)))
    c_all = Poly.interp_extrap(c, omega)
    pq = c_all[1::2]
    num_valid_triples = d - context.t + 1 - zeroes
    p_shares = map(context.Share, p[:num_valid_triples])
    q_shares = map(context.Share, q[:num_valid_triples])
    pq_shares = map(context.Share, pq[:num_valid_triples])
    return p_shares, q_shares, pq_shares
