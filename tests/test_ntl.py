from honeybadgermpc.ntl import (
    lagrange_interpolate,
    vandermonde_batch_interpolate,
    vandermonde_batch_evaluate,
    fft,
    fft_interpolate,
    fft_batch_interpolate,
    gao_interpolate,
    evaluate,
    sqrt_mod,
    partial_fft,
    fft_batch_evaluate,
)
import random


def test_interpolate(galois_field):
    # Given
    x = [1, 2]
    y = [1, 2]
    p = galois_field.modulus

    # When
    poly = lagrange_interpolate(x, y, p)

    # Then
    assert poly == [0, 1]


def test_batch_vandermonde_interpolate(galois_field):
    # Given
    x = [1, 2]
    y = [[1, 2], [3, 5]]
    p = galois_field.modulus

    # When
    polynomials = vandermonde_batch_interpolate(x, y, p)

    # Then
    assert polynomials == [[0, 1], [1, 2]]


def test_batch_vandermonde_evaluate(galois_field):
    # Given
    x = [1, 2]
    polynomials = [[0, 1], [1, 2]]
    p = galois_field.modulus

    # When
    y = vandermonde_batch_evaluate(x, polynomials, p)

    # Then
    assert y == [[1, 2], [3, 5]]


def test_fft():
    # Given
    coeffs = [0, 1]
    p = 13
    omega = 5
    n = 4

    # When
    fft_rep = fft(coeffs, omega, p, n)

    # Then
    assert fft_rep == [1, 5, 12, 8]


def test_fft_big(galois_field, galois_field_roots):
    # Given
    d = 20
    p = galois_field.modulus
    r = 5
    n = 2 ** r
    omega = galois_field_roots[r]
    coeffs = [galois_field.random().value for _ in range(d)]

    # When
    fft_rep = fft(coeffs, omega, p, n)

    # Then
    assert len(fft_rep) == n
    for i in range(n):
        x = pow(omega, i, p)
        assert fft_rep[i] == sum(coeffs[j] * pow(x, j, p) for j in range(d)) % p


def test_fft_batch_evaluate_big(galois_field, galois_field_roots):
    # Given
    d = 20
    # Only evaluations of first 25 powers
    k = 25
    p = galois_field.modulus
    r = 5
    n = 2 ** r
    batch_size = 64
    omega = galois_field_roots[r]
    coeffs = [
        [galois_field.random().value for _ in range(d)] for _ in range(batch_size)
    ]

    # When
    fft_rep = fft_batch_evaluate(coeffs, omega, p, n, k)

    # Then
    assert len(fft_rep) == batch_size
    for i in range(batch_size):
        assert len(fft_rep[i]) == k
        for j in range(k):
            x = pow(omega, j, p)
            assert (
                fft_rep[i][j] == sum(coeffs[i][l] * pow(x, l, p) for l in range(d)) % p
            )


def test_partial_fft_big(galois_field, galois_field_roots):
    # Given
    d = 20
    p = galois_field.modulus
    r = 5
    n = 2 ** r
    omega = galois_field_roots[r]
    coeffs = [galois_field.random().value for _ in range(d)]
    k = 25

    # When
    fft_rep = partial_fft(coeffs, omega, p, n, k)

    # Then
    assert len(fft_rep) == k
    for i in range(k):
        x = pow(omega, i, p)
        assert fft_rep[i] == sum(coeffs[j] * pow(x, j, p) for j in range(d)) % p


def test_fft_interpolate(galois_field, galois_field_roots):
    # Given
    r = 3
    n = 2 ** r
    p = galois_field.modulus
    omega = galois_field_roots[r]
    zs = [3, 0]
    xs = [pow(omega, z, p) for z in zs]
    # Polynomial = 2x + 1
    poly = [1, 2]
    ys = [sum(poly[i] * pow(x, i, p) for i in range(len(poly))) % p for x in xs]
    p = galois_field.modulus

    # When
    interp_poly = fft_interpolate(zs, ys, omega, p, n)

    # Then
    assert interp_poly == poly


def test_fft_batch_interpolate(galois_field, galois_field_roots):
    # Given
    r = 3
    n = 2 ** r
    p = galois_field.modulus
    omega = galois_field_roots[r]
    zs = [3, 0, 5]
    xs = [pow(omega, z, p) for z in zs]
    # Polynomials = 2x + 1, x^2 + 2x + 3, 2x^2 + 4x + 3
    polys = [[1, 2, 0], [3, 2, 1], [3, 4, 2]]
    ys = [
        [sum(poly[i] * pow(x, i, p) for i in range(len(poly))) % p for x in xs]
        for poly in polys
    ]
    p = galois_field.modulus

    # When
    interp_polys = fft_batch_interpolate(zs, ys, omega, p, n)

    # Then
    assert interp_polys == polys


def test_evaluate(galois_field, polynomial):
    # Given
    p = galois_field.modulus
    coeffs = [1, 2, 3, 4]
    poly = polynomial(coeffs)
    xs = [random.randint(0, p - 1) for _ in range(100)]

    # When
    ys = [evaluate(coeffs, x, p) for x in xs]

    # Then
    assert ys == [poly(x).value for x in xs]


