import asyncio
from copy import copy
from pytest import mark
from honeybadgermpc.elliptic_curve import Ideal, Point, Jubjub
from honeybadgermpc.progs.jubjub import SharedPoint, SharedIdeal, share_mul
from honeybadgermpc.progs.mixins.share_arithmetic import (
    BeaverMultiply,
    BeaverMultiplyArrays,
    InvertShare,
    InvertShareArray,
    DivideShares,
    DivideShareArrays,
)
from honeybadgermpc.progs.mixins.share_comparison import Equality

TEST_CURVE = Jubjub()

TEST_POINTS = [
    # zero
    Point(0, 1, TEST_CURVE),
    Point(
        5,
        6846412461894745224441235558443359243034138132682534265960483512729196124138,
        TEST_CURVE,
    ),  # noqa: E501
    Point(
        10,
        9069365299349881324022309154395348339753339814197599672892180073931980134853,
        TEST_CURVE,
    ),  # noqa: E501
    # equal to sum of last two elements
    Point(
        31969263762581634541702420136595781625976564652055998641927499388080005620826,
        31851650165997003853447983973612951129977622378317524209017259746316028027479,
        TEST_CURVE,
    ),
]

STANDARD_ARITHMETIC_MIXINS = [
    BeaverMultiply(),
    BeaverMultiplyArrays(),
    InvertShare(),
    InvertShareArray(),
    DivideShares(),
    DivideShareArrays(),
    Equality(),
]

STANDARD_PREPROCESSING = ["rands", "triples", "bits"]

n, t = 3, 1


async def run_test_program(
    prog, test_runner, n=n, t=t, k=1000, mixins=STANDARD_ARITHMETIC_MIXINS
):

    return await test_runner(prog, n, t, STANDARD_PREPROCESSING, k, mixins)


async def shared_point_equals(a_, b_):
    """Test utility function-- opens the two shared points, and
    then compares them that way. This should be faster than calling
    the secret shared equality function
    """
    a, b = await asyncio.gather(a_.open(), b_.open())
    return a == b


def test_basic_point_functionality():
    p1 = TEST_POINTS[0]
    ideal = Ideal(TEST_CURVE)

    assert TEST_CURVE.contains_point(p1)
    assert 2 * p1 == p1
    assert p1.double() == 2 * p1

    p2 = TEST_POINTS[1]
    assert p2 + ideal == p2
    assert p1 + p2 == p2
    assert p2.double() == p2 * 2
    assert -2 * p2 == 2 * (-p2)
    assert p2 - p2 == p1

    p3 = TEST_POINTS[2]
    assert p2 + p3 == TEST_POINTS[3]
    assert p2 != p3

    assert p3[0] == 10


@mark.asyncio
async def test_shared_point_equals(test_runner):
    async def _prog(context):
        p1 = SharedPoint.from_point(context, TEST_POINTS[0])
        p2 = SharedPoint.from_point(context, TEST_POINTS[1])

        # Different curve
        t3 = copy(TEST_POINTS[0])
        t3.curve = Jubjub(Jubjub.Field(-2))
        p3 = SharedPoint.from_point(context, t3)

        p4 = SharedIdeal(TEST_CURVE)

        eqs = await asyncio.gather(
            *[
                shared_point_equals(p1, p1),
                shared_point_equals(p1, p2),
                shared_point_equals(p1, p3),
                shared_point_equals(p1, p4),
            ]
        )

        assert [True, False, False, False] == eqs

    await run_test_program(_prog, test_runner)


@mark.asyncio
async def test_shared_point_creation_from_point(test_runner):
    async def _prog(context):
        p1 = Point(0, 1)
        p1s = SharedPoint.from_point(context, p1)
        assert await p1s.open() == p1

    await run_test_program(_prog, test_runner)


