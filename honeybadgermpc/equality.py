from honeybadgermpc.mpc import PreProcessedElements
import asyncio


async def equality(context, p_share, q_share, security_parameter=32):
    assert isinstance(p_share, context.Share)
    assert isinstance(q_share, context.Share)

    pp_elements = PreProcessedElements()
    diff_a = p_share - q_share

    def legendre_mod_p(a):
        """Return the legendre symbol ``legendre(a, p)`` where *p* is the
        order of the field of *a*.
        """
        assert a.modulus % 2 == 1

        b = a ** ((a.modulus - 1)//2)
        if b == 1:
            return 1
        elif b == a.modulus-1:
            return -1
        return 0

    async def _gen_test_bit():
        # # b \in {0, 1}
        b = pp_elements.get_bit(context)

        # # _b \in {5, 1}, for p = 1 mod 8, s.t. (5/p) = -1
        # # so _b = -4 * b + 5
        _b = (-4 * b) + context.Share(5)

        _r = pp_elements.get_rand(context)
        _rp = pp_elements.get_rand(context)

        # c = a * r + b * rp * rp
        # If b_i == 1, c_i is guaranteed to be a square modulo p if a is zero
        # and with probability 1/2 otherwise (except if rp == 0).
        # If b_i == -1 it will be non-square.
        c = await ((diff_a * _r) + (_b * _rp * _rp)).open()

        return c, _b

    async def gen_test_bit():
        cj, bj = await _gen_test_bit()
        while cj == 0:
            cj, bj = await _gen_test_bit()
        # bj.open() \in {5, 1}

        legendre = legendre_mod_p(cj)
        if legendre == 0:
            return gen_test_bit()

        return (legendre / context.field(2)) * (bj + context.Share(legendre))

    x = await asyncio.gather(*[gen_test_bit() for _ in range(security_parameter)])

    # Take the product (this is here the same as the "and") of all
    # the x'es
    while len(x) > 1:
        # Repeatedly split the shares in half and element-wise multiply the halves
        # until there's only one left.
        # TODO: Use a future version of this computation
        x_first, x_left = context.ShareArray(x[::2]), context.ShareArray(x[1::2])
        x = (await (x_first * x_left))._shares

    # Returns share, this will be equal to 0 only if the shares are equal
    return x[0]
