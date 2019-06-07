from pytest import mark
from random import randint
from honeybadgermpc.elliptic_curve import Jubjub
from honeybadgermpc.progs.mimc import mimc_mpc_batch
from honeybadgermpc.progs.mixins.share_arithmetic import (
    BeaverMultiply,
    BeaverMultiplyArrays,
    InvertShare,
    InvertShareArray,
    DivideShares,
    DivideShareArrays,
    Equality,
)

CONFIG = {
    BeaverMultiply.name: BeaverMultiply(),
    BeaverMultiplyArrays.name: BeaverMultiplyArrays(),
    InvertShare.name: InvertShare(),
    InvertShareArray.name: InvertShareArray(),
    DivideShares.name: DivideShares(),
    DivideShareArrays.name: DivideShareArrays(),
    Equality.name: Equality(),
}

PREPROCESSING = ["rands", "triples", "zeros", "cubes", "bits"]
n, t = 4, 1
k = 300000

TEST_CURVE = Jubjub()
TEST_FIELD = Jubjub.Field
TEST_KEY = TEST_FIELD(randint(0, TEST_FIELD.modulus))


# All iterations take around 30min total.
@mark.parametrize("batch_size", [10 ** i for i in range(4)])
def test_benchmark_mimc_mpc_batch(batch_size, benchmark_runner):
    async def _prog(context):
        xs = [context.preproc.get_rand(context) for _ in range(batch_size)]
        await mimc_mpc_batch(context, xs, TEST_KEY)

    benchmark_runner(_prog, n, t, PREPROCESSING, k)
