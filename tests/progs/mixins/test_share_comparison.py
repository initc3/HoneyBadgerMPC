import logging
from pytest import mark
from random import randint
from honeybadgermpc.field import GF
from honeybadgermpc.mpc import Subgroup
from honeybadgermpc.progs.mixins.share_arithmetic import (
    BeaverMultiply,
    BeaverMultiplyArrays,
    InvertShare,
    InvertShareArray,
    DivideShares,
    DivideShareArrays,
)
from honeybadgermpc.progs.mixins.share_comparison import Equality, LessThan

STANDARD_ARITHMETIC_MIXINS = [
    BeaverMultiply(),
    BeaverMultiplyArrays(),
    InvertShare(),
    InvertShareArray(),
    DivideShares(),
    DivideShareArrays(),
    Equality(),
    LessThan(),
]

PREPROCESSING = ["rands", "triples", "zeros", "cubes", "bits"]
n, t = 4, 1
k = 10000

FIELD = GF(Subgroup.BLS12_381)

p = FIELD.modulus
MAX = (p - 1) / 2
DIFF = 5
ranges = [0, p // 2 ** 128, p // 2 ** 64, p // 2 ** 32, p // 2 ** 16, MAX - DIFF]
range_pairs = [(x, y) for x, y in zip(ranges[:-1], ranges[1:])]


@mark.asyncio
@mark.parametrize("begin,end", range_pairs)
async def test_less_than(begin, end, test_preprocessing, test_runner):
    test_preprocessing.generate("share_bits", n, t, k=50)
    a_values = [randint(begin, end) for _ in range(3)]
    b_values = [a_values[0] - DIFF, a_values[1], a_values[2] + DIFF]

    async def _prog(context):
        a_shares = [context.Share(v) for v in a_values]
        b_shares = [context.Share(v) for v in b_values]

        for (a_, b_, a, b) in zip(a_shares, b_shares, a_values, b_values):
            if context.myid == 0:
                logging.info(f"a: {a}; b: {b}")
            res = bool(await (a_ < b_).open())
            assert res == (a < b)

    await test_runner(_prog, n, t, PREPROCESSING, k, STANDARD_ARITHMETIC_MIXINS)


@mark.asyncio
async def test_equality(test_preprocessing, test_runner):
    equality = Equality()

    async def _prog(context):
        share0 = test_preprocessing.elements.get_zero(context)
        share1 = test_preprocessing.elements.get_rand(context)
        share1_ = share0 + share1
        share2 = test_preprocessing.elements.get_rand(context)

        assert await (await equality(context, share1, share1_)).open()
        assert await (share1 == share1_).open()
        assert not await (share1 == share2).open()

    await test_runner(_prog, n, t, PREPROCESSING, k, STANDARD_ARITHMETIC_MIXINS)
