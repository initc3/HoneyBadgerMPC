from pytest import mark
from asyncio import gather
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
from honeybadgermpc.preprocessing import PreProcessedElements

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
n, t = 3, 1

FIELD = GF(Subgroup.BLS12_381)

p = FIELD.modulus
MAX = (p - 1) / 2
DIFF = 5
ranges = [0, p // 2 ** 128, p // 2 ** 64, p // 2 ** 32, p // 2 ** 16, MAX - DIFF]
range_pairs = [(x, y) for x, y in zip(ranges[:-1], ranges[1:])]


@mark.asyncio
@mark.parametrize("begin,end", range_pairs)
async def test_less_than(begin, end, test_runner):
    pp_elements = PreProcessedElements()
    pp_elements.generate_share_bits(50, n, t)
    a_values = [randint(begin, end) for _ in range(3)]
    b_values = [a_values[0] - DIFF, a_values[1], a_values[2] + DIFF]

    async def _prog(context):
        a_shares = [context.Share(v) for v in a_values]
        b_shares = [context.Share(v) for v in b_values]

        results = await gather(
            *[(a_ < b_).open() for a_, b_ in zip(a_shares, b_shares)]
        )

        for (res, a, b) in zip(results, a_values, b_values):
            assert bool(res) == (a < b)

    await test_runner(_prog, n, t, PREPROCESSING, 2500, STANDARD_ARITHMETIC_MIXINS)


@mark.asyncio
async def test_equality(test_runner):
    equality = Equality()

    async def _prog(context):
        share0 = context.preproc.get_zero(context)
        share1 = context.preproc.get_rand(context)
        share1_ = share0 + share1
        share2 = context.preproc.get_rand(context)

        assert await (await equality(context, share1, share1_)).open()
        assert await (share1 == share1_).open()
        assert not await (share1 == share2).open()

    await test_runner(_prog, n, t, PREPROCESSING, 1000, STANDARD_ARITHMETIC_MIXINS)
