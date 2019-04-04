from pytest import mark
from honeybadgermpc.field import GF
from honeybadgermpc.mpc import Subgroup
from honeybadgermpc.progs.mimc import mimc_mpc, mimc_plain
from honeybadgermpc.progs.mixins.share_arithmetic import BeaverMultiply

MIXINS = [BeaverMultiply()]
PREPROCESSING = ['rands', 'triples', 'zeros', 'cubes']
n, t = 3, 1
k = 10000


@mark.asyncio
async def test_mimc(test_preprocessing, test_runner):

    async def _prog(context):
        x = test_preprocessing.elements.get_zero(context)
        field = GF(Subgroup.BLS12_381)
        key = field(15)

        # Compute F_MiMC_mpc
        mm = await mimc_mpc(context, x, key)

        # open x, then compute F_MiMC_plain
        x_open = await x.open()
        mp = mimc_plain(x_open, key)

        # Compare the MPC evaluation to the plain one
        mm_ = await mm.open()
        assert mm_ == mp

    await test_runner(_prog, n, t, PREPROCESSING, k, MIXINS)
