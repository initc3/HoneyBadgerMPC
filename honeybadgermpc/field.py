# Copyright 2019 Decentralized Systems Lab
#
# This file (field.py) began as a modification of a file from
# Viff, the copyright notice for which is posted below.
# See https://viff.dk/
#
# Copyright 2007, 2008 VIFF Development Team.
#
# This file is part of VIFF, the Virtual Ideal Functionality Framework.
#
# VIFF is free software: you can redistribute it and/or modify it
# under the terms of the GNU Lesser General Public License (LGPL) as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# VIFF is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
# or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Lesser General
# Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with VIFF. If not, see <http://www.gnu.org/licenses/>.
from gmpy2 import is_prime, mpz
from random import Random


class FieldsNotIdentical(Exception):
    pass


class FieldElement(object):
    """Common base class for elements."""

    def __int__(self):
        return self.value

    __long__ = __int__


class GF(object):
    # Class is implemented following the 'multiton' design pattern
    # When the constructor is called with a value that's been used
    # before, it returns the previously created field, such that all
    # fields with the same modulus are the same object
    _field_cache = {}

    def __new__(cls, modulus):
        # Creates a new field if not present in the cache
        return GF._field_cache.setdefault(modulus, super(GF, cls).__new__(cls))

    def __init__(self, modulus):
        if not is_prime(mpz(modulus)):
            raise ValueError(f"{modulus} is not a prime")

        self.modulus = modulus

    def __call__(self, value):
        return GFElement(value, self)

    def __reduce__(self):
        return (GF, (self.modulus,))

    def random(self, seed=None):
        return GFElement(Random(seed).randint(0, self.modulus - 1), self)


