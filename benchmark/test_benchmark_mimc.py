from pytest import mark
import asyncio
from random import randint
from honeybadgermpc.mpc import TaskProgramRunner
from honeybadgermpc.elliptic_curve import Jubjub
from honeybadgermpc.progs.mimc import mimc_mpc_batch
from honeybadgermpc.progs.mixins.share_arithmetic import (
    BeaverMultiply, BeaverMultiplyArrays, InvertShare, InvertShareArray, DivideShares,
    DivideShareArrays, Equality)

CONFIG = {
    BeaverMultiply.name: BeaverMultiply(),
    BeaverMultiplyArrays.name: BeaverMultiplyArrays(),
    InvertShare.name: InvertShare(),
    InvertShareArray.name: InvertShareArray(),
    DivideShares.name: DivideShares(),
    DivideShareArrays.name: DivideShareArrays(),
    Equality.name: Equality()
}

PREPROCESSING = ['rands', 'triples', 'zeros', 'cubes', 'bits']
n, t = 4, 1
k = 300000

TEST_CURVE = Jubjub()
TEST_FIELD = Jubjub.Field
TEST_KEY = TEST_FIELD(randint(0, TEST_FIELD.modulus))


@mark.parametrize("batch_size", [10**i for i in range(4)])
def test_benchmark_mimc_mpc_batch(
        batch_size, test_preprocessing, test_runner, benchmark):
    """ First iteration does all of the preprocessing,
    All iterations take around 30min total.
    """
    async def _prog(context):
        if batch_size == 1:
            return

        xs = [test_preprocessing.elements.get_rand(context) for _ in range(batch_size)]

        # Compute F_MiMC_mpc, mm - mimc_mpc
        await mimc_mpc_batch(context, xs, TEST_KEY)

    for kind in PREPROCESSING:
        test_preprocessing.generate(kind, n, t, k=k)

    program_runner = TaskProgramRunner(n, t, CONFIG)
    program_runner.add(_prog)
    loop = asyncio.get_event_loop()

    def _work():
        loop.run_until_complete(program_runner.join())

    benchmark(_work)
