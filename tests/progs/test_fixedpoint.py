import random

from pytest import mark

from honeybadgermpc.preprocessing import (
    PreProcessedElements as FakePreProcessedElements,
)
from honeybadgermpc.progs.fixedpoint import FixedPoint
from honeybadgermpc.progs.mixins.share_arithmetic import BeaverMultiply, MixinConstants

config = {MixinConstants.MultiplyShare: BeaverMultiply()}


STANDARD_ARITHMETIC_MIXINS = [BeaverMultiply()]

STANDARD_PREPROCESSING = ["triples", "bits", "zeros"]

n, t = 4, 1


async def run_test_program(
    prog, test_runner, n=n, t=t, k=1000, mixins=STANDARD_ARITHMETIC_MIXINS
):

    return await test_runner(prog, n, t, STANDARD_PREPROCESSING, k, mixins)


def approx_equal(value, expected, epsilon=0.0001):
    return abs(value - expected) <= epsilon


@mark.asyncio
async def test_fixedpoint_addsub(test_preprocessing, test_runner):
    aval = random.random() * 100
    bval = random.random() * -100

    async def _prog(context):
        context.preproc = FakePreProcessedElements()
        a = FixedPoint(context, aval)
        b = FixedPoint(context, bval)

        assert approx_equal(await a.open(), aval)
        assert approx_equal(await b.open(), bval)

        assert approx_equal(await (a - b).open(), aval - bval)
        assert approx_equal(await (a + b).open(), aval + bval)

    await run_test_program(_prog, test_runner)


@mark.asyncio
async def test_fixedpoint_mul(test_preprocessing, test_runner):
    iters = 1
    aval = [random.random() * 100 for _ in range(0, iters)]
    bval = [random.random() * -100 for _ in range(0, iters)]

    async def _prog(context):
        context.preproc = FakePreProcessedElements()
        for i in range(0, iters):
            a = FixedPoint(context, aval[i])
            b = FixedPoint(context, bval[i])
            c = await a.__mul__(b)

            assert approx_equal(await c.open(), aval[i] * bval[i])

    await run_test_program(_prog, test_runner)


@mark.asyncio
async def test_fixedpoint_comparison(test_preprocessing, test_runner):
    iters = 1
    aval = [random.random() * 100 for _ in range(0, iters)]
    bval = [random.random() * -100 for _ in range(0, iters)]

    async def _prog(context):
        context.preproc = FakePreProcessedElements()
        for i in range(0, iters):
            a = FixedPoint(context, aval[i])
            b = FixedPoint(context, bval[i])

            assert await (await a.ltz()).open() == 0
            assert await (await b.ltz()).open() == 1

    await run_test_program(_prog, test_runner)
