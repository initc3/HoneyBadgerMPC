from pytest import mark
from honeybadgermpc.progs.jubjub import SharedPoint, share_mul
from honeybadgermpc.progs.mixins.share_arithmetic import (
    BeaverMultiply,
    BeaverMultiplyArrays,
    InvertShare,
    InvertShareArray,
    DivideShares,
    DivideShareArrays,
    Equality,
)
from honeybadgermpc.elliptic_curve import Jubjub, Point


MIXINS = [
    BeaverMultiply(),
    BeaverMultiplyArrays(),
    InvertShare(),
    InvertShareArray(),
    DivideShares(),
    DivideShareArrays(),
    Equality(),
]

TEST_PREPROCESSING = ["rands", "triples", "bits"]

TEST_CURVE = Jubjub()
TEST_POINT = Point(
    5,
    6846412461894745224441235558443359243034138132682534265960483512729196124138,
    TEST_CURVE,
)  # noqa: E501

ALL_BIT_NUMBERS = [int(f"0b{'1' * i}", 2) for i in [1, 64, 128]]

n, t = 4, 1
k = 50000
COUNT_MAX = 2


def run_benchmark(
    runner, prog, n=n, t=t, mixins=MIXINS, preprocessing=TEST_PREPROCESSING, k=k
):
    runner(prog, n, t, preprocessing, k, mixins)


def test_benchmark_shared_point_add(benchmark_runner):
    async def _prog(context):
        result = SharedPoint.from_point(context, TEST_POINT)
        result = result.add(result)
        await result.open()

    run_benchmark(benchmark_runner, _prog)


def test_benchmark_shared_point_double(benchmark_runner):
    async def _prog(context):
        result = SharedPoint.from_point(context, TEST_POINT)
        result = result.double()
        await result.open()

    run_benchmark(benchmark_runner, _prog)


# The following tests are parametrized on multiplier, as the more set bits
# in the multiplicand, the longer the operation takes.


@mark.parametrize("multiplier", ALL_BIT_NUMBERS)
def test_benchmark_shared_point_mul(benchmark_runner, multiplier):
    async def _prog(context):
        base = SharedPoint.from_point(context, TEST_POINT)
        result = base.mul(multiplier)
        await result.open()

    run_benchmark(benchmark_runner, _prog)


@mark.parametrize("multiplier", ALL_BIT_NUMBERS)
def test_benchmark_shared_point_montgomery_mul(benchmark_runner, multiplier):
    async def _prog(context):
        base = SharedPoint.from_point(context, TEST_POINT)
        result = base.montgomery_mul(multiplier)
        await result.open()

    run_benchmark(benchmark_runner, _prog)


@mark.parametrize("bit_length", list(range(64, 257, 64)))
def test_benchmark_share_mul(bit_length, benchmark_runner):
    p = TEST_POINT

    async def _prog(context):
        m_bits = [context.preproc.get_bit(context) for i in range(bit_length)]

        multiplier_ = Jubjub.Field(0)
        for idx, m_b in enumerate(m_bits):
            multiplier_ += (2 ** idx) * m_b

        # Compute share_mul
        p1_ = await share_mul(context, m_bits, p)
        await p1_.open()

    run_benchmark(benchmark_runner, _prog)
