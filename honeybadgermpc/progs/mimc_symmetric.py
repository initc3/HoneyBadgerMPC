import asyncio
from honeybadgermpc.field import GF
from honeybadgermpc.elliptic_curve import Subgroup
from honeybadgermpc.progs.mimc import mimc_mpc, mimc_plain

field = GF(Subgroup.BLS12_381)


def mimc_encrypt(key, ms):
    """
    ms - blocks of plaintext, that is, plaintext -> {m1, m2,...,ml}
         Each plaintext is a field element.
    ciphertext <- F_MiMC(counter, key) + plaintext
    """
    return [mimc_plain(idx, key) + m for (idx, m) in enumerate(ms)]


async def mimc_decrypt(context, key, cs):
    """
    plaintext <- F_MiMC(counter, key) - ciphertext
    """
    mpcs = await asyncio.gather(
        *[mimc_mpc(context, context.field(i), key) for i in range(len(cs))]
    )
    decrypted = [c - m for (c, m) in zip(cs, mpcs)]

    return decrypted
