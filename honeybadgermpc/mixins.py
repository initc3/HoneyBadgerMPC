from .preprocessing import PreProcessedElements


class MixinOpName(object):
    Mul = "mul"


class MixinBase(object):
    pp_elements = PreProcessedElements()


class BeaverTriple(MixinBase):
    @staticmethod
    async def multiply_shares(context, x, y):
        assert type(x) is context.Share
        assert type(y) is context.Share

        a, b, ab = MixinBase.pp_elements.get_triple(context)

        d = await (x - a).open()
        e = await (y - b).open()
        xy = context.Share(d*e) + d*b + e*a + ab
        return xy


class DoubleSharing(MixinBase):
    @staticmethod
    async def reduce_degree(context, x_2t):
        r_t, r_2t = MixinBase.pp_elements.get_double_share(context)
        diff = await (x_2t - r_2t).open()
        return context.Share(await (r_t + diff).open())

    @staticmethod
    async def multiply_shares(context, x, y):
        assert type(x) is context.Share
        assert type(y) is context.Share

        xy_2t = context.Share(x.v * y.v, context.t*2)
        xy_t = await DoubleSharing.reduce_degree(context, xy_2t)
        return xy_t
