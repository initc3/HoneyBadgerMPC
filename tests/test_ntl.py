from honeybadgermpc.ntl.helpers import interpolate, batch_vandermonde_interpolate, \
    batch_vandermonde_evaluate, fft, fft_interpolate, fft_batch_interpolate


def test_interpolate(galois_field):
    # Given
    x = [1, 2]
    y = [1, 2]
    p = galois_field.modulus

    # When
    poly = interpolate(x, y, p)

    # Then
    assert poly == [0, 1]


def test_batch_vandermonde_interpolate(galois_field):
    # Given
    x = [1, 2]
    y = [[1, 2], [3, 5]]
    p = galois_field.modulus

    # When
    polynomials = batch_vandermonde_interpolate(x, y, p)

    # Then
    assert polynomials == [[0, 1], [1, 2]]


def test_batch_vandermonde_evaluate(galois_field):
    # Given
    x = [1, 2]
    polynomials = [[0, 1], [1, 2]]
    p = galois_field.modulus

    # When
    y = batch_vandermonde_evaluate(x, polynomials, p)

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
    ys = [sum(poly[i] * pow(x, i, p) for i in range(len(poly))) % p
          for x in xs]
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
    polys = [[1, 2, 0],
             [3, 2, 1],
             [3, 4, 2]]
    ys = [[sum(poly[i] * pow(x, i, p) for i in range(len(poly))) % p
           for x in xs] for poly in polys]
    p = galois_field.modulus

    # When
    interp_polys = fft_batch_interpolate(zs, ys, omega, p, n)

    # Then
    assert interp_polys == polys
