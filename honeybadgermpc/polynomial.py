import operator
import random
from functools import reduce
from .field import GF, GFElement
from itertools import zip_longest
from .betterpairing import ZR
from .elliptic_curve import Subgroup


def strip_trailing_zeros(a):
    if len(a) == 0:
        return []
    for i in range(len(a), 0, -1):
        if a[i-1] != 0:
            break
    return a[:i]


_poly_cache = {}


def polynomialsOver(field):
    if field in _poly_cache:
        return _poly_cache[field]

    USE_RUST = False
    if field.modulus == Subgroup.BLS12_381:
        USE_RUST = False
        print('using bls12_381_r')

    class Polynomial(object):
        def __init__(self, coeffs):
            self.coeffs = list(strip_trailing_zeros(coeffs))
            for i in range(len(self.coeffs)):
                if type(self.coeffs[i]) is int:
                    self.coeffs[i] = field(self.coeffs[i])
            if USE_RUST:
                self._zrcoeffs = [ZR(c.value) for c in self.coeffs]
            self.field = field

        def isZero(self):
            return self.coeffs == [] or (len(self.coeffs) == 1 and self.coeffs[0] == 0)

        def __repr__(self):
            if self.isZero():
                return '0'
            return ' + '.join(['%s x^%d' % (a, i) if i > 0 else '%s' % a
                               for i, a in enumerate(self.coeffs)])

        def __call__(self, x):
            if USE_RUST:
                assert type(x) is int
                x = ZR(x)
                k = len(self.coeffs) - 1
                y = ZR(0)
                for i in range(k):
                    y *= x
                    y += self._zrcoeffs[k-i]
                return field(int(y))
            else:
                y = 0
                xx = 1
                for coeff in self.coeffs:
                    y += coeff * xx
                    xx *= x
                return y

        @classmethod
        def interpolate_at(cls, shares, x_recomb=field(0)):
            # shares are in the form (x, y=f(x))
            if type(x_recomb) is int:
                x_recomb = field(x_recomb)
            assert type(x_recomb) is GFElement
            xs, ys = zip(*shares)
            vector = []
            for i, x_i in enumerate(xs):
                factors = [(x_k - x_recomb) / (x_k - x_i)
                           for k, x_k in enumerate(xs) if k != i]
                vector.append(reduce(operator.mul, factors))
            return sum(map(operator.mul, ys, vector))

        _lagrangeCache = {}  # Cache lagrange polynomials

        @classmethod
        def interpolate(cls, shares):
            X = cls([field(0), field(1)])  # This is the polynomial f(x) = x
            ONE = cls([field(1)])  # This is the polynomial f(x) = 1
            xs, ys = zip(*shares)

            def lagrange(xi):
                # Let's cache lagrange values
                if (xs, xi) in cls._lagrangeCache:
                    return cls._lagrangeCache[(xs, xi)]

                def mul(a, b): return a*b
                num = reduce(mul, [X - cls([xj])
                                   for xj in xs if xj != xi], ONE)
                den = reduce(mul, [xi - xj for xj in xs if xj != xi], field(1))
                p = num * cls([1 / den])
                cls._lagrangeCache[(xs, xi)] = p
                return p
            f = cls([0])
            for xi, yi in zip(xs, ys):
                pi = lagrange(xi)
                f += cls([yi]) * pi
            return f

        @classmethod
        def interpolate_fft(cls, ys, omega):
            """
            Returns a polynoial f of given degree,
            such that f(omega^i) == ys[i]
            """
            n = len(ys)
            assert n & (n-1) == 0, "n must be power of two"
            assert type(omega) is GFElement
            assert omega ** n == 1, "must be an n'th root of unity"
            assert omega ** (n //
                             2) != 1, "must be a primitive n'th root of unity"
            coeffs = [b/n for b in fft_helper(ys, 1/omega, field)]
            return cls(coeffs)

        def evaluate_fft(self, omega, n):
            assert n & (n-1) == 0, "n must be power of two"
            assert type(omega) is GFElement
            assert omega ** n == 1, "must be an n'th root of unity"
            assert omega ** (n //
                             2) != 1, "must be a primitive n'th root of unity"
            return fft(self, omega, n)

        @classmethod
        def random(cls, degree, y0=None):
            coeffs = [field(random.randint(0, field.modulus-1))
                      for _ in range(degree+1)]
            if y0 is not None:
                coeffs[0] = y0
            return cls(coeffs)

        @classmethod
        def interp_extrap(cls, xs, omega):
            """
            Interpolates the polynomial based on the even points omega^2i
            then evaluates at all points omega^i
            """
            n = len(xs)
            assert n & (n-1) == 0, "n must be power of 2"
            assert pow(omega, 2*n) == 1, "omega must be 2n'th root of unity"
            assert pow(
                omega, n) != 1, "omega must be primitive 2n'th root of unity"

            # Interpolate the polynomial up to degree n
            poly = cls.interpolate_fft(xs, omega**2)

            # Evaluate the polynomial
            xs2 = poly.evaluate_fft(omega, 2*n)

            return xs2

        # the valuation only gives 0 to the zero polynomial, i.e. 1+degree
        def __abs__(self): return len(self.coeffs)

        def __iter__(self): return iter(self.coeffs)

        def __sub__(self, other): return self + (-other)

        def __neg__(self): return Polynomial([-a for a in self])

        def __len__(self): return len(self.coeffs)

        def __add__(self, other):
            newCoefficients = [sum(x) for x in zip_longest(
                self, other, fillvalue=self.field(0))]
            return Polynomial(newCoefficients)

        def __mul__(self, other):
            if self.isZero() or other.isZero():
                return Zero()

            newCoeffs = [self.field(0)
                         for _ in range(len(self) + len(other) - 1)]

            for i, a in enumerate(self):
                for j, b in enumerate(other):
                    newCoeffs[i+j] += a*b
            return Polynomial(newCoeffs)

        def degree(self): return abs(self) - 1

        def leadingCoefficient(self): return self.coeffs[-1]

        def __divmod__(self, divisor):
            quotient, remainder = Zero(), self
            divisorDeg = divisor.degree()
            divisorLC = divisor.leadingCoefficient()

            while remainder.degree() >= divisorDeg:
                monomialExponent = remainder.degree() - divisorDeg
                monomialZeros = [self.field(0)
                                 for _ in range(monomialExponent)]
                monomialDivisor = Polynomial(
                    monomialZeros + [remainder.leadingCoefficient() / divisorLC])

                quotient += monomialDivisor
                remainder -= monomialDivisor * divisor

            return quotient, remainder

        def __truediv__(self, divisor):
            if divisor.isZero():
                raise ZeroDivisionError
            return divmod(self, divisor)[0]

        def __mod__(self, divisor):
            if divisor.isZero():
                raise ZeroDivisionError
            return divmod(self, divisor)[1]

    def Zero():
        return Polynomial([])

    _poly_cache[field] = Polynomial
    return Polynomial


