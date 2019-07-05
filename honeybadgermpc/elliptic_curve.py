from .field import GF, GFElement


class Subgroup:
    BLS12_381 = 0x73EDA753299D7D483339D80809A1D80553BDA402FFFE5BFEFFFFFFFF00000001


class Jubjub(object):
    """
    JubJub is a twisted Edwards curve of the form -x^2 + y^2 = 1 + dx^2y^2
    """

    Field = GF(Subgroup.BLS12_381)

    def __init__(
        self, a: GFElement = Field(-1), d: GFElement = -(Field(10240) / Field(10241))
    ):
        self.a = a
        self.d = d

        a_d_diff = self.a - self.d
        self.disc = self.a * self.d * a_d_diff * a_d_diff * a_d_diff * a_d_diff

        if not self.is_smooth():
            raise Exception(f"The curve {self} is not smooth!")

    def __str__(self) -> str:
        return "%sx^2 + y^2 = 1 + %sx^2y^2" % (self.a, self.d)

    def __repr__(self) -> str:
        return str(self)

    def __eq__(self, other) -> bool:
        return (self.a, self.d) == (other.a, other.d)

    def is_smooth(self) -> bool:
        return self.disc != 0

    def contains_point(self, p: "Point") -> bool:
        """
        Checks whether or not the given point sits on the curve
        """
        return self.a * p.x * p.x + p.y * p.y == 1 + self.d * p.x * p.x * p.y * p.y


class Point(object):
    """
    Represents a point with optimized operations over Edwards curves
    This is the 'local' version of this class, that doesn't deal with shares
    """

    def __init__(self, x: int, y: int, curve: Jubjub = Jubjub()):
        if not isinstance(curve, Jubjub):
            raise Exception(
                f"Could not create Point-- given curve \
                not of type Jubjub ({type(curve)})"
            )

        self.curve = curve  # the curve containing this point
        self.x = x
        self.y = y

        if not self.curve.contains_point(self):
            raise Exception(
                f"Could not create Point({self})-- not on the given curve {curve}!"
            )

    def __str__(self):
        return "(%r, %r)" % (self.x, self.y)

    def __repr__(self):
        return str(self)

    def __neg__(self):
        return Point(self.curve.Field(-self.x), self.y, self.curve)

    def __add__(self, other: "Point") -> "Point":
        if self.curve != other.curve:
            raise Exception("Can't add points on different curves!")

        if isinstance(other, Ideal):
            return self

        x1, y1, x2, y2 = self.x, self.y, other.x, other.y

        x3 = ((x1 * y2) + (y1 * x2)) / (1 + self.curve.d * x1 * x2 * y1 * y2)
        y3 = ((y1 * y2) + (x1 * x2)) / (1 - self.curve.d * x1 * x2 * y1 * y2)

        return Point(x3, y3)

    def __sub__(self, other: "Point") -> "Point":
        return self + -other

    def __mul__(self, n: int) -> "Point":
        if not isinstance(n, int):
            raise Exception("Can't scale a point by something which isn't an int!")

        if n < 0:
            return -self * -n
        elif n == 0:
            return Ideal(self.curve)

        current = self
        product = Point(0, 1, self.curve)

        i = 1
        while i <= n:
            if n & i == i:
                product += current

            current += current
            i <<= 1

        return product

    def __rmul__(self, n: int):
        return self * n

    def __list__(self):
        return [self.x, self.y]

    def __eq__(self, other: object) -> bool:
        if type(other) is Ideal:
            return False
        elif self.curve != other.curve:
            return False

        return (self.x, self.y) == (other.x, other.y)

    def __ne__(self, other: object) -> bool:
        return not self == other

    def __getitem__(self, index: int) -> int:
        return [self.x, self.y][index]

    def double(self) -> "Point":
        return self + self


class Ideal(Point):
    """
    Represents the point at infinity of the curve
    """

    def __init__(self, curve):
        self.curve = curve

    def __neg__(self):
        return self

    def __str__(self):
        return "Ideal"

    def __add__(self, other: "Point") -> "Point":
        if not isinstance(other, Point):
            raise Exception("Can't add something that's not a point to a point")
        elif self.curve != other.curve:
            raise Exception("Can't add points on different curves!")

        return other

    def __mul__(self, n: int) -> "Point":
        if not isinstance(n, int):
            raise Exception("Can't scale a point by something which isn't an int!")

        return self

    def __eq__(self, other: object) -> bool:
        return type(other) is Ideal


if __name__ == "__main__":
    """
    main method for quick testing
    """
    n, t = 9, 2
    curve = Jubjub()

    p_actual = Point(0, 1)
    x_secret, y_secret = p_actual.x, p_actual.y

    p = Point(0, 1)
    print(p)
    ideal = Ideal(p.curve)
    print(ideal)

    print(p + ideal)
    print(2 * p + 3 * ideal)

    try:
        print(p * ideal)
    except Exception:
        print("correctly prevented multiplying points")
