import asyncio
from .preprocessing import PreProcessedElements


class MixinOpName(object):
    MultiplyShare = "multiply_share"
    MultiplyShareArray = "multiply_share_array"


class MixinBase(object):
    pp_elements = PreProcessedElements()


class BeaverTriple(MixinBase):
    @staticmethod
    async def multiply_shares(context, x, y):
        assert type(x) is context.Share
        assert type(y) is context.Share

        a, b, ab = MixinBase.pp_elements.get_triple(context)

        d, e = await asyncio.gather(*[(x - a).open(), (y - b).open()])
        xy = d*e + d*b + e*a + ab
        return xy

    @staticmethod
    async def multiply_share_arrays(context, j, k):
        assert type(j) is context.ShareArray
        assert type(k) is context.ShareArray
        assert len(j._shares) == len(k._shares)

        a, b, ab = [], [], []
        for _ in range(len(j._shares)):
            p, q, pq = MixinBase.pp_elements.get_triple(context)
            a.append(p)
            b.append(q)
            ab.append(pq)

        u, v = context.ShareArray(a), context.ShareArray(b)
        f, g = await asyncio.gather(*[(j - u).open(), (k - v).open()])
        xy = [d*e + d*q + e*p + pq for (p, q, pq, d, e) in zip(a, b, ab, f, g)]

        return context.ShareArray(xy)


class DoubleSharing(MixinBase):
    @staticmethod
    async def reduce_degree_share(context, x_2t):
        assert type(x_2t) is context.Share
        assert x_2t.t == context.t*2

        r_t, r_2t = MixinBase.pp_elements.get_double_share(context)
        diff = await (x_2t - r_2t).open()
        return context.Share(await (r_t + diff).open())

    @staticmethod
    async def reduce_degree_share_array(context, x_2t):
        assert x_2t.t == context.t*2
        assert type(x_2t) is context.ShareArray

        r_t, r_2t = [], []
        for _ in range(len(x_2t._shares)):
            r_t_, r_2t_ = MixinBase.pp_elements.get_double_share(context)
            r_t.append(r_t_)
            r_2t.append(r_2t_)

        q_t = context.ShareArray(r_t)
        q_2t = context.ShareArray(r_2t, 2*context.t)
        diff = await (x_2t - q_2t).open()
        return context.ShareArray(await (q_t + diff).open())

    @staticmethod
    async def multiply_shares(context, x, y):
        assert type(x) is context.Share
        assert type(y) is context.Share

        xy_2t = context.Share(x.v * y.v, context.t*2)
        xy_t = await DoubleSharing.reduce_degree_share(context, xy_2t)
        return xy_t

    @staticmethod
    async def multiply_share_arrays(context, x, y):
        assert type(x) is context.ShareArray
        assert type(y) is context.ShareArray
        assert len(x._shares) == len(y._shares)

        xy_2t = context.ShareArray(
            [j.v * k.v for j, k in zip(x._shares, y._shares)], context.t*2)
        xy_t = await DoubleSharing.reduce_degree_share_array(context, xy_2t)
        return xy_t
