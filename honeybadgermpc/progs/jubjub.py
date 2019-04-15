from honeybadgermpc.elliptic_curve import Jubjub, Point, Ideal
from honeybadgermpc.mpc import Mpc


class SharedPoint(object):
    """
    Represents a point with optimized operatons over Edward's curves.
    This is the 'shared' version of this class, which does deal with shares
    Math operations derived from
    https://en.wikipedia.org/wiki/Twisted_Edwards_curve#Addition_on_twisted_Edwards_curves # noqa: E501
    """

    def __init__(self, context: Mpc, xs, ys, curve: Jubjub = Jubjub()):
        assert isinstance(curve, Jubjub)

        self.context = context
        self.curve = curve
        self.xs = xs
        self.ys = ys

    async def _on_curve(self) -> bool:
        """
        Checks whether or not the given shares for x and y correspond to a
        point that sits on the current curve
        """
        x_sq = self.xs * self.xs
        y_sq = self.ys * self.ys

        # ax^2 + y^2
        lhs = self.curve.a * x_sq + y_sq

        # 1 + dx^2y^2
        rhs = self.context.field(1) + self.curve.d * x_sq * y_sq

        return await (await lhs == await rhs).open()

    @staticmethod
    async def create(context: Mpc, xs, ys, curve=Jubjub()):
        """ Given a context, secret shared coordinates and a curve,
            creates the given point
        """
        point = SharedPoint(context, xs, ys, curve)
        if not await point._on_curve():
            raise ValueError(
                f"Could not initialize Point {point}-- \
                does not sit on given curve {point.curve}")

        return point

    @staticmethod
    def from_point(context: Mpc, p: Point) -> 'SharedPoint':
        """ Given a local point and a context, created a shared point
        """
        if not isinstance(p, Point):
            raise Exception(f"Could not create shared point-- p ({p}) is not a Point!")

        return SharedPoint(context, context.Share(p.x),
                           context.Share(p.y), curve=p.curve)

    def __str__(self) -> str:
        return f"({self.xs}, {self.ys})"

    def __repr__(self) -> str:
        return str(self)

    def neg(self):
        return SharedPoint(self.context,
                           -1 * self.xs,
                           self.ys,
                           self.curve)

    async def add(self, other: 'SharedPoint') -> 'SharedPoint':
        if isinstance(other, SharedIdeal):
            return self
        elif not isinstance(other, SharedPoint):
            raise Exception(
                "Could not add other point-- not an instance of SharedPoint")
        elif self.curve != other.curve:
            raise Exception("Can't add points on different curves!")
        elif self.context != other.context:
            raise Exception("Can't add points from different contexts!")

        x1, y1, x2, y2 = self.xs, self.ys, other.xs, other.ys
        one = self.context.field(1)

        x_prod, y_prod = x1*x2, y1*y2

        # d_prod = d*x1*x2*y1*y2
        d_prod = self.curve.d * x_prod * y_prod

        # x3 = ((x1*y2) + (y1*x2)) / (1 + d*x1*x2*y1*y2)
        x3 = (x1 * y2 + y1 * x2) / (one + d_prod)

        # y3 = ((y1*y2) + (x1*x2)) / (1 - d*x1*x2*y1*y2)
        y3 = (y_prod + x_prod) / (one - d_prod)

        return SharedPoint(self.context, x3, y3, self.curve)

    async def sub(self, other: 'SharedPoint') -> 'SharedPoint':
        return await self.add(other.neg())

    async def mul(self, n: int) -> 'SharedPoint':
        # Using the Double-and-Add algorithm
        # https://en.wikipedia.org/wiki/Elliptic_curve_point_multiplication
        if not isinstance(n, int):
            raise Exception("Can't scale a SharedPoint by something which isn't an int!")

        if n < 0:
            return await self.neg().mul(-n)
        elif n == 0:
            return SharedIdeal(self.curve)

        current = self
        product = SharedPoint.from_point(self.context, Point(0, 1, self.curve))

        i = 1
        while i <= n:
            if n & i == i:
                product = await product.add(current)

            current = await current.double()
            i <<= 1

        return product

    async def montgomery_mul(self, n: int) -> 'SharedPoint':
        # Using the Montgomery Ladder algorithm
        # https://en.wikipedia.org/wiki/Elliptic_curve_point_multiplication
        if not isinstance(n, int):
            raise Exception("Can't scale a SharedPoint by something which isn't an int!")

        if n < 0:
            negated = await self.neg()
            return await negated.mul(-n)
        elif n == 0:
            return SharedIdeal(self.curve)

        current = self
        product = SharedPoint.from_point(self.context, Point(0, 1, self.curve))

        i = 1 << n.bit_length()
        while i > 0:
            if n & i == i:
                product = await product.add(current)
                current = await current.double()
            else:
                current = await product.add(current)
                product = await product.double()

            i >>= 1

        return product

    async def double(self) -> 'SharedPoint':
        # Uses the optimized implementation from wikipedia
        x_, y_ = self.xs, self.ys
        x_sq, y_sq = (x_*x_), (y_*y_)

        ax_sq = self.curve.a * x_sq
        x_denom = ax_sq + y_sq

        x = (2 * x_ * y_) / x_denom
        y = (y_sq - ax_sq) / (self.context.field(2) - x_denom)

        return SharedPoint(self.context, x, y, self.curve)


class SharedIdeal(SharedPoint):
    """ Analogue of the Ideal class for shared points
        Represents the point at infinity
    """

    def __init__(self, curve):
        self.curve = curve

    def __str__(self):
        return "SharedIdeal"

    async def neg(self):
        return self

    async def add(self, other):
        if not isinstance(other, SharedPoint):
            raise Exception(
                "Can't add a shared point with something which isn't a shared point")
        elif self.curve != other.curve:
            raise Exception("Can't add points on different curves")

        return self

    async def sub(self, other):
        if not isinstance(other, SharedPoint):
            raise Exception(
                "Can't subtract a shared point by something which isn't a shared point")
        elif self.curve != other.curve:
            raise Exception("Can't add points on different curves")

        return self

    async def mul(self, n):
        if not isinstance(n, int):
            raise Exception("Can't scale a point by something which isn't an int!")

        return self

    async def double(self):
        return self


async def share_mul(context: Mpc, bs: list, p: Point) -> SharedPoint:
    """
    The multiplication of the share of a field element and a point
    e.g. [x]P -> [X], where P is a point on the given elliptic curve
    x is the bitwise shared value,
    starting from the least significant bit.

    NOTE: This is an affine version.
    bs := [[b0], [b1], ... [bK]], then bs * P can be broken down into
    [b0] * (2^0 * P) + [b1] * (2^1 * P) .... + [bK] * (2^K * P)

    For each term [bi] * (2^i * P), we compute its x, y coordinates seperately.
    Let P2i := (2^i * P), and we have identity = (0, 1), then
        x = [b_i] * (P2i.x - identity.x) + identity.x
          = [b_i] * P2i.x
        y = [b_i] * (P2i.y - identity.y) + identity.y
          = [b_i] * (P2i.y - 1) + 1
    So we get the SharedPoint of each term.
    """
    if isinstance(p, Ideal):
        return SharedIdeal(p.curve)

    terms = []
    for i in range(len(bs)):
        p2i = (2**i) * p
        term = SharedPoint(context,
                           p2i.x * bs[i],
                           (p2i.y - 1) * bs[i] + p.curve.Field(1),
                           p.curve)
        terms.append(term)

    accum = terms[0]
    for i in terms[1:]:
        accum = await accum.add(i)

    return accum