def get_omega(field, n, seed=None):
    """
    Given a field, this method returns an n^th root of unity.
    If the seed is not None then this method will return the
    same n'th root of unity for every run with the same seed

    This only makes sense if n is a power of 2!
    """
    assert n & n-1 == 0, "n must be a power of 2"
    if seed is not None:
        random.seed(seed)
    x = field(random.randint(0, field.modulus-1))
    y = pow(x, (field.modulus-1)//n)
    if y == 1 or pow(y, n//2) == 1:
        return get_omega(field, n)
    assert pow(y, n) == 1, "omega must be 2n'th root of unity"
    assert pow(y, n//2) != 1, "omega must be primitive 2n'th root of unity"
    return y


def fft_helper(A, omega, field):
    """
    Given coefficients A of polynomial this method does FFT and returns
    the evaluation of the polynomial at [omega^0, omega^(n-1)]

    If the polynomial is a0*x^0 + a1*x^1 + ... + an*x^n then the coefficients
    list is of the form [a0, a1, ... , an].
    """
    n = len(A)
    assert not (n & (n-1)), "n must be a power of 2"

    if n == 1:
        return A

    B, C = A[0::2], A[1::2]
    B_bar = fft_helper(B, pow(omega, 2), field)
    C_bar = fft_helper(C, pow(omega, 2), field)
    A_bar = [field(1)]*(n)
    for j in range(n):
        k = (j % (n//2))
        A_bar[j] = B_bar[k] + pow(omega, j) * C_bar[k]
    return A_bar


def fft(poly, omega, n, seed=None):
    assert n & n-1 == 0, "n must be a power of 2"
    assert len(poly.coeffs) <= n
    assert pow(omega, n) == 1
    assert pow(omega, n//2) != 1

    paddedCoeffs = poly.coeffs + ([poly.field(0)] * (n-len(poly.coeffs)))
    return fft_helper(paddedCoeffs, omega, poly.field)


if __name__ == "__main__":
    field = GF.get(Subgroup.BLS12_381)
    Poly = polynomialsOver(field)
    poly = Poly.random(degree=7)
    poly = Poly([1, 5, 3, 15, 0, 3])
    n = 2**3
    omega = get_omega(field, n, seed=1)
    omega2 = get_omega(field, n, seed=4)
    # FFT
    # x = fft(poly, omega=omega, n=n, test=True, enable_profiling=True)
    x = poly.evaluate_fft(omega, n)
    # IFFT
    x2 = [b/n for b in fft_helper(x, 1/omega, field)]
    poly2 = Poly.interpolate_fft(x2, omega)
    print(poly2)

    print('omega1:', omega ** (n//2))
    print('omega2:', omega2 ** (n//2))

    print('eval:')
    omega = get_omega(field, 2*n)
    for i in range(len(x)):
        print(omega**(2*i), x[i])
    print('interp_extrap:')
    x3 = Poly.interp_extrap(x, omega)
    for i in range(len(x3)):
        print(omega**i, x3[i])

    print("How many omegas are there?")
    for i in range(10):
        omega = get_omega(field, 2**20)
        print(omega, omega**(2**17))
