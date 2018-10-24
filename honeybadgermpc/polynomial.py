import operator
import random
from functools import reduce


def strip_trailing_zeros(a):
    for i in range(len(a), 0, -1):
        if a[i-1] != 0:
            break
    return a[:i]


_poly_cache = {}


def polynomialsOver(field):
    if field in _poly_cache:
        return _poly_cache[field]

    class Polynomial(object):
        def __init__(self, coeffs):
            self.coeffs = strip_trailing_zeros(coeffs)
            self.field = field

        def isZero(self): return self.coeffs == []

        def __repr__(self):
            if self.isZero():
                return '0'
            return ' + '.join(['%s x^%d' % (a, i) if i > 0 else '%s' % a
                               for i, a in enumerate(self.coeffs)])

        def __call__(self, x):
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
            assert type(x_recomb) is field
            xs, ys = zip(*shares)
            vector = []
            for i, x_i in enumerate(xs):
                factors = [(x_k - x_recomb) / (x_k - x_i)
                           for k, x_k in enumerate(xs) if k != i]
                vector.append(reduce(operator.mul, factors))
            return sum(map(operator.mul, ys, vector))

        @classmethod
        def interpolate_fft(cls, ys, omega):
            """
            Returns a polynoial f of given degree,
            such that f(omega^i) == ys[i]
            """
            n = len(ys)
            assert n & (n-1) == 0, "n must be power of two"
            assert type(omega) is field
            assert omega ** n == 1, "must be an n'th root of unity"
            assert omega ** (n//2) != 1, "must be a primitive n'th root of unity"
            coeffs = [b/n for b in fft_helper(ys, 1/omega, field)]
            return cls(coeffs)

        def evaluate_fft(self, omega, n):
            assert n & (n-1) == 0, "n must be power of two"
            assert type(omega) is field
            assert omega ** n == 1, "must be an n'th root of unity"
            assert omega ** (n//2) != 1, "must be a primitive n'th root of unity"
            return fft(self, omega, n)

        @classmethod
        def random(cls, degree, y0=None):
            coeffs = [field(random.randint(0, field.modulus-1)) for _ in range(degree+1)]
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
            assert pow(omega, n) != 1, "omega must be primitive 2n'th root of unity"

            # Interpolate the polynomial up to degree n
            poly = cls.interpolate_fft(xs, omega**2)

            # Evaluate the polynomial
            xs2 = poly.evaluate_fft(omega, 2*n)

            return xs2

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
    from .field import GF
    field = GF.get(0x73eda753299d7d483339d80809a1d80553bda402fffe5bfeffffffff00000001)
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
