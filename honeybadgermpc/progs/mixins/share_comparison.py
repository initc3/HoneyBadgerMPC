from honeybadgermpc.progs.mixins.base import AsyncMixin
from honeybadgermpc.progs.mixins.constants import MixinConstants
from honeybadgermpc.utils.typecheck import TypeCheck
from honeybadgermpc.progs.mixins.dataflow import Share, ShareFuture

from asyncio import gather


class Equality(AsyncMixin):
    from honeybadgermpc.mpc import Mpc, GFElement

    name = MixinConstants.ShareEquality

    @staticmethod
    @TypeCheck()
    def legendre_mod_p(a: GFElement):
        """Return the legendre symbol ``legendre(a, p)`` where *p* is the
        order of the field of *a*.
        """
        assert a.modulus % 2 == 1

        b = a ** ((a.modulus - 1) // 2)
        if b == 1:
            return 1
        elif b == a.modulus - 1:
            return -1
        return 0

    @staticmethod
    @TypeCheck()
    async def _gen_test_bit(context: Mpc, diff: Share):
        # # b \in {0, 1}
        b = context.preproc.get_bit(context)

        # # _b \in {5, 1}, for p = 1 mod 8, s.t. (5/p) = -1
        # # so _b = -4 * b + 5
        _b = (-4 * b) + context.Share(5)

        _r = context.preproc.get_rand(context)
        _rp = context.preproc.get_rand(context)

        # c = a * r + b * rp * rp
        # If b_i == 1, c_i is guaranteed to be a square modulo p if a is zero
        # and with probability 1/2 otherwise (except if rp == 0).
        # If b_i == -1 it will be non-square.
        c = await ((diff * _r) + (_b * _rp * _rp)).open()

        return c, _b

    @staticmethod
    @TypeCheck()
    async def gen_test_bit(context: Mpc, diff: Share):
        cj, bj = await Equality._gen_test_bit(context, diff)
        while cj == 0:
            cj, bj = await Equality._gen_test_bit(context, diff)

        legendre = Equality.legendre_mod_p(cj)
        if legendre == 0:
            return Equality.gen_test_bit(context, diff)

        return (legendre / context.field(2)) * (bj + context.Share(legendre))

    @staticmethod
    @TypeCheck()
    async def _prog(
        context: Mpc, p_share: Share, q_share: Share, security_parameter: int = 32
    ):
        diff = p_share - q_share

        x = context.ShareArray(
            await gather(
                *[
                    Equality.gen_test_bit(context, diff)
                    for _ in range(security_parameter)
                ]
            )
        )

        # Take the product (this is here the same as the "and") of all
        return await x.multiplicative_product()


class LessThan(AsyncMixin):
    """ Given two shares, a_share and b_share with corresponding values a and b,
    compute a < b and output the result as a share. Requires that a, b < (p-1)/2.

    args:
        context (Mpc): MPC context
        a_share (context.Share) Share representing a in a < b
        b_share (context.Share) Share representing b in a < b

    output:
        A share representing 1 if a < b, otherwise 0

    NOTE: This requires that the arguments are both less than (p-1)/2

    Source:
    MULTIPARTY COMPARISON - An Improved Multiparty Protocol for
    Comparison of Secret-shared Values by Tord Ingolf Reistad(2007)

    TODO:   Currently, this fails every so often (~1/20 times experimentally).
            Investigate this / add assertions to detect this.
    """

    from honeybadgermpc.mpc import Mpc

    name = MixinConstants.ShareLessThan

    @staticmethod
    def _xor_bits(a, b):
        """ Given 2 secret-shared bits, this computes their xor
        """
        return a + b - 2 * a * b

    @staticmethod
    @TypeCheck()
    async def _transform_comparison(context: Mpc, a_share: Share, b_share: Share):
        """ Section 5.1 First Transformation
        Compute [r]_B and [c]_B, which are bitwise sharings of a random share [r] and
        [c] = 2([a] - [b]) + [r]
        """
        z = a_share - b_share

        r_b, r_bits = context.preproc.get_share_bits(context)

        # [c] = 2[z] + [r]_B = 2([a]-[b]) + [r]_B
        c = await (2 * z + r_b).open()
        c_bits = [context.field(x) for x in map(int, "{0:0255b}".format(c.value))]

        # LSB first
        c_bits.reverse()

        return r_bits, c_bits

    @staticmethod
    @TypeCheck()
    def _compute_x(context: Mpc, r_bits: list, c_bits: list):
        """ Section 5.2 Computing X
        Computes [x] from equation 7

        The least significant bit of [x], written [x_0] is equal to
        the value [r_i], where i is the most significant bit where [r_i] != c_i
        [x_0] == ([r]_B > c)

        TODO: precompute PRODUCT(1 + [r_j])
              Compute PRODUCT(1 + c_j) without MPC
              See final further work points in paper section 6
        """
        power_bits = [
            context.field(1) + LessThan._xor_bits(r, c)
            for r, c in zip(r_bits[1:], c_bits[1:])
        ]

        powers = [context.Share(1)]
        for b in reversed(power_bits):
            powers.insert(0, b * powers[0])

        # TODO: make this log(n)
        x = context.field(0)
        for (r_i, c_i, p) in zip(r_bits, c_bits, powers):
            x += r_i * (context.field(1) - c_i) * p

        return x

    @staticmethod
    @TypeCheck()
    async def _extract_lsb(context: Mpc, x: (Share, ShareFuture)):
        """ Section 5.3 Extracting the Least Significant Bit
        Returns a future to [x_0], which represents [r]_B > c
        """
        bit_length = context.field.modulus.bit_length()

        s_b, s_bits = context.preproc.get_share_bits(context)
        d_ = s_b + x
        d = await d_.open()

        # msb
        s_0 = s_bits[0]

        # lsb
        s_1 = s_bits[bit_length - 1]  # [s_{bit_length-1}]
        s_2 = s_bits[bit_length - 2]  # [s_{bit_length-2}]
        s_prod = s_1 * s_2

        # lsb
        d0 = d.value & 1

        d_xor_1 = context.field(d0 ^ (d.value < (1 << (bit_length - 1))))
        d_xor_2 = context.field(d0 ^ (d.value < (1 << (bit_length - 2))))
        d_xor_12 = context.field(
            d0 ^ (d.value < ((1 << (bit_length - 1)) + (1 << (bit_length - 2))))
        )

        d_0 = (
            (context.field(1) - s_1 - s_2 + s_prod) * d0
            + ((s_2 - s_prod) * d_xor_2)
            + ((s_1 - s_prod) * d_xor_1)
            + (s_prod * d_xor_12)
        )

        # [x0] = [s0] ^ [d0], equal to [r]_B > c
        return LessThan._xor_bits(s_0, d_0)

    @staticmethod
    @TypeCheck()
    async def _prog(context: Mpc, a_share: Share, b_share: Share):
        r_bits, c_bits = await LessThan._transform_comparison(context, a_share, b_share)
        x = LessThan._compute_x(context, r_bits, c_bits)
        x_0 = await LessThan._extract_lsb(context, x)

        # ([a] < [b]) = c_0 \xor [r_0] \xor ([r]_B > c)
        return LessThan._xor_bits(LessThan._xor_bits(c_bits[0], r_bits[0]), x_0)
