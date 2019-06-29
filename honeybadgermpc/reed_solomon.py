from honeybadgermpc.ntl import vandermonde_batch_evaluate, vandermonde_batch_interpolate
from honeybadgermpc.ntl import gao_interpolate
from honeybadgermpc.ntl import (
    fft,
    fft_interpolate,
    fft_batch_interpolate,
    fft_batch_evaluate,
    SetNumThreads,
    AvailableNTLThreads,
)
from honeybadgermpc.reed_solomon_wb import make_wb_encoder_decoder
from honeybadgermpc.exceptions import HoneyBadgerMPCError
import logging
import psutil
from abc import ABC, abstractmethod


class Encoder(ABC):
    """
    Generate encoding for given data
    """

    def encode(self, data):
        if type(data[0]) in [list, tuple]:
            return self.encode_batch(data)
        return self.encode_one(data)

    @abstractmethod
    def encode_one(self, data):
        """
        :type data: list of integers
        :return: Encoded value
        """
        raise NotImplementedError

    @abstractmethod
    def encode_batch(self, data):
        """
        :type data: list of list of integers
        :return: Encoded values
        """
        raise NotImplementedError


class Decoder(ABC):
    """
    Recover data from encoded values
    """

    def decode(self, z, encoded):
        if type(encoded[0]) in [list, tuple]:
            return self.decode_batch(z, encoded)
        return self.decode_one(z, encoded)

    @abstractmethod
    def decode_one(self, z, encoded):
        """
        :type z: list of integers
        :type encoded: list of integers
        :return: Decoded values or None
        """
        raise NotImplementedError

    @abstractmethod
    def decode_batch(self, z, encoded):
        """
        :type z: list of integers
        :type encoded: list of lists of integers
        :return:
        """
        raise NotImplementedError


class RobustDecoder(ABC):
    @abstractmethod
    def robust_decode(self, z, encoded):
        """
        :type z: list of integers
        :type encoded: list of integers
        :return: Decoded values or None, error locations
        """
        raise NotImplementedError


class VandermondeEncoder(Encoder):
    def __init__(self, point):
        self.n = point.n
        self.x = [point(i).value for i in range(self.n)]
        self.modulus = point.field.modulus

    def encode_one(self, data):
        return vandermonde_batch_evaluate(self.x, [data], self.modulus)[0]

    def encode_batch(self, data):
        return vandermonde_batch_evaluate(self.x, data, self.modulus)


class FFTEncoder(Encoder):
    def __init__(self, point):
        assert point.use_omega_powers is True, (
            "FFTEncoder only usable with roots of unity " "evaluation points"
        )

        self.order = point.order
        self.omega = point.omega.value
        self.modulus = point.field.modulus
        self.n = point.n

    def encode_one(self, data):
        return fft(data, self.omega, self.modulus, self.order)[: self.n]

    def encode_batch(self, data):
        return fft_batch_evaluate(data, self.omega, self.modulus, self.order, self.n)


class VandermondeDecoder(Decoder):
    def __init__(self, point):
        self.n = point.n
        self.modulus = point.field.modulus
        self.point = point

    def decode_one(self, z, encoded):
        x = [self.point(zi).value for zi in z]
        return vandermonde_batch_interpolate(x, [encoded], self.modulus)[0]

    def decode_batch(self, z, encoded):
        x = [self.point(zi).value for zi in z]
        return vandermonde_batch_interpolate(x, encoded, self.modulus)


class FFTDecoder(Decoder):
    def __init__(self, point):
        assert point.use_omega_powers is True, (
            "FFTEncoder only usable with roots of unity " "evaluation points"
        )
        self.order = point.order
        self.omega = point.omega.value
        self.modulus = point.field.modulus
        self.n = point.n

    def decode_one(self, z, encoded):
        return fft_interpolate(z, encoded, self.omega, self.modulus, self.order)

    def decode_batch(self, z, encoded):
        return fft_batch_interpolate(z, encoded, self.omega, self.modulus, self.order)


