from honeybadgermpc.ntl.helpers import vandermonde_batch_evaluate, \
    vandermonde_batch_interpolate
from honeybadgermpc.ntl.helpers import gao_interpolate
from honeybadgermpc.ntl.helpers import fft, fft_interpolate, fft_batch_interpolate
from honeybadgermpc.wb_interpolate import make_wb_encoder_decoder
from honeybadgermpc.exceptions import HoneyBadgerMPCError
import logging


class Encoder(object):
    """
    Generate encoding for given data
    """

    def encode(self, data):
        if type(data[0]) in [list, tuple]:
            return self.encode_batch(data)
        return self.encode_one(data)

    def encode_one(self, data):
        """
        :type data: list of integers
        :return: Encoded value
        """
        raise NotImplementedError

    def encode_batch(self, data):
        """
        :type data: list of list of integers
        :return: Encoded values
        """
        raise NotImplementedError


class Decoder(object):
    """
    Recover data from encoded values
    """

    def decode(self, z, encoded):
        if type(encoded[0]) in [list, tuple]:
            return self.decode_batch(z, encoded)
        return self.decode_one(z, encoded)

    def decode_one(self, z, encoded):
        """
        :type z: list of integers
        :type encoded: list of integers
        :return: Decoded values or None
        """
        raise NotImplementedError

    def decode_batch(self, z, encoded):
        """
        :type z: list of integers
        :type encoded: list of lists of integers
        :return:
        """
        raise NotImplementedError


class RobustDecoder(object):
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
        assert point.use_fft is True, "FFTEncoder only usable with roots of unity " \
                                      "evaluation points"

        self.order = point.order
        self.omega = point.omega.value
        self.modulus = point.field.modulus
        self.n = point.n

    def encode_one(self, data):
        return fft(data, self.omega, self.modulus, self.order)[:self.n]

    def encode_batch(self, data):
        return [fft(d, self.omega, self.modulus, self.order)[:self.n]
                for d in data]


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
        assert point.use_fft is True, "FFTEncoder only usable with roots of unity " \
                                      "evaluation points"
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
        self.use_fft = point.use_fft

    def robust_decode(self, z, encoded):
        x = [self.point(zi).value for zi in z]

        if self.use_fft:
            decoded, error_poly = gao_interpolate(x, encoded, self.d + 1,
                                                  self.modulus, z,
                                                  self.point.omega.value,
                                                  self.point.order,
                                                  use_fft=True)

            if decoded is not None:
                errors = []
                if len(error_poly) > 1:
                    err_eval = fft(error_poly, self.point.omega.value,
                                   self.modulus, self.point.order)[:self.point.n]
                    errors = [i for i in range(self.point.n)
                              if err_eval[i] == 0]
                return decoded, errors
            return None, None
        else:
            decoded, error_poly = gao_interpolate(x, encoded, self.d + 1, self.modulus)

            if decoded is not None:
                errors = []
                if len(error_poly) > 1:
                    x = [self.point(i).value for i in range(self.point.n)]
                    err_eval = vandermonde_batch_evaluate(x, [error_poly],
                                                          self.modulus)[0]
                    errors = [i for i in range(self.point.n)
                              if err_eval[i] == 0]
                return decoded, errors
            return None, None


class WelchBerlekampRobustDecoder(RobustDecoder):
    def __init__(self, d, point):
        self.n = point.n
        self.d = d
        self.modulus = point.field.modulus
        self.point = point
        _, dec, _ = make_wb_encoder_decoder(self.n, self.d + 1, self.modulus, self.point)
        self._dec = dec

    def robust_decode(self, z, encoded):
        m = {zi: i for i, zi in enumerate(z)}
        enc_extended = [self.point.field(encoded[m[i]]) if i in m else None
                        for i in range(self.n)]
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
            poly_eval = vandermonde_batch_evaluate(x, [coeffs],
                                                   self.modulus)[0]
            errors = [i for i in range(self.point.n)
                      if enc_extended[i] is not None and
                      enc_extended[i].value != poly_eval[i]]

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

    def __init__(self, encoder, decoder, robust_decoder,
                 degree, batch_size, max_errors,
                 confirmed_errors=None, validator=None):
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
            self._guess_decoded = self.decoder.decode_batch(self._z,
                                                            self._available_data)
            self._guess_encoded = self.encoder.encode_batch(self._guess_decoded)
        else:
            # We have a guess. It might be right. Check now
            for i in range(self.batch_size):
                if data[i] != self._guess_encoded[i][idx]:
                    success = False
                    break

            if success is False:
                # Guess was incorrect
                self._guess_decoded = None
                self._guess_encoded = None
                self._optimistic = False

        if success and len(self._available_points) >= self._min_points_required():
            # Decoding successful
            self._result = self._guess_decoded

        return success

    def _robust_update(self):
        while self._num_decoded < self.batch_size:
            decoded, errors = self.robust_decoder.robust_decode(self._z,
                                                                self._available_data[0])

            # Need to wait for more data
            if decoded is None:
                break

            num_agreement = len(self._available_points) - len(errors)
            if num_agreement >= self._min_points_required():
                # Errors detected considered to be confirmed errors
                self._confirmed_errors |= set(errors)
                self._available_points -= set(errors)
                error_indices = []
                for e in errors:
                    error_idx = self._z.index(e)
                    error_indices.append(error_idx)
                    del self._z[error_idx]
                self._num_decoded += 1
                self._available_data = self._available_data[1:]
                self._partial_result.append(decoded)

                for error_idx in error_indices:
                    for i in range(len(self._available_data)):
                        del self._available_data[i][error_idx]
            else:
                break

        # We're done
        if self._num_decoded == self.batch_size:
            self._result = self._partial_result

    # Public API
    def add(self, idx, data):
        if self.done() or idx in self._available_points or \
                idx in self._confirmed_errors:
            return

        if self._validate(data) is False:
            logging.error("Logging failed for data from %d: %s", idx, str(data))
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


class Algorithm:
    VANDERMONDE = 'vandermonde'
    FFT = 'fft'
    GAO = 'gao'
    WELCH_BERLEKAMP = 'welch-berlekamp'


class EncoderFactory:
    @staticmethod
    def get(point, algorithm=Algorithm.VANDERMONDE):
        if algorithm == Algorithm.VANDERMONDE:
            return VandermondeEncoder(point)
        elif algorithm == Algorithm.FFT:
            return FFTEncoder(point)
        raise ValueError(f"Incorrect algorithm. "
                         f"Supported algorithms are "
                         f"{[Algorithm.VANDERMONDE, Algorithm.FFT]}")


class DecoderFactory:
    @staticmethod
    def get(point, algorithm=Algorithm.VANDERMONDE):
        if algorithm == Algorithm.VANDERMONDE:
            return VandermondeDecoder(point)
        elif algorithm == Algorithm.FFT:
            return FFTDecoder(point)
        raise ValueError(f"Incorrect algorithm. "
                         f"Supported algorithms are "
                         f"{[Algorithm.VANDERMONDE, Algorithm.FFT]}")


class RobustDecoderFactory:
    @staticmethod
    def get(t, point, algorithm=Algorithm.GAO):
        if algorithm == Algorithm.GAO:
            return GaoRobustDecoder(t, point)
        elif algorithm == Algorithm.WELCH_BERLEKAMP:
            return WelchBerlekampRobustDecoder(t, point)
        raise ValueError(f"Invalid algorithm. "
                         f"Supported algorithms are "
                         f"[{Algorithm.GAO},"
                         f" {Algorithm.WELCH_BERLEKAMP}]")
