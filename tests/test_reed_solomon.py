import pytest
from honeybadgermpc.reed_solomon import (
    VandermondeEncoder,
    FFTEncoder,
    VandermondeDecoder,
    FFTDecoder,
    GaoRobustDecoder,
    WelchBerlekampRobustDecoder,
)
from honeybadgermpc.polynomial import EvalPoint
from honeybadgermpc.reed_solomon import EncoderFactory, DecoderFactory
from honeybadgermpc.reed_solomon import EncoderSelector, DecoderSelector
from honeybadgermpc.ntl import AvailableNTLThreads
from unittest.mock import patch


@pytest.fixture
def encoding_test_cases(galois_field):
    test_cases = [
        [[1, 2], [3, 5, 7, 9], EvalPoint(galois_field, 4)],
        [[[1, 2], [2, 3]], [[3, 5, 7, 9], [5, 8, 11, 14]], EvalPoint(galois_field, 4)],
    ]
    return test_cases


@pytest.fixture
def fft_encoding_test_cases(galois_field):
    point = EvalPoint(galois_field, 4, use_omega_powers=True)
    omega = point.omega.value
    p = point.field.modulus
    test_cases = []
    test_cases.append(
        [
            [1, 2],
            [
                (2 * pow(omega, 0, p) + 1) % p,
                (2 * pow(omega, 1, p) + 1) % p,
                (2 * pow(omega, 2, p) + 1) % p,
                (2 * pow(omega, 3, p) + 1) % p,
            ],
            point,
        ]
    )
    return test_cases


@pytest.fixture
def decoding_test_cases(galois_field):
    test_cases = [
        [[1, 3], [5, 9], [1, 2], EvalPoint(galois_field, 4)],
        [[1, 3], [[5, 9], [8, 14]], [[1, 2], [2, 3]], EvalPoint(galois_field, 4)],
    ]
    return test_cases


@pytest.fixture
def fft_decoding_test_cases(galois_field):
    point = EvalPoint(galois_field, 4, use_omega_powers=True)
    omega = point.omega.value
    p = galois_field.modulus
    test_cases = []
    test_cases.append(
        [
            [1, 3],
            [(2 * pow(omega, 1, p) + 1) % p, (2 * pow(omega, 3, p) + 1) % p],
            [1, 2],
            point,
        ]
    )
    return test_cases