class GaoRobustDecoder(RobustDecoder):
    def __init__(self, d, point):
        self.d = d
        self.point = point
        self.modulus = point.field.modulus
        self.use_omega_powers = point.use_omega_powers

    # TODO: refactor this using `OptimalEncoder`
    #       see: https://github.com/initc3/HoneyBadgerMPC/pull/268
    def robust_decode(self, z, encoded):
        x = [self.point(zi).value for zi in z]

        args = [x, encoded, self.d + 1, self.modulus]
        if self.use_omega_powers:
            args += [z, self.point.omega.value, self.point.order]

        decoded, error_poly = gao_interpolate(
            *args, use_omega_powers=self.use_omega_powers
        )

        if decoded is None:
            return None, None

        errors = []
        if len(error_poly) > 1:
            if self.use_omega_powers:
                err_eval = fft(
                    error_poly, self.point.omega.value, self.modulus, self.point.order
                )[: self.point.n]
            else:
                x = [self.point(i).value for i in range(self.point.n)]
                err_eval = vandermonde_batch_evaluate(x, [error_poly], self.modulus)[0]

            errors = [i for i in range(self.point.n) if err_eval[i] == 0]

        return decoded, errors


class WelchBerlekampRobustDecoder(RobustDecoder):
    def __init__(self, d, point):
        self.n = point.n
        self.d = d
        self.modulus = point.field.modulus
        self.point = point
        _, dec, _ = make_wb_encoder_decoder(
            self.n, self.d + 1, self.modulus, self.point
        )
        self._dec = dec

    def robust_decode(self, z, encoded):
        m = {zi: i for i, zi in enumerate(z)}
        enc_extended = [
            self.point.field(encoded[m[i]]) if i in m else None for i in range(self.n)
        ]
        try:
            coeffs = self._dec(enc_extended)
        except Exception as e:
            # Welch-Berlekamp doesn't throw any specific exceptions.
            # Just catch 'em all
            if str(e) not in ("Wrong degree", "found no divisors!"):
                raise e
            coeffs = None

        if coeffs is not None:
            coeffs = [c.value for c in coeffs]
            x = [self.point(i).value for i in range(self.point.n)]
            poly_eval = vandermonde_batch_evaluate(x, [coeffs], self.modulus)[0]
            errors = [
                i
                for i in range(self.point.n)
                if enc_extended[i] is not None and enc_extended[i].value != poly_eval[i]
            ]

            return coeffs, errors
        return None, None


class DecodeValidationError(HoneyBadgerMPCError):
    pass


