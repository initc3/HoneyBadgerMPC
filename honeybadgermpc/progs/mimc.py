from math import log, ceil
from honeybadgermpc.mpc import PreProcessedElements, Subgroup

# ROUND: iteration time of MiMC encryption function,
# In BLS12_381, r = ceil(log(p, 3)) = 161
ROUND = ceil(log(Subgroup.BLS12_381, 3))


async def mimc_mpc(context, x, k):
    """
    MiMC block cipher encryption encrypts message x with secret key k,
    where x and k are elements of F_p
    See: https://eprint.iacr.org/2016/542.pdf
    """
    pp_elements = PreProcessedElements()

    # def cubing_share(): [x] -> [x^3]
    async def cubing_share(x):
        r1, r2, r3 = pp_elements.get_cube(context)
        y = await (x - r1).open()
        # [x^3] = 3y[r^2] + 3y^2[r] + y^3 + [r^3]
        x3 = 3*y*r2 + 3*(y**2)*r1 + y**3 + r3
        return x3

    # iterating the round function ROUND times
    inp = x
    for ctr in range(ROUND):
        inp = await cubing_share(inp + (k + ctr))

    return inp + k


def mimc_plain(x, k):
    inp = x
    for ctr in range(ROUND):
        inp = (inp + (k + ctr)) ** 3

    return inp + k