def test_gao_interpolate():
    int_msg = [2, 3, 2, 8, 7, 5, 9, 5]
    k = len(int_msg)  # length of message
    n = 22  # size of encoded message
    p = 53  # prime
    t = k - 1  # degree of polynomial

    x = list(range(n))
    encoded = [
        sum(int_msg[j] * pow(x[i], j, p) for j in range(k)) % p for i in range(n)
    ]

    # Check decoding with no errors
    decoded, _ = gao_interpolate(x, encoded, k, p)
    assert decoded == int_msg

    # Corrupt with maximum number of erasures:
    cmax = n - 2 * t - 1
    corrupted = corrupt(encoded, num_errors=0, num_nones=cmax)
    coeffs, _ = gao_interpolate(x, corrupted, k, p)
    assert coeffs == int_msg

    # Corrupt with maximum number of errors:
    emax = (n - 2 * t - 1) // 2
    corrupted = corrupt(encoded, num_errors=emax, num_nones=0)
    coeffs, _ = gao_interpolate(x, corrupted, k, p)
    assert coeffs == int_msg

    # Corrupt with a mixture of errors and erasures
    e = emax // 2
    c = cmax // 4
    corrupted = corrupt(encoded, num_errors=e, num_nones=c)
    coeffs, _ = gao_interpolate(x, corrupted, k, p)
    assert coeffs == int_msg


def test_gao_interpolate_all_zeros():
    int_msg = [0, 0, 0, 0, 0, 0, 0, 0]
    k = len(int_msg)  # length of message
    n = 22  # size of encoded message
    p = 53  # prime
    t = k - 1  # degree of polynomial

    x = list(range(n))
    encoded = [
        sum(int_msg[j] * pow(x[i], j, p) for j in range(k)) % p for i in range(n)
    ]

    # Check decoding with no errors
    decoded, _ = gao_interpolate(x, encoded, k, p)
    assert decoded == int_msg

    # Corrupt with maximum number of erasures:
    cmax = n - 2 * t - 1
    corrupted = corrupt(encoded, num_errors=0, num_nones=cmax)
    coeffs, _ = gao_interpolate(x, corrupted, k, p)
    assert coeffs == int_msg

    # Corrupt with maximum number of errors:
    emax = (n - 2 * t - 1) // 2
    corrupted = corrupt(encoded, num_errors=emax, num_nones=0)
    coeffs, _ = gao_interpolate(x, corrupted, k, p)
    assert coeffs == int_msg

    # Corrupt with a mixture of errors and erasures
    e = emax // 2
    c = cmax // 4
    corrupted = corrupt(encoded, num_errors=e, num_nones=c)
    coeffs, _ = gao_interpolate(x, corrupted, k, p)
    assert coeffs == int_msg


def test_gao_interpolate_fft(galois_field, galois_field_roots):
    int_msg = [2, 3, 2, 8, 7, 5, 9, 5]
    k = len(int_msg)  # length of message
    n = 22  # size of encoded message
    p = galois_field.modulus  # prime
    r = 5  # 2 ** 5 = 32 > 22
    omega = galois_field_roots[r]
    order = 2 ** 5  # = 32
    t = k - 1  # degree of polynomial

    z = list(range(n))
    x = [pow(omega, zi, p) for zi in z]
    encoded = [
        sum(int_msg[j] * pow(x[i], j, p) for j in range(k)) % p for i in range(n)
    ]

    # Check decoding with no errors
    decoded, _ = gao_interpolate(
        x, encoded, k, p, z=z, omega=omega, order=order, use_omega_powers=True
    )
    # decoded, _ = gao_interpolate(x, encoded, k, p)
    assert decoded == int_msg

    # Corrupt with maximum number of erasures:
    cmax = n - 2 * t - 1
    corrupted = corrupt(encoded, num_errors=0, num_nones=cmax)
    coeffs, _ = gao_interpolate(
        x, corrupted, k, p, z=z, omega=omega, order=order, use_omega_powers=True
    )
    assert coeffs == int_msg

    # Corrupt with maximum number of errors:
    emax = (n - 2 * t - 1) // 2
    corrupted = corrupt(encoded, num_errors=emax, num_nones=0)
    coeffs, _ = gao_interpolate(
        x, corrupted, k, p, z=z, omega=omega, order=order, use_omega_powers=True
    )
    assert coeffs == int_msg

    # Corrupt with a mixture of errors and erasures
    e = emax // 2
    c = cmax // 4
    corrupted = corrupt(encoded, num_errors=e, num_nones=c)
    coeffs, _ = gao_interpolate(
        x, corrupted, k, p, z=z, omega=omega, order=order, use_omega_powers=True
    )
    assert coeffs == int_msg


def corrupt(message, num_errors, num_nones, min_val=0, max_val=131):
    """
    Inserts random corrupted values
    """
    message = list.copy(message)
    assert len(message) >= num_errors + num_nones, "too much errors and none elements!"
    indices = random.sample(list(range(len(message))), num_errors + num_nones)
    for i in range(0, num_errors):
        message[indices[i]] = random.randint(min_val, max_val)
    for i in range(0, num_nones):
        message[indices[i + num_errors]] = None
    return message


def test_sqrt_mod(galois_field):
    p = galois_field.modulus
    random.seed(0)
    x = [random.randint(0, p - 1) for _ in range(500)]
    # Square
    x_sqr = [pow(xi, 2, p) for xi in x]

    actual = [sqrt_mod(yi, p) for yi in x_sqr]
    actual_sqr = [pow(xi, 2, p) for xi in actual]

    assert actual_sqr == x_sqr