class IncrementalDecoder(object):
    """
    Incremental decoder helps process new data incrementally and aims to make the
    case where no error is present extremely fast.

    1) Validate that the data is indeed correct.
    2) If at least d + 1 points are available (where d is the degree of the polynomial
    we wish to reconstruct), then we can use a non-robust decoder
       (which is usually faster) to decode available data and arrive at our first guess
    3) As we get more data, validate it against the previous guess, if we find an
    error now, then our guess is probably wrong. We then use robust decoding to arrive
    at new guesses.
    4) We are done after at least (d + 1) + max_errors - confirmed_errors parties
    agree on every polynomial in the batch
    """

    def __init__(
        self,
        encoder,
        decoder,
        robust_decoder,
        degree,
        batch_size,
        max_errors,
        confirmed_errors=None,
        validator=None,
    ):
        self.encoder = encoder
        self.decoder = decoder
        self.robust_decoder = robust_decoder

        self.degree = degree
        self.batch_size = batch_size
        self.max_errors = max_errors
        self.validator = validator

        self._confirmed_errors = set()
        if confirmed_errors is not None:
            self._confirmed_errors = confirmed_errors
        self._available_points = set()
        self._z = []
        self._available_data = [[] for _ in range(batch_size)]
        self._result = None

        # State specifically for optimistic run
        self._guess_decoded = None
        self._guess_encoded = None
        self._optimistic = True

        # State for robust runs
        self._num_decoded = 0
        self._partial_result = []

        # Final results
        self._result = None

    def _validate(self, data):
        # Ideally, any validation error should just be added to the set
        # of confirmed errors
        if len(data) != self.batch_size:
            raise DecodeValidationError("Incorrect length of data")

        if data is None:
            return False

        if self.validator is not None:
            for d in data:
                self.validator(d)
        return True

    def _min_points_required(self):
        return self.degree + 1 + self.max_errors - len(self._confirmed_errors)

    def _optimistic_update(self, idx, data):
        """Try to optimistically decode or check if guess is right"""
        success = True
        if len(self._available_points) == self.degree + 1:
            # Optimistic decode
            self._guess_decoded = self.decoder.decode_batch(
                self._z, self._available_data
            )
            self._guess_encoded = self.encoder.encode_batch(self._guess_decoded)
        else:
            # We have a guess. It might be right. Check now
            for i in range(self.batch_size):
                if data[i] != self._guess_encoded[i][idx]:
                    success = False
                    break

            if success is False:
                # Guess was incorrect
                logging.critical("Optimistic decoding failed")
                self._guess_decoded = None
                self._guess_encoded = None
                self._optimistic = False

        if success and len(self._available_points) >= self._min_points_required():
            # Decoding successful
            self._result = self._guess_decoded

        return success

    def _robust_update(self):
        while self._num_decoded < self.batch_size:
            decoded, errors = self.robust_decoder.robust_decode(
                self._z, self._available_data[0]
            )

            # Need to wait for more data
            if decoded is None:
                break

            num_agreement = len(self._available_points) - len(errors)
            if num_agreement < self._min_points_required():
                break

            self._num_decoded += 1
            self._available_data = self._available_data[1:]
            self._partial_result.append(decoded)

            # Errors detected considered to be confirmed errors
            self._confirmed_errors |= set(errors)
            self._available_points -= set(errors)

            for e in errors:
                error_idx = self._z.index(e)

                del self._z[error_idx]
                for i in range(len(self._available_data)):
                    del self._available_data[i][error_idx]

        # We're done
        if self._num_decoded == self.batch_size:
            self._result = self._partial_result

    # Public API
    def add(self, idx, data):
        if self.done():
            return
        elif idx in self._available_points or idx in self._confirmed_errors:
            return

        if not self._validate(data):
            logging.error("Validation failed for data from %d: %s", idx, str(data))
            raise DecodeValidationError("Custom validation failed for %s" % str(data))

        # Update data
        self._available_points.add(idx)
        self._z.append(idx)

        for i in range(self._num_decoded, self.batch_size):
            self._available_data[i - self._num_decoded].append(data[i])

        # Nothing to do
        if len(self._available_points) <= self.degree:
            return

        # I'm still optimistic. Let's guess or validate guess
        if self._optimistic and self._optimistic_update(idx, data):
            return

        # When optimism fails me
        if len(self._available_points) >= self._min_points_required():
            self._robust_update()

    def done(self):
        return self._result is not None

    def get_results(self):
        if self._result is not None:
            return self._result, self._confirmed_errors
        return None, None


class EncoderSelector(object):
    # If n is lesser than this value, always pick Vandermonde
    LOW_VAN_THRESHOLD = 8
    # If n is greater than this value, always pick FFT
    HIGH_VAN_THRESHOLD = 128

    @staticmethod
    def set_optimal_thread_count(k):
        SetNumThreads(min(k, psutil.cpu_count(logical=False)))

    @staticmethod
    def select(point, k):
        assert point.use_omega_powers is True
        n = point.n
        if n < EncoderSelector.LOW_VAN_THRESHOLD:
            return VandermondeEncoder(point)
        if n >= EncoderSelector.HIGH_VAN_THRESHOLD:
            return FFTEncoder(point)

        # Check if n is close to the nearest power of 2
        # In the worst case, n would be just one above a power of 2. For example, 65
        # The nearest power of 2 greater than this is 128
        # 128 - 65 = 63 > 128 / 4 = 32. This is bad.
        # So we will use vandermonde here.
        npow2 = n if n & (n - 1) == 0 else 2 ** n.bit_length()
        if npow2 - n > npow2 // 4 and n < 128:
            return VandermondeEncoder(point)
        else:
            return FFTEncoder(point)


