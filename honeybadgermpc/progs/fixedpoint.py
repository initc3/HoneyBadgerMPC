import asyncio
import logging
import time

from honeybadgermpc.elliptic_curve import Subgroup
from honeybadgermpc.field import GF
from honeybadgermpc.mpc import TaskProgramRunner
from honeybadgermpc.preprocessing import (
    PreProcessedElements as FakePreProcessedElements,
)
from honeybadgermpc.progs.mixins.share_arithmetic import BeaverMultiply, MixinConstants


config = {MixinConstants.MultiplyShare: BeaverMultiply()}
"""
Secure Computation With Fixed-Point Numbers
Catrina and Saxena
http://www.ifca.ai/pub/fc10/31_47.pdf
"""


# Fixed Point parameters

F = 32  # The precision (binary bits)
"""
This implementation of the library is not completely hiding. This leaks information about the bits used in computation which is determinied by the security parameter Kappa.
In particular, we leak O(1/(2^Kappa)) information theorotic bits per operation on a floating point secret.
"""
KAPPA = 32  # Statistical security parameter
K = 64  # Total number of padding bits ()
p = modulus = Subgroup.BLS12_381
Field = GF(p)

"""
Library for fixed point operations:
Throughout the code:
`x` stands for private floating point number
`k` is the total of number of bits we are representing

"""


# General (non MPC) fixed point functions
""" Change a function to fixed point form. In general when we are dealing with fixed points, it
is convert them back to fixed form.

2.5 with f = 32 goes to 2.5* 2**32 which is an int.
Note that this function always rounds down the error
"""


def to_fixed_point_repr(x, f=F):
    return int(x * 2 ** f)


"""
Convert a number back from fixed point int form to python float.
x: number to be converted.
changes an int `x` to float value `x`/2**f deafult F=32
"""


def from_fixed_point_repr(x, k=K, f=F, signed=True):
    x = x.value
    if x >= 2 ** (k - 1) and signed:
        x = -(p - x)

    return float(x) / 2 ** f


"""
Convert x to a k-bit representation
Least significant bit first
"""


def binary_repr(x, k):
    assert isinstance(x, int)
    try:
        bin_str = f"{x:0{k}b}"
    except ValueError:
        raise TypeError("x must be an integer")
    return [int(i) for i in bin_str[::-1]]


# MPC operations for fixed point
# Get a random integer from [0  ... 2**m -1) range or m bit random number
async def random2m(ctx, m):
    result = ctx.Share(0)
    bits = []
    for i in range(m):
        bits.append(ctx.preproc.get_bit(ctx))
        result = result + Field(2) ** i * bits[-1]

    return result, bits


"""
truncate `m` least significant bits from x. `k` is the total of number of bits we are representing.
Return the shares of the trancated number,
"""


async def trunc_pr(ctx, x, k, m):
    """
    k: Maximum number of bits
    m: Truncation bits
    """
    assert k > m
    r1, _ = await random2m(ctx, m)
    r2, _ = await random2m(ctx, k + KAPPA - m)
    r2 = ctx.Share(r2.v * Field(2) ** m)
    c = await (x + Field(2 ** (k - 1)) + r1.v + r2.v).open()
    c2 = c.value % (2 ** m)
    d = ctx.Share((x.v - Field(c2) + r1.v) * ~(Field(2) ** m))
    return d


"""
Add a_bits and b_bits vectors and return the final carry bit. This is used in substracting numbers `a` and `b`
If the `a` + (1^n - `b`) has a carry bit then a > b. where 1^n represents the all one vector.
"""


