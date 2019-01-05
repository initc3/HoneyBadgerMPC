from random import randint, shuffle
from honeybadgermpc.polynomial import get_omega, fnt_decode_step1, fnt_decode_step2


def test_poly_eval_at_k(galois_field, polynomial):
    poly1 = polynomial([0, 1])  # y = x
    for i in range(10):
        assert poly1(i) == i

    poly2 = polynomial([10, 0, 1])  # y = x^2 + 10
    for i in range(10):
        assert poly2(i) == pow(i, 2) + 10

    d = randint(1, 50)
    coeffs = [randint(0, galois_field.modulus-1) for i in range(d)]
    poly3 = polynomial(coeffs)  # random polynomial of degree d
    x = galois_field(randint(0, galois_field.modulus-1))
    y = sum([pow(x, i) * a for i, a in enumerate(coeffs)])
    assert y == poly3(x)


def test_evaluate_fft(galois_field, polynomial):
    d = randint(210, 300)
    coeffs = [randint(0, galois_field.modulus-1) for i in range(d)]
    poly = polynomial(coeffs)  # random polynomial of degree d
    n = len(poly.coeffs)
    n = n if n & n-1 == 0 else 2**n.bit_length()
    omega = get_omega(galois_field, n)
    fft_result = poly.evaluate_fft(omega, n)
    assert len(fft_result) == n
    for i, a in zip(range(1, 201, 2), fft_result[1:201:2]):  # verify only 100 points
        assert poly(pow(omega, i)) == a


def test_interpolate_fft(galois_field, polynomial):
    d = randint(210, 300)
    y = [randint(0, galois_field.modulus-1) for i in range(d)]
    n = len(y)
    n = n if n & n-1 == 0 else 2**n.bit_length()
    ys = y + [galois_field(0)] * (n - len(y))
    omega = get_omega(galois_field, n)
    poly = polynomial.interpolate_fft(ys, omega)
    for i, a in zip(range(1, 201, 2), ys[1:201:2]):  # verify only 100 points
        assert poly(pow(omega, i)) == a


def test_interp_extrap(galois_field, polynomial):
    d = randint(210, 300)
    y = [randint(0, galois_field.modulus-1) for i in range(d)]
    n = len(y)
    n = n if n & n-1 == 0 else 2**n.bit_length()
    ys = y + [galois_field(0)] * (n - len(y))
    omega = get_omega(galois_field, 2*n)
    values = polynomial.interp_extrap(ys, omega)
    for a, b in zip(ys, values[0:201:2]):  # verify only 100 points
        assert a == b


def test_fft_decode(GaloisField, Polynomial):
    d = randint(210, 300)
    coeffs = [randint(0, GaloisField.modulus-1) for i in range(d)]
    P = Polynomial(coeffs)
    n = d
    n = n if n & n-1 == 0 else 2**n.bit_length()
    omega2 = get_omega(GaloisField, 2*n)
    omega = omega2 ** 2

    # Create shares and erasures
    zs = list(range(n))
    shuffle(zs)
    zs = zs[:d]
    ys = list(P.evaluate_fft(omega, n))
    ys = [ys[i] for i in zs]

    As_, Ais_ = fnt_decode_step1(Polynomial, zs, omega2, n)
    Prec_ = fnt_decode_step2(Polynomial, zs, ys, As_, Ais_, omega2, n)
    print('Prec_(X):', Prec_)
    print('P(X):', P)
    assert Prec_.coeffs == P.coeffs
