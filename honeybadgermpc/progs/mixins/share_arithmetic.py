from honeybadgermpc.progs.mixins.base import MixinBase, AsyncMixin
from honeybadgermpc.progs.mixins.constants import MixinConstants
from honeybadgermpc.progs.mixins.utils import static_type_check

from asyncio import gather


class BeaverMultiply(AsyncMixin):
    from honeybadgermpc.mpc import Mpc, Share

    name = MixinConstants.MultiplyShare

    @staticmethod
    @static_type_check(Mpc, 'context.Share', 'context.Share')
    async def _prog(context, x, y):
        a, b, ab = MixinBase.pp_elements.get_triple(context)

        d, e = await gather(*[(x - a).open(), (y - b).open()])
        xy = d*e + d*b + e*a + ab
        return xy


class BeaverMultiplyArrays(AsyncMixin):
    from honeybadgermpc.mpc import Mpc, ShareArray

    name = MixinConstants.MultiplyShareArray

    @staticmethod
    @static_type_check(Mpc, 'context.ShareArray', 'context.ShareArray')
    async def _prog(context, j, k):
        assert len(j) == len(k)

        a, b, ab = [], [], []
        for _ in range(len(j)):
            p, q, pq = MixinBase.pp_elements.get_triple(context)
            a.append(p)
            b.append(q)
            ab.append(pq)

        u, v = context.ShareArray(a), context.ShareArray(b)
        f, g = await gather(*[(j - u).open(), (k - v).open()])
        xy = [d*e + d*q + e*p + pq for (p, q, pq, d, e) in zip(a, b, ab, f, g)]

        return context.ShareArray(xy)


class DoubleSharingMultiply(AsyncMixin):
    from honeybadgermpc.mpc import Mpc, Share

    name = MixinConstants.MultiplyShare

    @staticmethod
    @static_type_check(Mpc, 'context.Share')
    async def reduce_degree_share(context, x_2t):
        assert x_2t.t == context.t*2

        r_t, r_2t = MixinBase.pp_elements.get_double_share(context)
        diff = await (x_2t - r_2t).open()

        return r_t + diff

    @staticmethod
    @static_type_check(Mpc, 'context.Share', 'context.Share')
    async def _prog(context, x, y):

        xy_2t = context.Share(x.v * y.v, context.t*2)
        xy_t = await DoubleSharingMultiply.reduce_degree_share(context, xy_2t)
        return xy_t


class DoubleSharingMultiplyArrays(AsyncMixin):
    from honeybadgermpc.mpc import Mpc, ShareArray

    name = MixinConstants.MultiplyShareArray

    @staticmethod
    @static_type_check(Mpc, 'context.ShareArray')
    async def reduce_degree_share_array(context, x_2t):
        assert x_2t.t == context.t*2

        r_t, r_2t = [], []
        for _ in range(len(x_2t)):
            r_t_, r_2t_ = MixinBase.pp_elements.get_double_share(context)
            r_t.append(r_t_)
            r_2t.append(r_2t_)

        q_t = context.ShareArray(r_t)
        q_2t = context.ShareArray(r_2t, 2*context.t)
        diff = await (x_2t - q_2t).open()
        return context.ShareArray(await (q_t + diff).open())

    @staticmethod
    @static_type_check(Mpc, 'context.ShareArray', 'context.ShareArray')
    async def _prog(context, x, y):
        assert len(x) == len(y)

        xy_2t = context.ShareArray(
            [j.v * k.v for j, k in zip(x._shares, y._shares)], context.t*2)
        xy_t = await DoubleSharingMultiplyArrays.reduce_degree_share_array(
            context, xy_2t)
        return xy_t


class InvertShare(AsyncMixin):
    from honeybadgermpc.mpc import Mpc, Share

    name = MixinConstants.InvertShare

    @staticmethod
    @static_type_check(Mpc, 'context.Share')
    async def _prog(context, x):
        r = MixinBase.pp_elements.get_rand(context)
        sig = await (x*r).open()

        return r * (1/sig)


class InvertShareArray(AsyncMixin):
    from honeybadgermpc.mpc import Mpc, ShareArray

    name = MixinConstants.InvertShareArray

    @staticmethod
    @static_type_check(Mpc, 'context.ShareArray')
    async def _prog(context, xs):
        rs = context.ShareArray([MixinBase.pp_elements.get_rand(context)
                                 for _ in range(len(xs))])

        sigs = await (await (xs*rs)).open()
        sig_invs = context.ShareArray([1/sig for sig in sigs])

        return await (rs * sig_invs)


class DivideShares(AsyncMixin):
    from honeybadgermpc.mpc import Mpc, Share

    name = MixinConstants.DivideShare
    dependencies = [MixinConstants.InvertShare]

    @staticmethod
    @static_type_check(Mpc, 'context.Share', 'context.Share')
    async def _prog(context, x, y):
        y_inv = await context.config[MixinConstants.InvertShare](context, y)
        return await (x * y_inv)


class DivideShareArrays(AsyncMixin):
    from honeybadgermpc.mpc import Mpc, ShareArray

    name = MixinConstants.DivideShareArray
    dependencies = [MixinConstants.InvertShareArray]

    @staticmethod
    @static_type_check(Mpc, 'context.ShareArray', 'context.ShareArray')
    async def _prog(context, xs, ys):
        y_invs = await context.config[MixinConstants.InvertShareArray](context, ys)
        return await (xs * y_invs)


class Equality(AsyncMixin):
    from honeybadgermpc.mpc import Mpc, GFElement

    name = MixinConstants.ShareEquality

    @staticmethod
    @static_type_check(GFElement)
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

    @staticmethod
    @static_type_check(Mpc, 'context.Share')
    async def _gen_test_bit(context, diff):
        # # b \in {0, 1}
        b = MixinBase.pp_elements.get_bit(context)

        # # _b \in {5, 1}, for p = 1 mod 8, s.t. (5/p) = -1
        # # so _b = -4 * b + 5
        _b = (-4 * b) + context.Share(5)

        _r = MixinBase.pp_elements.get_rand(context)
        _rp = MixinBase.pp_elements.get_rand(context)

        # c = a * r + b * rp * rp
        # If b_i == 1, c_i is guaranteed to be a square modulo p if a is zero
        # and with probability 1/2 otherwise (except if rp == 0).
        # If b_i == -1 it will be non-square.
        c = await ((diff * _r) + (_b * _rp * _rp)).open()

        return c, _b

    @staticmethod
    @static_type_check(Mpc, 'context.Share')
    async def gen_test_bit(context, diff):
        cj, bj = await Equality._gen_test_bit(context, diff)
        while cj == 0:
            cj, bj = await Equality._gen_test_bit(context, diff)

        legendre = Equality.legendre_mod_p(cj)
        if legendre == 0:
            return Equality.gen_test_bit(context, diff)

        return (legendre / context.field(2)) * (bj + context.Share(legendre))

    @staticmethod
    @static_type_check(Mpc, 'context.Share', 'context.Share', int)
    async def _prog(context, p_share, q_share, security_parameter=32):
        diff = p_share - q_share

        x = await gather(*[Equality.gen_test_bit(context, diff)
                           for _ in range(security_parameter)])

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