async def get_carry_bit(ctx, a_bits, b_bits, low_carry_bit=1):
    a_bits.reverse()
    b_bits.reverse()
    assert len(a_bits) == len(b_bits)

    async def _bit_ltl_reduce(x):
        if len(x) == 1:
            return x[0]
        carry1, all_one1 = await _bit_ltl_reduce(x[: len(x) // 2])
        carry2, all_one2 = await _bit_ltl_reduce(x[len(x) // 2 :])
        return carry1 + (await (all_one1 * carry2)), (await (all_one1 * all_one2))

    carry_bits = [(await (ai * bi)) for ai, bi in zip(a_bits, b_bits)]
    all_one_bits = [
        ctx.Share(ai.v + bi.v - 2 * carryi.v)
        for ai, bi, carryi in zip(a_bits, b_bits, carry_bits)
    ]
    carry_bits.append(ctx.Share(low_carry_bit))
    all_one_bits.append(ctx.Share(0))
    return (await _bit_ltl_reduce(list(zip(carry_bits, all_one_bits))))[0]


"""
This is used in substracting numbers `a` and `b_bits`.
a is a known public number and b_bits is a secret shared array.
This algorithm computes whether a + int(1^n - b) has a carry bit.
In other words, we check whether number created from the secret shared bit decompation of the b_bits,
`b` is less than publically known `a`.
"""


async def bit_ltl(ctx, a, b_bits):
    """
    a: Public
    b: List of private bit shares. Least significant digit first
    """
    b_bits = [ctx.Share(Field(1) - bi.v) for bi in b_bits]
    a_bits = [ctx.Share(ai) for ai in binary_repr(int(a), len(b_bits))]

    carry = await get_carry_bit(ctx, a_bits, b_bits)
    return ctx.Share(Field(1) - carry.v)


"""
Given the secret shared [x] calcuate the secret shares of [x//(2^m)].
// operator represents integer division. 9//4 = 2
x is a secret shared floating point value and m is a known public value.
k is the total number of bits for the floating point number.
returns the secret shares of [x//2^m]
"""


async def div2m(ctx, x, k, m):
    r1, r1_bits = await random2m(ctx, m)
    r2, _ = await random2m(ctx, k + KAPPA - m)
    r2 = ctx.Share(r2.v * Field(2) ** m)

    c = await (x + r2 + r1 + Field(2) ** (k - 1)).open()
    c2 = int(c) % (2 ** m)
    u = await bit_ltl(ctx, c2, r1_bits)
    a2 = ctx.Share(Field(c2) - r1.v + (2 ** m) * u.v)
    return a2


"""
Given the secret shared [x] calcuate the secret shares of [x%2^m] for known  public m.
This is calcuated by first calculating the value of [x//2^m] usiinig div2m and substracting that from [x]


This function takes in as arugment secret shares [x] of a floating point number,
`k` the total number of bits we are representing and `m` the truncation modulas.
Returns the (share)value: [x % 2^m]
"""


async def trunc(ctx, x, k, m):
    a2 = await div2m(ctx, x, k, m)
    d = ctx.Share((x.v - a2.v) / (Field(2)) ** m)
    return d


class FixedPoint:
    def __init__(self, ctx, x):
        self.ctx = ctx
        if isinstance(x, (float, int)):
            self.share = ctx.preproc.get_zero(ctx) + ctx.Share(int(x * 2 ** F))
        elif type(x) is ctx.Share:
            self.share = x
        else:
            raise NotImplementedError

    def __add__(self, x):
        if type(x) is FixedPoint:
            return FixedPoint(self.ctx, self.share + x.share)

    def __sub__(self, x):
        if type(x) is FixedPoint:
            return FixedPoint(self.ctx, self.share - x.share)
        raise NotImplementedError

    """
    TODO: replacing * in __mul__ in a await statement does not work.

    Multiplty the two number using normal multiplication of numbers.
    Truncate the last F bits of resulting 2*K bit number.
    """

    async def __mul__(self, x):
        if type(x) is FixedPoint:
            start_time = time.time()
            res_share = await (self.share * x.share)
            end_time = time.time()
            logging.info("Multiplication time: %.2f", end_time - start_time)
            start_time = time.time()
            res_share = await trunc_pr(self.ctx, res_share, 2 * K, F)
            end_time = time.time()
            logging.info("Trunc time: %.2f", end_time - start_time)
            return FixedPoint(self.ctx, res_share)
        raise NotImplementedError

    async def open(self):
        x = (await self.share.open()).value
        if x >= 2 ** (K - 1):
            x = -(p - x)
        return float(x) / 2 ** F

    def neg(self):
        return FixedPoint(self.ctx, Field(-1) * self.share)

    """
    Compute the last K-1 bits and check if the resulting number is 0 or 1.
    """

    async def ltz(self):
        t = await trunc(self.ctx, self.share, K, K - 1)
        return self.ctx.Share(-t.v)

    """
    Check whether the self is than is x.
    """

    async def lt(self, x):
        return await (self - x).ltz()

    async def div(self, x):
        if type(x) in [float, int]:
            return await self.__mul__(FixedPoint(self.ctx, 1.0 / x))
        raise NotImplementedError


async def _prog(ctx):
    ctx.preproc = FakePreProcessedElements()
    logging.info("Starting _prog")
    a = FixedPoint(ctx, 2.5)
    b = FixedPoint(ctx, -3.8)
    A = await a.open()  # noqa: F841, N806
    B = await b.open()  # noqa: F841, N806
    AplusB = await (a + b).open()  # noqa: N806
    AminusB = await (a - b).open()  # noqa: N806
    AtimesB = await (await a.__mul__(b)).open()  # noqa: N806
    AltB = await (await a.lt(b)).open()  # noqa: N806
    BltA = await (await b.lt(a)).open()  # noqa: N806
    logging.info("done")
    logging.info(f"A:{A} B:{B} A-B:{AminusB} A+B:{AplusB}")
    logging.info(f"A*B:{AtimesB} A<B:{AltB} B<A:{BltA}")
    logging.info("Finished _prog")


async def tutorial_fixedpoint():
    n, t = 4, 1
    pp = FakePreProcessedElements()
    pp.generate_zeros(100, n, t)
    pp.generate_triples(1000, n, t)
    pp.generate_bits(1000, n, t)
    program_runner = TaskProgramRunner(n, t, config)
    program_runner.add(_prog)
    results = await program_runner.join()
    return results


def main():
    # Run the tutorials
    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    loop.run_until_complete(tutorial_fixedpoint())


if __name__ == "__main__":
    main()
