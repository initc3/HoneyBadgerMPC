from random import randint, shuffle

from honeybadgermpc.polynomial import fnt_decode_step1, fnt_decode_step2, get_omega


def test_poly_eval_at_k(galois_field, polynomial):
    poly1 = polynomial([0, 1])  # y = x
    for i in range(10):
        assert poly1(i) == i

    poly2 = polynomial([10, 0, 1])  # y = x^2 + 10
    for i in range(10):
        assert poly2(i) == pow(i, 2) + 10

    d = randint(1, 50)
    coeffs = [galois_field.random().value for i in range(d)]
    poly3 = polynomial(coeffs)  # random polynomial of degree d
    x = galois_field.random()
    y = sum([pow(x, i) * a for i, a in enumerate(coeffs)])
    assert y == poly3(x)


def test_evaluate_fft(galois_field, polynomial):
    d = randint(210, 300)
    coeffs = [galois_field.random().value for i in range(d)]
    poly = polynomial(coeffs)  # random polynomial of degree d
    n = len(poly.coeffs)
    n = n if n & n - 1 == 0 else 2 ** n.bit_length()
    omega = get_omega(galois_field, n)
    fft_result = poly.evaluate_fft(omega, n)
    assert len(fft_result) == n
    for i, a in zip(range(1, 201, 2), fft_result[1:201:2]):  # verify only 100 points
        assert poly(pow(omega, i)) == a


def test_interpolate_fft(galois_field, polynomial):
    d = randint(210, 300)
    y = [galois_field.random().value for i in range(d)]
    n = len(y)
    n = n if n & n - 1 == 0 else 2 ** n.bit_length()
    ys = y + [galois_field(0)] * (n - len(y))
    omega = get_omega(galois_field, n)
    poly = polynomial.interpolate_fft(ys, omega)
    for i, a in zip(range(1, 201, 2), ys[1:201:2]):  # verify only 100 points
        assert poly(pow(omega, i)) == a


def test_interp_extrap(galois_field, polynomial):
    d = randint(210, 300)
    y = [galois_field.random().value for i in range(d)]
    n = len(y)
    n = n if n & n - 1 == 0 else 2 ** n.bit_length()
    ys = y + [galois_field(0)] * (n - len(y))
    omega = get_omega(galois_field, 2 * n)
    values = polynomial.interp_extrap(ys, omega)
    for a, b in zip(ys, values[0:201:2]):  # verify only 100 points
        assert a == b


def test_interp_extrap_cpp(galois_field, polynomial):
    d = randint(210, 300)
    y = [galois_field.random().value for i in range(d)]
    n = len(y)
    n = n if n & n - 1 == 0 else 2 ** n.bit_length()
    ys = y + [0] * (n - len(y))
    omega = get_omega(galois_field, 2 * n)
    values = polynomial.interp_extrap_cpp(ys, omega)
    for a, b in zip(ys, values[0:201:2]):  # verify only 100 points
        assert a == b


def test_fft_decode(galois_field, polynomial):
    d = randint(210, 300)
    coeffs = [galois_field.random().value for i in range(d)]
    poly = polynomial(coeffs)
    n = d
    n = n if n & n - 1 == 0 else 2 ** n.bit_length()
    omega2 = get_omega(galois_field, 2 * n)
    omega = omega2 ** 2

    # Create shares and erasures
    zs = list(range(n))
    shuffle(zs)
    zs = zs[:d]
    ys = list(poly.evaluate_fft(omega, n))
    ys = [ys[i] for i in zs]

    as_, ais_ = fnt_decode_step1(polynomial, zs, omega2, n)
    prec_ = fnt_decode_step2(polynomial, zs, ys, as_, ais_, omega2, n)
    print("Prec_(X):", prec_)
    print("P(X):", poly)
    assert prec_.coeffs == poly.coeffs


def test_poly_interpolate_at(galois_field, polynomial):
    # Take x^2 + 10 as the polynomial
    values = [(i, pow(i, 2) + 10) for i in range(3)]
    k = galois_field.random()
    assert polynomial.interpolate_at(values, k) == pow(k, 2) + 10


def test_poly_interpolate_at_random(galois_field, polynomial):
    t = randint(10, 50)
    random_poly = polynomial.random(t)
    values = [(i, random_poly(i)) for i in range(t + 1)]
    k = galois_field.random()
    assert polynomial.interpolate_at(values, k) == random_poly(k)


####################################################################################
# Test cases to cover the scenario when ZR is used.
####################################################################################


def test_rust_poly_eval_at_k(rust_field, rust_polynomial):
    poly1 = rust_polynomial([0, 1])  # y = x
    for i in range(10):
        assert poly1(i) == i

    poly2 = rust_polynomial([10, 0, 1])  # y = x^2 + 10
    for i in range(10):
        assert poly2(i) == pow(i, 2) + 10

    d = randint(1, 50)
    coeffs = [rust_field.random() for i in range(d)]
    poly3 = rust_polynomial(coeffs)  # random polynomial of degree d
    x = rust_field.random()
    y = sum([pow(x, i) * a for i, a in enumerate(coeffs)])
    assert y == poly3(x)


def test_rust_poly_interpolate_at(rust_field, rust_polynomial):
    # Take x^2 + 10 as the polynomial
    values = [(i, pow(i, 2) + 10) for i in range(3)]
    k = rust_field.random()
    assert rust_polynomial.interpolate_at(values, k) == pow(k, 2) + 10


def test_rust_poly_interpolate_at_random(rust_field, rust_polynomial):
    t = randint(10, 50)
    random_poly = rust_polynomial.random(t)
    values = [(i, random_poly(i)) for i in range(t + 1)]
    k = rust_field.random()
    assert rust_polynomial.interpolate_at(values, k) == random_poly(k)
