import pytest
from honeybadgermpc.reed_solomon import VandermondeEncoder, FFTEncoder, \
    VandermondeDecoder, FFTDecoder, GaoRobustDecoder, WelchBerlekampRobustDecoder
from honeybadgermpc.polynomial import EvalPoint


@pytest.fixture
def encoding_test_cases(galois_field):
    test_cases = [
        [[1, 2], [3, 5, 7, 9], EvalPoint(galois_field, 4)],
        [[[1, 2], [2, 3]],
         [[3, 5, 7, 9], [5, 8, 11, 14]],
         EvalPoint(galois_field, 4)]
    ]
    return test_cases


@pytest.fixture
def fft_encoding_test_cases(galois_field):
    point = EvalPoint(galois_field, 4, use_fft=True)
    omega = point.omega.value
    p = point.field.modulus
    test_cases = []
    test_cases.append([
        [1, 2],
        [(2 * pow(omega, 0, p) + 1) % p, (2 * pow(omega, 1, p) + 1) % p,
         (2 * pow(omega, 2, p) + 1) % p, (2 * pow(omega, 3, p) + 1) % p],
        point
    ])
    return test_cases


@pytest.fixture
def decoding_test_cases(galois_field):
    test_cases = [
        [[1, 3], [5, 9], [1, 2], EvalPoint(galois_field, 4)],
        [[1, 3], [[5, 9], [8, 14]],
         [[1, 2], [2, 3]], EvalPoint(galois_field, 4)]
    ]
    return test_cases


@pytest.fixture
def fft_decoding_test_cases(galois_field):
    point = EvalPoint(galois_field, 4, use_fft=True)
    omega = point.omega.value
    p = galois_field.modulus
    test_cases = []
    test_cases.append([
        [1, 3],
        [(2 * pow(omega, 1, p) + 1) % p, (2 * pow(omega, 3, p) + 1) % p],
        [1, 2],
        point
    ])
    return test_cases


@pytest.fixture
def robust_decoding_test_cases(galois_field):
    omega = EvalPoint(galois_field, 4, use_fft=True).omega.value
    p = galois_field.modulus
    # Order: Index of parties, Encoded values, Expected decoded values,
    # Expected erroneous parties, t, point
    test_cases = [
        # Correct array would be [3, 5, 7, 9]
        [[0, 1, 2, 3], [3, 5, 0, 9],
         [1, 2], [2], 1, EvalPoint(galois_field, 4)],
        [[0, 1, 2, 3],
         [(2 * pow(omega, 0, p) + 1) % p, (2 * pow(omega, 1, p) + 1) % p,
          0, (2 * pow(omega, 3, p) + 1) % p],
         [1, 2], [2], 1, EvalPoint(galois_field, 4, use_fft=True)]
    ]

    return test_cases


def test_vandermonde_encode(encoding_test_cases):
    for test_case in encoding_test_cases:
        data, encoded, point = test_case
        enc = VandermondeEncoder(point)
        actual = enc.encode(data)
        assert actual == encoded


def test_fft_encode(fft_encoding_test_cases):
    for test_case in fft_encoding_test_cases:
        data, encoded, point = test_case
        enc = FFTEncoder(point)
        actual = enc.encode(data)
        assert actual == encoded


def test_vandermonde_decode(decoding_test_cases):
    for test_case in decoding_test_cases:
        z, encoded, decoded, point = test_case
        dec = VandermondeDecoder(point)
        actual = dec.decode(z, encoded)
        assert actual == decoded


def test_fft_decode(fft_decoding_test_cases):
    for test_case in fft_decoding_test_cases:
        z, encoded, decoded, point = test_case
        dec = FFTDecoder(point)
        actual = dec.decode(z, encoded)
        assert actual == decoded


def test_gao_robust_decode(robust_decoding_test_cases):
    for test_case in robust_decoding_test_cases:
        z, encoded, decoded, expected_errors, t, point = test_case
        dec = GaoRobustDecoder(t, point)
        actual, actual_errors = dec.robust_decode(z, encoded)
        assert actual == decoded
        assert actual_errors == expected_errors


def test_wb_robust_decode(robust_decoding_test_cases):
    for test_case in robust_decoding_test_cases:
        z, encoded, decoded, expected_errors, t, point = test_case
        dec = WelchBerlekampRobustDecoder(t, point)
        actual, actual_errors = dec.robust_decode(z, encoded)
        assert actual == decoded
        assert actual_errors == expected_errors
