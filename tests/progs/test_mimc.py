from pytest import mark
from random import randint
from honeybadgermpc.field import GF
from honeybadgermpc.mpc import Subgroup
from honeybadgermpc.progs.mimc import mimc_mpc, mimc_plain, mimc_mpc_batch
from honeybadgermpc.progs.mixins.share_arithmetic import BeaverMultiply

MIXINS = [BeaverMultiply()]
PREPROCESSING = ["rands", "triples", "zeros", "cubes"]
n, t = 4, 1
k = 3500


@mark.asyncio
async def test_mimc(test_runner):
    async def _prog(context):
        x = context.preproc.get_zero(context)
        field = GF(Subgroup.BLS12_381)
        key = field(15)

        # Compute F_MiMC_mpc
        mm = await mimc_mpc(context, x, key)
        mm_open = await mm.open()

        # open x, then compute F_MiMC_plain
        x_open = await x.open()
        mp = mimc_plain(x_open, key)

        # Compare the MPC evaluation to the plain one
        assert mm_open == mp

    await test_runner(_prog, n, t, PREPROCESSING, k, MIXINS)


@mark.asyncio
async def test_mimc_mpc_batch(test_runner):
    field = GF(Subgroup.BLS12_381)
    key = field(randint(0, field.modulus))

    async def _prog(context):
        xs = [context.preproc.get_rand(context) for _ in range(20)]

        # Compute F_MiMC_mpc, mm - mimc_mpc
        mm = await mimc_mpc_batch(context, xs, key)
        mm_open = await context.ShareArray(mm).open()

        # open x, then compute F_MiMC_plain, mp - mimc_plain
        xs_open = await context.ShareArray(xs).open()
        mp = [mimc_plain(x, key) for x in xs_open]

        # Compare the MPC evaluation to the plain one
        assert mm_open == mp

    await test_runner(_prog, n, t, PREPROCESSING, k, MIXINS)
