from pytest import mark
from random import randint
from honeybadgermpc.field import GF
from honeybadgermpc.elliptic_curve import Subgroup
from honeybadgermpc.progs.mixins.share_arithmetic import BeaverMultiply
from honeybadgermpc.progs.mimc_symmetric import mimc_encrypt, mimc_decrypt

MIXINS = [BeaverMultiply()]
PREPROCESSING = ["rands", "triples", "zeros", "cubes", "bits"]
n, t = 4, 1
k = 1000


@mark.asyncio
async def test_mimc_symmetric(test_runner):
    field = GF(Subgroup.BLS12_381)
    plaintext = [randint(0, field.modulus)]
    key_ = field(randint(0, field.modulus))

    async def _prog(context):
        key = context.preproc.get_zero(context) + key_

        cipher = mimc_encrypt(key_, plaintext)
        decrypted_value = await mimc_decrypt(context, key, cipher)

        decrypted_open = await context.ShareArray(decrypted_value).open()
        assert decrypted_open == plaintext

    await test_runner(_prog, n, t, PREPROCESSING, k, MIXINS)
