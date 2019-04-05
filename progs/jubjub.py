from honeybadgermpc.elliptic_curve import Jubjub, Point
from honeybadgermpc.mpc import Mpc


class SharedPoint(object):
    """
    Represents a point with optimized operatons over Edward's curves.
    This is the 'shared' version of this class, which does deal with shares
    Math operations derived from
    https://en.wikipedia.org/wiki/Twisted_Edwards_curve#Addition_on_twisted_Edwards_curves # noqa: E501
    """

    def __init__(self, context: Mpc, xs, ys, curve: Jubjub = Jubjub()):
        if not isinstance(curve, Jubjub):
            raise Exception(
                f"Could not create Point-- given \
                curve not of type Jubjub({type(curve)})")

        self.context = context
        self.curve = curve
        self.xs = xs
        self.ys = ys

    async def __on_curve(self) -> bool:
        """
        Checks whether or not the given shares for x and y correspond to a
        point that sits on the current curve

        WARNING: This method currently leaks information about the shared point--
                 We need to use share equality testing instead
        """
        x_sq = await(self.xs * self.xs)
        y_sq = await(self.ys * self.ys)
        a_ = self.context.Share(self.curve.a)
        d_ = self.context.Share(self.curve.d)

        # ax^2 + y^2
        lhs = await(a_ * x_sq) + y_sq

        # 1 + dx^2y^2
        rhs = self.context.Share(1) + await(d_ * await(x_sq * y_sq))

        # TODO: use share equality to prevent the leaking of data
        return await lhs.open() == await rhs.open()

    async def __init(self):
        """asynchronous part of initialization via create or from_point
        """
        if not await(self.__on_curve()):
            raise Exception(
                f"Could not initialize Point {self}-- \
                does not sit on given curve {self.curve}")

    @staticmethod
    async def create(context: Mpc, xs, ys, curve=Jubjub()):
        """ Given a context, secret shared coordinates and a curve,
            creates the given point
        """
        point = SharedPoint(context, xs, ys, curve)
        await point.__init()

        return point

    @staticmethod
    async def from_point(context: Mpc, p: Point) -> 'SharedPoint':
        """ Given a local point and a context, created a shared point
        """
        if not isinstance(p, Point):
            raise Exception(f"Could not create shared point-- p ({p}) is not a Point!")

        return await(SharedPoint.create(context, context.Share(p.x), context.Share(p.y)))

    def __str__(self) -> str:
        return f"({self.xs}, {self.ys})"

    def __repr__(self) -> str:
        return str(self)

    async def neg(self):
        return await(SharedPoint.create(self.context,
                                        await(self.context.Share(-1) * self.xs),
                                        self.ys,
                                        self.curve))

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

        one = self.context.Share(1)
        y_prod = await(y1 * y2)
        x_prod = await(x1 * x2)
        d_ = self.context.Share(self.curve.d)

        # d_prod = d*x1*x2*y1*y2
        d_prod = await(await(d_ * x_prod) * y_prod)

        # x3 = ((x1*y2) + (y1*x2)) / (1 + d*x1*x2*y1*y2)
        x3 = await((await(x1 * y2) + await(y1 * x2)) / (one + d_prod))

        # y3 = ((y1*y2) + (x1*x2)) / (1 - d*x1*x2*y1*y2)
        y3 = await((y_prod + x_prod) / (one - d_prod))

        return await(SharedPoint.create(self.context, x3, y3, self.curve))

    async def sub(self, other: 'SharedPoint') -> 'SharedPoint':
        return await self.add(await(other.neg()))

    async def mul(self, n: int) -> 'SharedPoint':
        # Using the Double-and-Add algorithm
        # https://en.wikipedia.org/wiki/Elliptic_curve_point_multiplication
        if not isinstance(n, int):
            raise Exception("Can't scale a SharedPoint by something which isn't an int!")

        if n < 0:
            negated = await self.neg()
            return await negated.mul(-n)
        elif n == 0:
            return SharedIdeal(self.curve)

        current = self
        product = await(SharedPoint.from_point(self.context, Point(0, 1, self.curve)))

        i = 1
        while i <= n:
            if n & i == i:
                product = await(product.add(current))

            current = await(current.double())
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
        product = await(SharedPoint.from_point(self.context, Point(0, 1, self.curve)))

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
        x, y = self.xs, self.ys

        x_sq, y_sq = await(x*x), await(y*y)
        ax_sq = self.curve.a * x_sq

        x_prod = 2 * await(x * y)
        y_prod = y_sq - ax_sq

        x_denom = ax_sq + y_sq
        y_denom = self.context.Share(2) - ax_sq - y_sq

        return await(SharedPoint.create(self.context,
                                        await(x_prod / x_denom),
                                        await(y_prod / y_denom),
                                        self.curve))


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
