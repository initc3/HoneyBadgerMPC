from random import randint
from honeybadgermpc.polynomial import get_omega


def test_poly_eval_at_k(GaloisField, Polynomial):
    poly1 = Polynomial([0, 1])  # y = x
    for i in range(10):
        assert poly1(i) == i

    poly2 = Polynomial([10, 0, 1])  # y = x^2 + 10
    for i in range(10):
        assert poly2(i) == pow(i, 2) + 10

    d = randint(1, 50)
    coeffs = [randint(0, GaloisField.modulus-1) for i in range(d)]
    poly3 = Polynomial(coeffs)  # random polynomial of degree d
    x = GaloisField(randint(0, GaloisField.modulus-1))
    y = sum([pow(x, i) * a for i, a in enumerate(coeffs)])
    assert y == poly3(x)


def test_evaluate_fft(GaloisField, Polynomial):
    d = randint(210, 300)
    coeffs = [randint(0, GaloisField.modulus-1) for i in range(d)]
    poly = Polynomial(coeffs)  # random polynomial of degree d
    n = len(poly.coeffs)
    n = n if n & n-1 == 0 else 2**n.bit_length()
    omega = get_omega(GaloisField, n)
    fftResult = poly.evaluate_fft(omega, n)
    assert len(fftResult) == n
    for i, a in zip(range(1, 201, 2), fftResult[1:201:2]):  # verify only 100 points
        assert poly(pow(omega, i)) == a


def test_interpolate_fft(GaloisField, Polynomial):
    d = randint(210, 300)
    y = [randint(0, GaloisField.modulus-1) for i in range(d)]
    n = len(y)
    n = n if n & n-1 == 0 else 2**n.bit_length()
    ys = y + [GaloisField(0)] * (n - len(y))
    omega = get_omega(GaloisField, n)
    poly = Polynomial.interpolate_fft(ys, omega)
    for i, a in zip(range(1, 201, 2), ys[1:201:2]):  # verify only 100 points
        assert poly(pow(omega, i)) == a


def test_interp_extrap(GaloisField, Polynomial):
    d = randint(210, 300)
    y = [randint(0, GaloisField.modulus-1) for i in range(d)]
    n = len(y)
    n = n if n & n-1 == 0 else 2**n.bit_length()
    ys = y + [GaloisField(0)] * (n - len(y))
    omega = get_omega(GaloisField, 2*n)
    values = Polynomial.interp_extrap(ys, omega)
    for a, b in zip(ys, values[0:201:2]):  # verify only 100 points
        assert a == b
