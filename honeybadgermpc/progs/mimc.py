from math import log, ceil
from honeybadgermpc.mpc import PreProcessedElements, Subgroup

# ROUND: iteration time of MiMC encryption function,
# In BLS12_381, r = ceil(log(p, 3)) = 161
ROUND = ceil(log(Subgroup.BLS12_381, 3))


def mimc_plain(x, k):
    inp = x
    for ctr in range(ROUND):
        inp = (inp + (k + ctr)) ** 3

    return inp + k


async def mimc_mpc(context, x, k):
    """
    MiMC block cipher encryption encrypts message x with secret key k,
    where either x or k can be secret share, the other is an element of F_p
    See: https://eprint.iacr.org/2016/542.pdf
    """
    pp_elements = PreProcessedElements()

    # def cubing_share(): [x] -> [x^3]
    async def cubing_share(x):
        r1, r2, r3 = pp_elements.get_cube(context)
        y = await (x - r1).open()
        # [x^3] = 3y[r^2] + 3y^2[r] + y^3 + [r^3]
        x3 = 3 * y * r2 + 3 * (y ** 2) * r1 + y ** 3 + r3
        return x3

    # iterating the round function ROUND times
    inp = x
    for ctr in range(ROUND):
        inp = await cubing_share((k + context.field(ctr)) + inp)

    return inp + k


async def mimc_mpc_batch(context, xs, k):
    """
    MiMC block cipher encryption encrypts blocks of message xs with secret key k,
    where xs are a list of shared secrets, k is an element of F_p
    """
    pp_elements = PreProcessedElements()

    # def cubing_share_array(): [x1,..., xK] -> [x1^3,..., xK^3]
    async def cubing_share_array(xs):
        rs, rs_sq, rs_cube = [], [], []
        x3s = []

        for x in xs:
            r1, r2, r3 = pp_elements.get_cube(context)
            y = await (x - r1).open()
            rs.append(r1)
            rs_sq.append(r2)
            rs_cube.append(r3)

        ys = await (context.ShareArray(xs) - context.ShareArray(rs)).open()
        for i, y in enumerate(ys):
            # [x^3] = 3y[r^2] + 3y^2[r] + y^3 + [r^3]
            x3s.append(3 * y * rs_sq[i] + 3 * (y ** 2) * rs[i] + y ** 3 + rs_cube[i])

        return x3s

    # iterating the round function ROUND times
    inp_array = xs
    for ctr in range(ROUND):
        inp_array = await cubing_share_array(
            [(k + context.field(ctr)) + inp for inp in inp_array]
        )

    return [inp + k for inp in inp_array]