@mark.asyncio
async def test_shared_point_double(test_runner):
    async def _prog(context):
        shared_points = [SharedPoint.from_point(context, p) for p in TEST_POINTS]
        actual_doubled = [
            SharedPoint.from_point(context, p.double()) for p in TEST_POINTS
        ]

        results = [p.double() for p in shared_points]
        assert all(
            await asyncio.gather(
                *[shared_point_equals(a, r) for a, r in zip(actual_doubled, results)]
            )
        )

    await run_test_program(_prog, test_runner)


@mark.asyncio
async def test_shared_point_neg(test_runner):
    async def _prog(context):
        shared_points = [SharedPoint.from_point(context, p) for p in TEST_POINTS]
        actual_negated = [SharedPoint.from_point(context, -p) for p in TEST_POINTS]

        shared_negated = [s.neg() for s in shared_points]

        zipped = zip(actual_negated, shared_negated)
        assert all(
            await asyncio.gather(*[shared_point_equals(a, r) for a, r in zipped])
        )

    await run_test_program(_prog, test_runner)


@mark.asyncio
async def test_shared_point_add(test_runner):
    async def _prog(context):
        ideal = SharedIdeal(TEST_CURVE)

        p1, p2, p3, p4 = [
            SharedPoint.from_point(context, point) for point in TEST_POINTS
        ]

        r1, r2, r3 = p2.add(ideal), p1.add(p2), p2.add(p3)

        assert all(
            await asyncio.gather(
                shared_point_equals(r1, p2),
                shared_point_equals(r2, p2),
                shared_point_equals(r3, p4),
            )
        )

    await run_test_program(_prog, test_runner)


@mark.asyncio
async def test_shared_point_sub(test_runner):
    async def _prog(context):
        shared_points = [SharedPoint.from_point(context, p) for p in TEST_POINTS]
        actual_negated = [SharedPoint.from_point(context, -p) for p in TEST_POINTS]

        # We're going to be testing that given point p, p - p == p + (-p)
        actual = [p.sub(p) for p in shared_points]
        result = [p1.add(p2) for p1, p2 in zip(shared_points, actual_negated)]

        assert all(
            await asyncio.gather(
                *[shared_point_equals(a, r) for a, r in zip(actual, result)]
            )
        )

    await run_test_program(_prog, test_runner)


@mark.asyncio
async def test_shared_point_mul(test_runner):
    async def _prog(context):
        p1 = SharedPoint.from_point(context, TEST_POINTS[1])
        p1_double = p1.double()
        p1_quad = p1_double.double()
        p4 = p1.mul(4)
        p5 = p1.add(p4)
        p1_quint = p1_quad.add(p1)

        assert await shared_point_equals(p1_quad, p4)
        assert await shared_point_equals(p1_quint, p5)

    await run_test_program(_prog, test_runner)


@mark.asyncio
async def test_shared_point_montgomery_mul(test_runner):
    async def _prog(context):
        p1 = SharedPoint.from_point(context, TEST_POINTS[1])
        p1_double = p1.double()
        p1_quad = p1_double.double()

        assert await shared_point_equals(p1_quad, p1.montgomery_mul(4))

        assert await shared_point_equals(p1_quad.add(p1), p1.montgomery_mul(5))

    await run_test_program(_prog, test_runner)


@mark.asyncio
async def test_share_mul(test_runner):
    bit_length = 40  # Short key for testing

    async def _prog(context):
        p = TEST_POINTS[1]

        multiplier_ = Jubjub.Field(0)
        m_bits = [context.preproc.get_bit(context) for i in range(bit_length)]

        for idx, m in enumerate(m_bits):
            multiplier_ += (2 ** idx) * m

        # Compute share_mul
        p1_ = await share_mul(context, m_bits, p)
        result = await p1_.open()

        # Assertation
        multiplier = await multiplier_.open()
        if multiplier == Jubjub.Field(0):
            assert result == p
        else:
            assert result == int(multiplier) * p

        q1_ = await share_mul(context, m_bits, Ideal(TEST_CURVE))
        q2_ = SharedIdeal(TEST_CURVE)
        assert await shared_point_equals(q1_, q2_)

    await run_test_program(_prog, test_runner)