class DecoderSelector(object):
    # If n is lesser than this value, always pick Vandermonde
    LOW_VAN_THRESHOLD = 8
    # If batch size is greater than BATCH_SIZE_THRESH_SLOPE * n * self.cores, then
    # pick Vandermonde
    BATCH_SIZE_THRESH_SLOPE = 0.5

    @staticmethod
    def set_optimal_thread_count(k):
        SetNumThreads(min(k, psutil.cpu_count(logical=False)))

    @staticmethod
    def select(point, k):
        assert point.use_omega_powers is True
        n = point.n
        if n < DecoderSelector.LOW_VAN_THRESHOLD:
            return VandermondeDecoder(point)

        nt = AvailableNTLThreads()
        if k > DecoderSelector.BATCH_SIZE_THRESH_SLOPE * n * nt:
            return VandermondeDecoder(point)
        else:
            return FFTDecoder(point)


class OptimalEncoder(Encoder):
    """A wrapper for EncoderSelector which can directly be used in EncoderFactory"""

    def __init__(self, point):
        assert point.use_omega_powers is True
        self.point = point

    def encode_one(self, data):
        EncoderSelector.set_optimal_thread_count(1)
        return EncoderSelector.select(self.point, 1).encode_one(data)

    def encode_batch(self, data):
        EncoderSelector.set_optimal_thread_count(len(data))
        return EncoderSelector.select(self.point, len(data)).encode_batch(data)


class OptimalDecoder(Decoder):
    """A wrapper for DecoderSelector which can directly be used in DecoderFactory"""

    def __init__(self, point):
        assert point.use_omega_powers is True
        self.point = point

    def decode_one(self, z, data):
        DecoderSelector.set_optimal_thread_count(1)
        return DecoderSelector.select(self.point, 1).decode_one(z, data)

    def decode_batch(self, z, data):
        DecoderSelector.set_optimal_thread_count(len(data))
        return DecoderSelector.select(self.point, len(data)).decode_batch(z, data)


class Algorithm:
    VANDERMONDE = "vandermonde"
    FFT = "fft"
    GAO = "gao"
    WELCH_BERLEKAMP = "welch-berlekamp"


class EncoderFactory:
    @staticmethod
    def get(point, algorithm=None):
        if algorithm == Algorithm.VANDERMONDE:
            return VandermondeEncoder(point)
        elif algorithm == Algorithm.FFT:
            return FFTEncoder(point)
        elif algorithm is None:
            if point.use_omega_powers:
                return OptimalEncoder(point)
            else:
                return VandermondeEncoder(point)

        raise ValueError(
            f"Incorrect algorithm. "
            f"Supported algorithms are "
            f"{[Algorithm.VANDERMONDE, Algorithm.FFT]}\n"
            f"Pass algorithm=None with FFT Enabled for automatic "
            f"selection of encoder"
        )


class DecoderFactory:
    @staticmethod
    def get(point, algorithm=None):
        if algorithm == Algorithm.VANDERMONDE:
            return VandermondeDecoder(point)
        elif algorithm == Algorithm.FFT:
            return FFTDecoder(point)
        elif algorithm is None:
            if point.use_omega_powers:
                return OptimalDecoder(point)
            else:
                return VandermondeDecoder(point)

        raise ValueError(
            f"Incorrect algorithm. "
            f"Supported algorithms are "
            f"{[Algorithm.VANDERMONDE, Algorithm.FFT]}\n"
            f"Pass algorithm=None with FFT Enabled for automatic "
            f"selection of decoder"
        )


class RobustDecoderFactory:
    @staticmethod
    def get(t, point, algorithm=Algorithm.GAO):
        if algorithm == Algorithm.GAO:
            return GaoRobustDecoder(t, point)
        elif algorithm == Algorithm.WELCH_BERLEKAMP:
            return WelchBerlekampRobustDecoder(t, point)

        raise ValueError(
            f"Invalid algorithm. "
            f"Supported algorithms are "
            f"[{Algorithm.GAO},"
            f" {Algorithm.WELCH_BERLEKAMP}]"
        )
