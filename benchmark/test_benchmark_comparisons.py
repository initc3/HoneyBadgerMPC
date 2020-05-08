from pytest import mark

from honeybadgermpc.progs.fixedpoint import FixedPoint

from honeybadgermpc.progs.mixins.share_arithmetic import (
    BeaverMultiply,
    BeaverMultiplyArrays,
    DivideShareArrays,
    DivideShares,
    InvertShare,
    InvertShareArray,
)
from honeybadgermpc.progs.mixins.share_comparison import Equality

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


@mark.parametrize("comparator", ALL_BIT_NUMBERS)
def test_benchmark_fixedpoint_lt(benchmark_runner, comparator):
    async def _prog(context):
        base = FixedPoint(
            context,
            6846412461894745224441235558443359243034138132682534265960483512729196124138,
        )
        result = await base.lt(FixedPoint(context, comparator))
        await result.open()

    run_benchmark(benchmark_runner, _prog)


@mark.parametrize("comparator", ALL_BIT_NUMBERS)
def test_benchmark_share_eq(benchmark_runner, comparator):
    equality = Equality()

    async def _prog(context):
        base = context.Share(
            6846412461894745224441235558443359243034138132682534265960483512729196124138
        )
        comp = context.Share(comparator)
        result = await equality(context, base, comp)
        await result.open()

    run_benchmark(benchmark_runner, _prog)
