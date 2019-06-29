from honeybadgermpc.progs.mixins.base import MixinBase, AsyncMixin
from honeybadgermpc.progs.mixins.constants import MixinConstants
from honeybadgermpc.utils.typecheck import TypeCheck
from honeybadgermpc.progs.mixins.dataflow import Share, ShareArray
from honeybadgermpc.field import GFElement

from asyncio import gather


class BeaverMultiply(AsyncMixin):
    from honeybadgermpc.mpc import Mpc, Share

    name = MixinConstants.MultiplyShare

    @staticmethod
    @TypeCheck()
    async def _prog(context: Mpc, x: Share, y: Share):
        a, b, ab = MixinBase.pp_elements.get_triple(context)

        d, e = await gather(*[(x - a).open(), (y - b).open()])
        xy = d * e + d * b + e * a + ab
        return xy


class BeaverMultiplyArrays(AsyncMixin):
    from honeybadgermpc.mpc import Mpc

    name = MixinConstants.MultiplyShareArray

    @staticmethod
    @TypeCheck()
    async def _prog(context: Mpc, j: ShareArray, k: ShareArray):
        assert len(j) == len(k)

        a, b, ab = [], [], []
        for _ in range(len(j)):
            p, q, pq = MixinBase.pp_elements.get_triple(context)
            a.append(p)
            b.append(q)
            ab.append(pq)

        u, v = context.ShareArray(a), context.ShareArray(b)
        f, g = await gather(*[(j - u).open(), (k - v).open()])
        xy = [d * e + d * q + e * p + pq for (p, q, pq, d, e) in zip(a, b, ab, f, g)]

        return context.ShareArray(xy)


class DoubleSharingMultiply(AsyncMixin):
    from honeybadgermpc.mpc import Mpc

    name = MixinConstants.MultiplyShare

    @staticmethod
    @TypeCheck()
    async def reduce_degree_share(context: Mpc, x_2t: Share):
        assert x_2t.t == context.t * 2

        r_t, r_2t = MixinBase.pp_elements.get_double_share(context)
        diff = await (x_2t - r_2t).open()

        return r_t + diff

    @staticmethod
    @TypeCheck()
    async def _prog(context: Mpc, x: Share, y: Share):
        xy_2t = context.Share(x.v * y.v, context.t * 2)
        xy_t = await DoubleSharingMultiply.reduce_degree_share(context, xy_2t)
        return xy_t


class DoubleSharingMultiplyArrays(AsyncMixin):
    from honeybadgermpc.mpc import Mpc

    name = MixinConstants.MultiplyShareArray

    @staticmethod
    @TypeCheck()
    async def reduce_degree_share_array(context: Mpc, x_2t: ShareArray):
        assert x_2t.t == context.t * 2

        r_t, r_2t = [], []
        for _ in range(len(x_2t)):
            r_t_, r_2t_ = MixinBase.pp_elements.get_double_share(context)
            r_t.append(r_t_)
            r_2t.append(r_2t_)

        q_t = context.ShareArray(r_t)
        q_2t = context.ShareArray(r_2t, 2 * context.t)
        diff = await (x_2t - q_2t).open()
        return q_t + diff

    @staticmethod
    @TypeCheck()
    async def _prog(context: Mpc, x: ShareArray, y: ShareArray):
        assert len(x) == len(y)

        xy_2t = context.ShareArray(
            [j.v * k.v for j, k in zip(x._shares, y._shares)], context.t * 2
        )
        xy_t = await DoubleSharingMultiplyArrays.reduce_degree_share_array(
            context, xy_2t
        )
        return xy_t


class InvertShare(AsyncMixin):
    from honeybadgermpc.mpc import Mpc

    name = MixinConstants.InvertShare

    @staticmethod
    @TypeCheck()
    async def _prog(context: Mpc, x: Share):
        r = MixinBase.pp_elements.get_rand(context)
        sig = await (x * r).open()

        return r * (1 / sig)


class InvertShareArray(AsyncMixin):
    from honeybadgermpc.mpc import Mpc

    name = MixinConstants.InvertShareArray

    @staticmethod
    @TypeCheck()
    async def _prog(context: Mpc, xs: ShareArray):
        rs = context.ShareArray(
            [MixinBase.pp_elements.get_rand(context) for _ in range(len(xs))]
        )

        sigs = await (await (xs * rs)).open()
        sig_invs = context.ShareArray([1 / sig for sig in sigs])

        return await (rs * sig_invs)


class DivideShares(AsyncMixin):
    from honeybadgermpc.mpc import Mpc

    name = MixinConstants.DivideShare
    dependencies = [MixinConstants.InvertShare]

    @staticmethod
    @TypeCheck()
    async def _prog(context: Mpc, x: Share, y: Share):
        y_inv = await context.config[MixinConstants.InvertShare](context, y)
        return await (x * y_inv)


class DivideShareArrays(AsyncMixin):
    from honeybadgermpc.mpc import Mpc

    name = MixinConstants.DivideShareArray
    dependencies = [MixinConstants.InvertShareArray]

    @staticmethod
    @TypeCheck()
    async def _prog(context: Mpc, xs: ShareArray, ys: ShareArray):
        y_invs = await context.config[MixinConstants.InvertShareArray](context, ys)
        return await (xs * y_invs)


class Equality(AsyncMixin):
    from honeybadgermpc.mpc import Mpc

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

        return await x.multiplicative_product()