@pytest.fixture
def robust_decoding_test_cases(galois_field):
    omega = EvalPoint(galois_field, 4, use_omega_powers=True).omega.value
    p = galois_field.modulus
    # Order: Index of parties, Encoded values, Expected decoded values,
    # Expected erroneous parties, t, point
    test_cases = [
        # Correct array would be [3, 5, 7, 9]
        [[0, 1, 2, 3], [3, 5, 0, 9], [1, 2], [2], 1, EvalPoint(galois_field, 4)],
        [
            [0, 1, 2, 3],
            [
                (2 * pow(omega, 0, p) + 1) % p,
                (2 * pow(omega, 1, p) + 1) % p,
                0,
                (2 * pow(omega, 3, p) + 1) % p,
            ],
            [1, 2],
            [2],
            1,
            EvalPoint(galois_field, 4, use_omega_powers=True),
        ],
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


def test_auto_encode_fft_disabled(encoding_test_cases):
    # Just check if some encoder is being picked
    for test_case in encoding_test_cases:
        data, encoded, point = test_case
        enc = EncoderFactory.get(point)
        actual = enc.encode(data)
        assert actual == encoded


def test_auto_encode_fft_enabled(fft_encoding_test_cases):
    # Just check if some encoder is being picked
    for test_case in fft_encoding_test_cases:
        data, encoded, point = test_case
        enc = EncoderFactory.get(point)
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


def test_auto_decode_fft_disabled(decoding_test_cases):
    for test_case in decoding_test_cases:
        z, encoded, decoded, point = test_case
        dec = DecoderFactory.get(point)
        actual = dec.decode(z, encoded)
        assert actual == decoded


def test_auto_decode_fft_enabled(fft_decoding_test_cases):
    for test_case in fft_decoding_test_cases:
        z, encoded, decoded, point = test_case
        dec = DecoderFactory.get(point)
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


def test_encoder_selection(galois_field):
    # Very small n < 8. Vandermonde should always be picked
    point = EvalPoint(galois_field, 4, use_omega_powers=True)
    assert isinstance(EncoderSelector.select(point, 1), VandermondeEncoder)
    assert isinstance(EncoderSelector.select(point, 100000), VandermondeEncoder)

    # Intermediate values of n (8 < n < 128
    # Bad n (Nearest power of 2 is much higher) Vandermonde should
    # always be picked
    point = EvalPoint(galois_field, 65, use_omega_powers=True)
    assert isinstance(EncoderSelector.select(point, 1), VandermondeEncoder)
    assert isinstance(EncoderSelector.select(point, 100000), VandermondeEncoder)

    point = EvalPoint(galois_field, 40, use_omega_powers=True)
    assert isinstance(EncoderSelector.select(point, 1), VandermondeEncoder)
    assert isinstance(EncoderSelector.select(point, 100000), VandermondeEncoder)

    # Good n (Nearest power of 2 is close) FFT should be picked
    point = EvalPoint(galois_field, 120, use_omega_powers=True)
    assert isinstance(EncoderSelector.select(point, 1), FFTEncoder)
    assert isinstance(EncoderSelector.select(point, 100000), FFTEncoder)

    point = EvalPoint(galois_field, 55, use_omega_powers=True)
    assert isinstance(EncoderSelector.select(point, 1), FFTEncoder)
    assert isinstance(EncoderSelector.select(point, 100000), FFTEncoder)

    # Large n. Always pick FFT
    point = EvalPoint(galois_field, 255, use_omega_powers=True)
    assert isinstance(EncoderSelector.select(point, 1), FFTEncoder)
    assert isinstance(EncoderSelector.select(point, 100000), FFTEncoder)

    point = EvalPoint(galois_field, 257, use_omega_powers=True)
    assert isinstance(EncoderSelector.select(point, 1), FFTEncoder)
    assert isinstance(EncoderSelector.select(point, 100000), FFTEncoder)


@patch("psutil.cpu_count")
def test_decoder_selection(mocked_cpu_count, galois_field):
    # Very small n < 8. Vandermonde should always be picked
    point = EvalPoint(galois_field, 4, use_omega_powers=True)
    for cpu_count in [1, 100]:
        mocked_cpu_count.return_value = cpu_count
        for batch_size in [1, 1000, 100000]:
            DecoderSelector.set_optimal_thread_count(batch_size)
            assert isinstance(
                DecoderSelector.select(point, batch_size), VandermondeDecoder
            )

    # Small batches (~n). Reasonable number of threads. Pick FFT
    point = EvalPoint(galois_field, 65, use_omega_powers=True)
    for cpu_count in [1, 2, 4, 8]:
        mocked_cpu_count.return_value = cpu_count
        for batch_size in [1, 16, 32]:
            DecoderSelector.set_optimal_thread_count(batch_size)
            assert isinstance(DecoderSelector.select(point, batch_size), FFTDecoder)

    # Small n. Reasonable number of threads,
    # Large batch sizes > ~ numthreads * n. Pick Vandermonde
    point = EvalPoint(galois_field, 65, use_omega_powers=True)
    for cpu_count in [1, 2, 4, 8]:
        mocked_cpu_count.return_value = cpu_count
        for batch_size in [512, 1024, 2048, 4096]:
            DecoderSelector.set_optimal_thread_count(batch_size)
            assert isinstance(
                DecoderSelector.select(point, batch_size), VandermondeDecoder
            )

    # Extremely large n. FFT should ideally be picked at reasonable batch sizes
    point = EvalPoint(galois_field, 65536, use_omega_powers=True)
    for cpu_count in [1, 2, 4, 8]:
        mocked_cpu_count.return_value = cpu_count
        for batch_size in [512, 1024, 2048, 4096, 8192]:
            DecoderSelector.set_optimal_thread_count(batch_size)
            assert isinstance(DecoderSelector.select(point, batch_size), FFTDecoder)

    # The scenarios above checked extreme cases. Below we check more rigorously based
    # on the exact approximation formula. Ideally, the cases above should not change
    # over time but the tests below will as the selection algorithm changes
    for n in [32, 64, 128, 256]:
        point = EvalPoint(galois_field, n, use_omega_powers=True)
        for cpu_count in [2 ** i for i in range(5)]:
            mocked_cpu_count.return_value = cpu_count
            for batch_size in [2 ** i for i in range(16)]:
                DecoderSelector.set_optimal_thread_count(batch_size)
                if batch_size > 0.5 * n * min(batch_size, AvailableNTLThreads()):
                    assert isinstance(
                        DecoderSelector.select(point, batch_size), VandermondeDecoder
                    )
                else:
                    assert isinstance(
                        DecoderSelector.select(point, batch_size), FFTDecoder
                    )
