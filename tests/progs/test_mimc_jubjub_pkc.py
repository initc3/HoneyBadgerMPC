from pytest import mark
import asyncio
from honeybadgermpc.field import GF
from honeybadgermpc.mpc import Subgroup
from honeybadgermpc.progs.mixins.share_arithmetic import (
    BeaverMultiply,
    BeaverMultiplyArrays,
    InvertShare,
    InvertShareArray,
    DivideShares,
    DivideShareArrays,
)
from honeybadgermpc.progs.mixins.share_comparison import Equality
from honeybadgermpc.progs.mimc_jubjub_pkc import (
    mimc_encrypt,
    mimc_decrypt,
    key_generation,
)

STANDARD_ARITHMETIC_MIXINS = [
    BeaverMultiply(),
    BeaverMultiplyArrays(),
    InvertShare(),
    InvertShareArray(),
    DivideShares(),
    DivideShareArrays(),
    Equality(),
]

PREPROCESSING = ["rands", "triples", "zeros", "cubes", "bits"]
n, t = 4, 1
k = 1000


@mark.asyncio
async def test_mimc_jubjub_pkc(test_runner):

    field = GF(Subgroup.BLS12_381)
    plaintext = [field.random().value]
    seed = field.random().value

    async def _prog(context):
        # Key Generation
        priv_key, pub_key = await key_generation(context)

        # Encryption & Decryption
        cipher = mimc_encrypt(pub_key, plaintext, seed)
        decrypted_value = await mimc_decrypt(context, priv_key, cipher)
        decrypted = await asyncio.gather(*[d.open() for d in decrypted_value])

        assert decrypted == plaintext

    await test_runner(_prog, n, t, PREPROCESSING, k, STANDARD_ARITHMETIC_MIXINS)
