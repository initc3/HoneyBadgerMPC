from __future__ import annotations  # noqa: F407
import asyncio
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

    @staticmethod
    def from_point(context: Mpc, p: Point) -> SharedPoint:
        """ Given a local point and a context, created a shared point
        """
        if not isinstance(p, Point):
            raise Exception(f"Could not create shared point-- p ({p}) is not a Point!")

        return SharedPoint(
            context, context.Share(p.x), context.Share(p.y), curve=p.curve
        )

    def __str__(self) -> str:
        return f"({self.xs}, {self.ys})"

    def __repr__(self) -> str:
        return str(self)

    def open(self):
        """Opens the shares of the shared point, and returns a future which evaluates
        to a point
        """
        res = asyncio.Future()

        def cb(r):
            x, y = r.result()
            res.set_result(Point(x, y, self.curve))

        opening = asyncio.gather(self.xs.open(), self.ys.open())
        opening.add_done_callback(cb)

        return res

    def equals(self, other):
        """Returns a future that evaluates to the result of the equality check
        """
        res = asyncio.Future()

        if isinstance(other, (SharedIdeal)):
            res.set_result(False)
        elif not isinstance(other, (SharedPoint)):
            res.set_result(False)
        elif self.curve != other.curve:
            res.set_result(False)
        else:
            opening = asyncio.gather(
                (self.xs == other.xs).open(), (self.ys == other.ys).open()
            )

            def cb(r):
                x_equal, y_equal = r.result()
                res.set_result(bool(x_equal) and bool(y_equal))

            opening.add_done_callback(cb)

        return res

    def neg(self):
        return SharedPoint(self.context, -1 * self.xs, self.ys, self.curve)

    def add(self, other: SharedPoint) -> SharedPoint:
        if isinstance(other, SharedIdeal):
            return self
        elif not isinstance(other, SharedPoint):
            raise Exception(
                "Could not add other point-- not an instance of SharedPoint"
            )
        elif self.curve != other.curve:
            raise Exception("Can't add points on different curves!")
        elif self.context != other.context:
            raise Exception("Can't add points from different contexts!")

        x1, y1, x2, y2 = self.xs, self.ys, other.xs, other.ys
        one = self.context.field(1)

        x_prod, y_prod = x1 * x2, y1 * y2

        # d_prod = d*x1*x2*y1*y2
        d_prod = self.curve.d * x_prod * y_prod

        # x3 = ((x1*y2) + (y1*x2)) / (1 + d*x1*x2*y1*y2)
        x3 = (x1 * y2 + y1 * x2) / (one + d_prod)

        # y3 = ((y1*y2) + (x1*x2)) / (1 - d*x1*x2*y1*y2)
        y3 = (y_prod + x_prod) / (one - d_prod)

        return SharedPoint(self.context, x3, y3, self.curve)

    def sub(self, other: SharedPoint) -> SharedPoint:
        return self.add(other.neg())

    def mul(self, n: int) -> SharedPoint:
        # Using the Double-and-Add algorithm
        # https://en.wikipedia.org/wiki/Elliptic_curve_point_multiplication
        if not isinstance(n, int):
            raise Exception(
                "Can't scale a SharedPoint by something which isn't an int!"
            )

        if n < 0:
            return self.neg().mul(-n)
        elif n == 0:
            return SharedIdeal(self.curve)

        current = self
        product = SharedPoint.from_point(self.context, Point(0, 1, self.curve))

        i = 1
        while i <= n:
            if n & i == i:
                product = product.add(current)

            current = current.double()
            i <<= 1

        return product

    def montgomery_mul(self, n: int) -> SharedPoint:
        # Using the Montgomery Ladder algorithm
        # https://en.wikipedia.org/wiki/Elliptic_curve_point_multiplication
        if not isinstance(n, int):
            raise Exception(
                "Can't scale a SharedPoint by something which isn't an int!"
            )

        if n < 0:
            negated = self.neg()
            return negated.mul(-n)
        elif n == 0:
            return SharedIdeal(self.curve)

        current = self
        product = SharedPoint.from_point(self.context, Point(0, 1, self.curve))

        i = 1 << n.bit_length()
        while i > 0:
            if n & i == i:
                product = product.add(current)
                current = current.double()
            else:
                current = product.add(current)
                product = product.double()

            i >>= 1

        return product

    def double(self) -> SharedPoint:
        # Uses the optimized implementation from wikipedia
        x_, y_ = self.xs, self.ys
        x_sq, y_sq = (x_ * x_), (y_ * y_)

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

    def neg(self):
        return self

    def add(self, other):
        if not isinstance(other, SharedPoint):
            raise Exception(
                "Can't add a shared point with something which isn't a shared point"
            )
        elif self.curve != other.curve:
            raise Exception("Can't add points on different curves")

        return self

    def sub(self, other):
        if not isinstance(other, SharedPoint):
            raise Exception(
                "Can't subtract a shared point by something which isn't a shared point"
            )
        elif self.curve != other.curve:
            raise Exception("Can't add points on different curves")

        return self

    def mul(self, n):
        if not isinstance(n, int):
            raise Exception("Can't scale a point by something which isn't an int!")

        return self

    def double(self):
        return self

    def equals(self, other):
        """ Made to return a future for consistency with SharedPoint
        Future resolves to true if and only if the other object is
        a SharedPoint with the same curve.
        """

        res = asyncio.Future()

        if not isinstance(other, SharedIdeal):
            res.set_result(False)
        else:
            res.set_result(self.curve == other.curve)

        return res

    def open(self):
        """ Made to return a future for consistency with SharedPoint
        Returns a non-shared Ideal point.
        """

        res = asyncio.Future()

        res.set_result(Ideal(self.curve))

        return res


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
    p2i = p
    for b in bs:
        x = p2i.x * b
        y = (p2i.y - 1) * b + p.curve.Field(1)
        terms.append(SharedPoint(context, x, y, p.curve))
        p2i = p2i.double()

    while len(terms) > 1:
        left_terms, right_terms = terms[::2], terms[1::2]
        terms = [l.add(r) for (l, r) in zip(left_terms, right_terms)]
        if len(left_terms) > len(right_terms):
            terms.append(left_terms[-1])

    return terms[0]
