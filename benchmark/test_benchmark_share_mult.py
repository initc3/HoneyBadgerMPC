from pytest import mark

from honeybadgermpc.progs.fixedpoint import FixedPoint, from_fixed_point_repr

from random import randint

from honeybadgermpc.progs.mixins.dataflow import Share, ShareFuture
from honeybadgermpc.progs.mixins.share_arithmetic import (
    BeaverMultiply,
    BeaverMultiplyArrays,
    DivideShareArrays,
    DivideShares,
    InvertShare,
    InvertShareArray,
)
from honeybadgermpc.progs.mixins.share_comparison import (
    Equality
)

MIXINS = [
    BeaverMultiply(),
    BeaverMultiplyArrays(),
    InvertShare(),
    InvertShareArray(),
    DivideShares(),
    DivideShareArrays(),
    Equality(),
]

TEST_PREPROCESSING = ["rands", "triples", "zeros", "cubes", "bits"]

ALL_BIT_NUMBERS = [int(f"0b{'1' * i}", 2) for i in [1, 64, 128, 256]]

n, t = 4, 1
k = 50000
COUNT_MAX = 2


def run_benchmark(
    runner, prog, n=n, t=t, preprocessing=TEST_PREPROCESSING, k=k, mixins=MIXINS
):
    runner(prog, n, t, preprocessing, k, mixins)



@mark.parametrize("multiplier", ALL_BIT_NUMBERS)
def test_benchmark_beaver_mul_shares(benchmark_runner, multiplier):
    multiply = BeaverMultiply()
    async def _prog(context):
        base = context.Share(6846412461894745224441235558443359243034138132682534265960483512729196124138)
        mult = context.Share(multiplier)
        result = await multiply(context, base, mult)
        await result.open()

    run_benchmark(benchmark_runner, _prog)