class GFElement(FieldElement):
    def __init__(self, value, gf):
        self.modulus = gf.modulus
        self.field = gf
        self.value = value % self.modulus

    def __add__(self, other):
        """Addition."""
        if not isinstance(other, (GFElement, int)):
            return NotImplemented
        try:
            # We can do a quick test using 'is' here since
            # there will only be one class representing this
            # field.
            if self.field is not other.field:
                raise FieldsNotIdentical
            return GFElement(self.value + other.value, self.field)
        except AttributeError:
            return GFElement(self.value + other, self.field)

    __radd__ = __add__

    def __sub__(self, other):
        """Subtraction."""
        if not isinstance(other, (GFElement, int)):
            return NotImplemented
        try:
            if self.field is not other.field:
                raise FieldsNotIdentical
            return GFElement(self.value - other.value, self.field)
        except AttributeError:
            return GFElement(self.value - other, self.field)

    def __rsub__(self, other):
        """Subtraction (reflected argument version)."""
        return GFElement(other - self.value, self.field)

    def __mul__(self, other):
        """Multiplication."""
        if not isinstance(other, (GFElement, int)):
            return NotImplemented
        try:
            if self.field is not other.field:
                raise FieldsNotIdentical
            return GFElement(self.value * other.value, self.field)
        except AttributeError:
            return GFElement(self.value * other, self.field)

    __rmul__ = __mul__

    def __pow__(self, exponent):
        """Exponentiation."""
        return GFElement(pow(self.value, exponent, self.modulus), self.field)

    def __neg__(self):
        """Negation."""
        return GFElement(-self.value, self.field)

    def __invert__(self):
        """Inversion.

        Note that zero cannot be inverted, trying to do so
        will raise a ZeroDivisionError.
        """
        if self.value == 0:
            raise ZeroDivisionError("Cannot invert zero")

        def extended_gcd(a, b):
            """The extended Euclidean algorithm."""
            x = 0
            lastx = 1
            y = 1
            lasty = 0
            while b != 0:
                quotient = a // b
                a, b = b, a % b
                x, lastx = lastx - quotient * x, x
                y, lasty = lasty - quotient * y, y
            return (lastx, lasty, a)

        inverse = extended_gcd(self.value, self.modulus)[0]
        return GFElement(inverse, self.field)

    def __div__(self, other):
        """Division."""
        try:
            if self.field is not other.field:
                raise FieldsNotIdentical
            return self * ~other
        except AttributeError:
            return self * ~GFElement(other, self.field)

    __truediv__ = __div__
    __floordiv__ = __div__

    def __rdiv__(self, other):
        """Division (reflected argument version)."""
        return GFElement(other, self.field) / self

    __rtruediv__ = __rdiv__
    __rfloordiv__ = __rdiv__

    def sqrt(self):
        """Square root.
        No attempt is made the to return the positive square root.
        """
        assert self.modulus % 2 == 1, "Modulus must be odd"
        assert pow(self, (self.modulus - 1) // 2) == 1

        if self.modulus % 4 == 3:
            # The case that the modulus is a Blum prime
            # (congruent to 3 mod 4), there will be no remainder in the
            # division below.
            root = pow(self.value, (self.modulus + 1) // 4)
            return GFElement(root, self.field)
        else:
            # The case that self.modulus % 4 == 1
            # Cipolla’s Algorithm
            # http://people.math.gatech.edu/~mbaker/pdf/cipolla2011.pdf
            t = u = 0
            for i in range(1, self.modulus):
                u = i * i - self
                if pow(u, (self.modulus - 1) // 2) == self.modulus - 1:
                    t = i
                    break

            def cipolla_mult(a, b, w):
                return ((a[0] * b[0] + a[1] * b[1] * w), (a[0] * b[1] + a[1] * b[0]))

            exp = (self.modulus + 1) // 2
            exp_bin = bin(exp)[2:]
            x1 = (t, 1)
            x2 = cipolla_mult(x1, x1, u)
            for i in range(1, len(exp_bin)):
                if exp_bin[i] == "0":
                    x2 = cipolla_mult(x2, x1, u)
                    x1 = cipolla_mult(x1, x1, u)
                else:
                    x1 = cipolla_mult(x1, x2, u)
                    x2 = cipolla_mult(x2, x2, u)
            return x1[0]

    def bit(self, index):
        """Extract a bit (index is counted from zero)."""
        return (self.value >> index) & 1

    def signed(self):
        """Return a signed integer representation of the value.

        If x > floor(p/2) then subtract p to obtain negative integer.
        """
        if self.value > ((self.modulus - 1) / 2):
            return self.value - self.modulus
        else:
            return self.value

    def unsigned(self):
        """Return a unsigned representation of the value"""
        return self.value

    def __repr__(self):
        return "{%d}" % self.value
        # return "GFElement(%d)" % self.value

    def __str__(self):
        """Informal string representation.

        This is simply the value enclosed in curly braces.
        """
        return "{%d}" % self.unsigned()

    def __eq__(self, other):
        """Equality test."""
        try:
            if self.field is not other.field:
                raise FieldsNotIdentical
            return self.value == other.value
        except AttributeError:
            return self.value == other

    def __ne__(self, other):
        """Inequality test."""
        try:
            if self.field is not other.field:
                raise FieldsNotIdentical
            return self.value != other.value
        except AttributeError:
            return self.value != other

    def __cmp__(self, other):
        """Comparison."""
        try:
            if self.field is not other.field:
                raise FieldsNotIdentical
            # TODO Replace with (a > b) - (a < b)
            # see https://docs.python.org/3/whatsnew/3.0.html#ordering-comparisons
            return cmp(self.value, other.value)  # noqa  XXX until above is done
        except AttributeError:
            # TODO Replace with (a > b) - (a < b)
            # see https://docs.python.org/3/whatsnew/3.0.html#ordering-comparisons
            return cmp(self.value, other)  # noqa XXX until above is done

    def __hash__(self):
        """Hash value."""
        return hash((self.field, self.value))

    def __bool__(self):
        """Truth value testing.

        Returns False if this element is zero, True otherwise.
        This allows GF elements to be used directly in Boolean
        formula:

        >>> bool(GF256(0))
        False
        >>> bool(GF256(1))
        True
        >>> x = GF256(1)
        >>> not x
        False
        """
        return self.value != 0


def fake_gf(modulus):
    """Construct a fake field.

    These fields should only be used in benchmarking. They work like
    any other field except that all computations will give ``-1`` as
    the result:

    >>> F = FakeGF(1031)
    >>> a = F(123)
    >>> b = F(234)
    >>> a + b
    {{1030}}
    >>> a * b
    {{1030}}
    >>> a.sqrt()
    {{1030}}
    >>> a.bit(100)
    1
    """

    # Return value of all operations on FakeFieldElements. We choose
    # this value to maximize the communication complexity.
    return_value = modulus - 1

    class FakeFieldElement(FieldElement):
        """Fake field which does no computations."""

        def __init__(self, value):
            """Create a fake field element.

            The element will store *value* in order to take up a realistic
            amount of RAM, but any further computation will yield the
            value ``-1``.
            """
            self.value = value

        # Binary operations.
        __add__ = (
            __radd__
        ) = (
            __sub__
        ) = (
            __rsub__
        ) = (
            __mul__
        ) = (
            __rmul__
        ) = (
            __div__
        ) = (
            __rdiv__
        ) = (
            __truediv__
        ) = (
            __rtruediv__
        ) = (
            __floordiv__
        ) = __rfloordiv__ = __pow__ = __neg__ = lambda self, other: FakeFieldElement(
            return_value
        )

        # Unary operations.
        __invert__ = sqrt = lambda self: FakeFieldElement(return_value)

        # Bit extraction. We pretend that the number is *very* big.
        def bit(self, index):
            return 1  # noqa  XXX for the time being

        # Fake field elements are printed with double curly brackets.
        __repr__ = __str__ = lambda self: "{{%d}}" % self.value

    FakeFieldElement.field = FakeFieldElement
    FakeFieldElement.modulus = modulus
    return FakeFieldElement


if __name__ == "__main__":
    import doctest  # pragma NO COVER

    doctest.testmod()  # pragma NO COVER
