from pytest import mark, raises
from honeybadgermpc.mpc import TaskProgramRunner
from honeybadgermpc.mixins import MixinOpName, BeaverTriple, Inverter
from honeybadgermpc.elliptic_curve import Ideal, Point, Jubjub
from progs.jubjub import SharedPoint, SharedIdeal
import asyncio

TEST_CURVE = Jubjub()

TEST_POINTS = [
    # zero
    Point(0, 1, TEST_CURVE),
    Point(5, 6846412461894745224441235558443359243034138132682534265960483512729196124138, TEST_CURVE),  # noqa: E501
    Point(10, 9069365299349881324022309154395348339753339814197599672892180073931980134853, TEST_CURVE),  # noqa: E501

    # equal to sum of last two elements
    Point(31969263762581634541702420136595781625976564652055998641927499388080005620826,
          31851650165997003853447983973612951129977622378317524209017259746316028027479,
          TEST_CURVE)
]


async def run_test_prog(prog, test_preprocessing=None, n=4, t=1, k=10000):
    if test_preprocessing is not None:
        test_preprocessing.generate("rands", n, t, k=k)
        test_preprocessing.generate("triples", n, t, k=k)

    program_runner = TaskProgramRunner(
        n, t, {
            MixinOpName.MultiplyShare: BeaverTriple.multiply_shares,
            MixinOpName.InvertShare: Inverter.invert_share})
    program_runner.add(prog)
    await(program_runner.join())


async def shared_point_equals(a, b):
    if a.curve != b.curve:
        return False
    elif type(a) != type(b):
        return False
    elif isinstance(a, (Ideal, SharedIdeal)):
        return True

    a_x, a_y, b_x, b_y = await asyncio.gather(
        a.xs.open(), a.ys.open(), b.xs.open(), b.ys.open())

    return (a_x, a_y) == (b_x, b_y)


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
async def test_shared_point_equals(test_preprocessing):
    async def _prog(context):
        p1 = await SharedPoint.from_point(context, TEST_POINTS[0])
        p2 = await SharedPoint.from_point(context, TEST_POINTS[1])
        p3 = await SharedPoint.create(context, context.Share(
            0), context.Share(1), Jubjub(Jubjub.Field(-2)))

        assert await shared_point_equals(p1, p1)
        assert not await shared_point_equals(p1, p2)
        assert not await shared_point_equals(p1, p3)

    await run_test_prog(_prog, test_preprocessing)


@mark.asyncio
async def test_contains_shared_point(test_preprocessing):
    async def _prog(context):
        # Will throw an exception if not on the curve
        await SharedPoint.create(context, context.Share(0), context.Share(1))

        with raises(ValueError):
            await SharedPoint.create(context, context.Share(0), context.Share(2))

    await run_test_prog(_prog, test_preprocessing)


@mark.asyncio
async def test_shared_point_creation_from_point(test_preprocessing):
    async def _prog(context):
        p1 = Point(0, 1)
        p1s = await SharedPoint.from_point(context, p1)
        p2 = await SharedPoint.create(context, context.Share(0), context.Share(1))
        assert await shared_point_equals(p1s, p2)

    await run_test_prog(_prog, test_preprocessing)


@mark.asyncio
async def test_shared_point_double(test_preprocessing):
    async def _prog(context):
        shared_points, actual_doubled = await asyncio.gather(
            asyncio.gather(*[SharedPoint.from_point(context, p) for p in TEST_POINTS]),
            asyncio.gather(*[SharedPoint.from_point(context, p.double())
                             for p in TEST_POINTS]))

        results = await asyncio.gather(*[p.double() for p in shared_points])

        assert all(await asyncio.gather(
            *[shared_point_equals(a, r) for a, r in zip(actual_doubled, results)]))

    await run_test_prog(_prog, test_preprocessing)


@mark.asyncio
async def test_shared_point_neg(test_preprocessing):
    async def _prog(context):
        shared_points, actual_negated = await asyncio.gather(
            asyncio.gather(
                *[SharedPoint.from_point(context, p) for p in TEST_POINTS]),
            asyncio.gather(
                *[SharedPoint.from_point(context, -p) for p in TEST_POINTS]))

        shared_negated = await asyncio.gather(*[s.neg() for s in shared_points])

        zipped = zip(actual_negated, shared_negated)
        assert all(await asyncio.gather(
            *[shared_point_equals(a, r) for a, r in zipped]))

    await run_test_prog(_prog, test_preprocessing)


@mark.asyncio
async def test_shared_point_add(test_preprocessing):
    async def _prog(context):
        ideal = SharedIdeal(TEST_CURVE)

        p1, p2, p3, p4 = await asyncio.gather(
            *[SharedPoint.from_point(context, point) for point in TEST_POINTS])

        r1, r2, r3 = await asyncio.gather(
            p2.add(ideal),
            p1.add(p2),
            p2.add(p3))

        assert all(await asyncio.gather(
            shared_point_equals(r1, p2),
            shared_point_equals(r2, p2),
            shared_point_equals(r3, p4)
        ))

    await run_test_prog(_prog, test_preprocessing)


@mark.asyncio
async def test_shared_point_sub(test_preprocessing):
    async def _prog(context):
        shared_points, actual_negated = await asyncio.gather(
            asyncio.gather(
                *[SharedPoint.from_point(context, p) for p in TEST_POINTS]),
            asyncio.gather(
                *[SharedPoint.from_point(context, -p) for p in TEST_POINTS]))

        # We're going to be testing that given point p, p - p == p + (-p)
        actual, result = await asyncio.gather(
            asyncio.gather(*[p.sub(p) for p in shared_points]),
            asyncio.gather(*[p1.add(p2)
                             for p1, p2 in zip(shared_points, actual_negated)]))

        assert all(await asyncio.gather(
            *[shared_point_equals(a, r) for a, r in zip(actual, result)]))

    await run_test_prog(_prog, test_preprocessing)


@mark.asyncio
async def test_shared_point_mul(test_preprocessing):
    async def _prog(context):
        p1 = await SharedPoint.from_point(context, TEST_POINTS[1])
        p1_double = await p1.double()
        p1_quad = await p1_double.double()
        p4 = await p1.mul(4)
        p5 = await p1.add(p4)
        p1_quint = await p1_quad.add(p1)

        assert await shared_point_equals(p1_quad, p4)
        assert await shared_point_equals(p1_quint, p5)

    await run_test_prog(_prog, test_preprocessing)


@mark.asyncio
async def test_shared_point_montgomery_mul(test_preprocessing):
    async def _prog(context):
        p1 = await SharedPoint.from_point(context, TEST_POINTS[1])
        p1_double = await p1.double()
        p1_quad = await p1_double.double()

        assert await shared_point_equals(
            p1_quad,
            await p1.montgomery_mul(4))

        assert await shared_point_equals(
            await p1_quad.add(p1),
            await p1.montgomery_mul(5))

    await run_test_prog(_prog, test_preprocessing)
