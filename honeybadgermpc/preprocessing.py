import logging
import asyncio
import re
import os
from os import makedirs, listdir
from os.path import isfile, join
from uuid import uuid4
from random import randint
from collections import defaultdict
from itertools import chain
from enum import Enum
from abc import ABC, abstractmethod
from shutil import rmtree

from .field import GF
from .polynomial import polynomials_over
from .ntl import vandermonde_batch_evaluate
from .elliptic_curve import Subgroup


class PreProcessingConstants(Enum):
    SHARED_DATA_DIR = "sharedata/"
    READY_FILE_NAME = f"{SHARED_DATA_DIR}READY"
    TRIPLES = "triples"
    CUBES = "cubes"
    ZEROS = "zeros"
    RANDS = "rands"
    BITS = "bits"
    POWERS = "powers"
    SHARES = "share"
    ONE_MINUS_ONE = "one_minus_one"
    DOUBLE_SHARES = "double_shares"
    SHARE_BITS = "share_bits"

    def __str__(self):
        return self.value


class PreProcessingMixin(ABC):
    """ Abstract base class of preprocessing mixins.
    The interface exposed is composed of a few parts:
    - metadata:
        - _preprocessing_stride dictates how many values are needed per element
          when retrieving preprocessing
        - preprocessing_name dictates the type of preprocessing-- e.g. "rands",
          "triples", etc.
            - file_prefix uses this to determine the filename to store preprocessed
              values in.
        - min_count returns the minimal amount of preprocessing remaining for a
          given n, t combination.
    - generation:
        - generate_values is the public interface to generate preprocessing values from
          the mixin
        - _generate_polys is the private interface for doing the same thing, which is
          what is overridden by subclasses.
    - retrieval:
        - get_value is the public interface to retrieve a value from preprocessing
        - _get_value is the private interface for doing the same thing, which is what is
          overridden by subclasses
    """

    def __init__(self, field, poly, data_dir):
        self.field = field
        self.poly = poly
        self.cache = defaultdict(chain)
        self.count = defaultdict(int)
        self.data_dir = data_dir
        self._refresh_cache()

    @property
    def file_prefix(self):
        """ Beginning prefix of filenames storing preprocessing values for this mixin
        """
        return f"{self.data_dir}{self.preprocessing_name}"

    def min_count(self, n, t):
        """ Returns the minimum number of preprocessing stored in the cache across all
        of the keys with the given n, t values.
        """
        counts = []
        for (id_, n_, t_) in self.count:
            if (n_, t_) == (n, t):
                counts.append(self.count[id_, n_, t_])

        if len(counts) == 0:
            return 0

        return min(counts) // self._preprocessing_stride

    def get_value(self, context, *args, **kwargs):
        """ Given an MPC context, retrieve one preprocessing value.

        args:
            context: MPC context to use when fetching the value

        outputs:
            Preprocessing value for this mixin
        """
        key = (context.myid, context.N, context.t)

        to_return, used = self._get_value(context, key, *args, **kwargs)
        self.count[key] -= used

        return to_return

    def _read_preprocessing_file(self, file_name):
        """ Given the filename of the preprocessing file to read, fetch all of the
        values stored in the preprocessing file.
        """
        with open(file_name, "r") as f:
            lines = f.read().splitlines()
            values = list(map(int, lines))
            assert len(values) >= 3

            modulus = values[0]
            assert modulus == self.field.modulus, (
                f"Expected file "
                f"to have modulus {self.field.modulus}, but found {modulus}"
            )

            # The second and third lines of the file contain the degree and context id
            # correspondingly.
            return values[3:]

    def _write_preprocessing_file(
        self, file_name, degree, context_id, values, append=False
    ):
        """ Write the values to the preprocessing file given by the filename.
        When append is true, this will append to an existing file, otherwise, it will
        overwrite.
        """
        if not os.path.isfile(file_name):
            append = False

        if append:
            with open(file_name, "r") as f:
                meta = tuple(int(f.readline()) for _ in range(3))
                expected_meta = (self.field.modulus, degree, context_id)
                assert meta == expected_meta, (
                    f"File {file_name} "
                    f"expected to have metadata {expected_meta}, but had {meta}"
                )

            f = open(file_name, "a")
        else:
            f = open(file_name, "w")
            print(self.field.modulus, degree, context_id, file=f, sep="\n")

        print(*values, file=f, sep="\n")
        f.close()

    def build_filename(self, n, t, context_id, prefix=None):
        """ Given a file prefix, and metadata, return the filename to put
        the shares in.

        args:
            n: Value of n used in preprocessing
            t: Value of t used in preprocessing
            context_id: myid of the mpc context we're preprocessing for.
            prefix: filename prefix, e.g. "sharedata/triples".
                Defaults to self.file_prefix

        output:
            Filename to use
        """
        if prefix is None:
            prefix = self.file_prefix

        return f"{prefix}_{n}_{t}-{context_id}.share"

    def _parse_file_name(self, file_name):
        """ Given a potential filename, return (n, t, context_id) of the
        file if it's a valid file, otherwise, return None
        """
        if not file_name.startswith(self.file_prefix):
            return None

        reg = re.compile(f"{self.file_prefix}_(\\d+)_(\\d+)-(\\d+).share")
        res = reg.search(file_name)
        if res is None:
            return None

        if len(res.groups()) != 3:
            return None

        return tuple(map(int, res.groups()))

    def _refresh_cache(self):
        """ Refreshes the cache by reading in sharedata files, and
        updating the cache values and count variables.
        """
        self.cache = defaultdict(chain)
        self.count = defaultdict(int)

        for f in listdir(self.data_dir):
            file_name = join(self.data_dir, f)
            if not isfile(file_name):
                continue

            groups = self._parse_file_name(file_name)
            if groups is None:
                continue

            (n, t, context_id) = groups
            key = (context_id, n, t)
            values = self._read_preprocessing_file(file_name)

            self.cache[key] = chain(values)
            self.count[key] = len(values)

    def _write_polys(self, n, t, polys, append=False, prefix=None):
        """ Given a file prefix, a list of polynomials, and associated n, t values,
        write the preprocessing for the share values represented by the polnomials.

        args:
            prefix: prefix to use when writing the file
            n: number of nodes this is preprocessing for
            t: number of faults tolerated by this preprocessing
            polys: polynomials corresponding to secret share values to write
            append: Whether or not to append shares to an existing file, or to overwrite.
        """
        polys = [[coeff.value for coeff in poly.coeffs] for poly in polys]
        all_values = vandermonde_batch_evaluate(
            list(range(1, n + 1)), polys, self.field.modulus
        )

        for i in range(n):
            values = [v[i] for v in all_values]
            file_name = self.build_filename(n, t, i, prefix=prefix)
            self._write_preprocessing_file(file_name, t, i, values, append=append)

            key = (i, n, t)
            if append:
                self.cache[key] = chain(self.cache[key], values)
                self.count[key] += len(values)
            else:
                self.cache[key] = chain(values)
                self.count[key] = len(values)

    def generate_values(self, k, n, t, *args, append=False, **kwargs):
        """ Given some n, t, generate k values and write them to disk.
        If append is true, this will add on to existing preprocessing. Otherwise,
        this will overwrite existing preprocessing.

        args:
            k: number of values to generate
            n: number of nodes to generate for
            t: number of faults that should be tolerated in generation
            append: set to true if this should append, or false to overwrite.
        """
        polys = self._generate_polys(k, n, t, *args, **kwargs)
        self._write_polys(n, t, polys, append=append)

    @property
    @staticmethod
    @abstractmethod
    def preprocessing_name():
        """ String representation of the type of preprocessing done by this mixin
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def _preprocessing_stride(self):
        """ Mixins should override this to return the number of values required from the
        preprocessing file in order to fetch one preprocessing element.
        """
        raise NotImplementedError

    @abstractmethod
    def _generate_polys(self, k, n, t):
        """ Private helper method to generate polynomials for use in preprocessing.

        args:
            k: number of elements to generate
            n: number of nodes to generate for
            t: number of faults that should be tolerated by preprocessing

        outputs: A list of polynomials corresponding to share values
        """
        raise NotImplementedError

    @abstractmethod
    def _get_value(self, context, key, *args, **kwargs):
        """ Private helper method to retrieve a value from the cache for
        this mixin.

        args:
            context: MPC context to retrieve the value for
            key: tuple of (n, t, i) used to index the cache

        outputs:
            Preprocessing value for this mixin
        """
        raise NotImplementedError


class ShareBitsPreProcessing(PreProcessingMixin):
    preprocessing_name = PreProcessingConstants.SHARE_BITS.value

    @property
    def _preprocessing_stride(self):
        return self.field.modulus.bit_length() + 1

    def _generate_polys(self, k, n, t):
        bit_length = self.field.modulus.bit_length()
        polys = []
        for _ in range(k):
            r = self.field.random()
            r_bits = [
                self.field(b)
                for b in map(int, reversed(f"{{0:0{bit_length}b}}".format(r.value)))
            ]

            polys.append(self.poly.random(t, r))
            polys += [self.poly.random(t, b) for b in r_bits]

        return polys

    def _get_value(self, context, key):
        bit_length = self.field.modulus.bit_length()
        assert self.count[key] >= 1

        share = context.Share(next(self.cache[key]))
        bits = [context.Share(next(self.cache[key])) for _ in range(bit_length)]
        return (share, bits), self._preprocessing_stride


class DoubleSharingPreProcessing(PreProcessingMixin):
    preprocessing_name = PreProcessingConstants.DOUBLE_SHARES.value
    _preprocessing_stride = 2

    def _generate_polys(self, k, n, t):
        polys = []
        for _ in range(k):
            r = self.field.random()
            polys.append(self.poly.random(t, r))
            polys.append(self.poly.random(2 * t, r))

        return polys

    def _get_value(self, context, key):
        assert self.count[key] >= 2
        r_t = context.Share(next(self.cache[key]))
        r_2t = context.Share(next(self.cache[key]), 2 * context.t)
        return (r_t, r_2t), self._preprocessing_stride


class PowersPreProcessing(PreProcessingMixin):
    preprocessing_name = PreProcessingConstants.POWERS.value
    _preprocessing_stride = 1

    def generate_values(self, k, n, t, z, append=False):
        polys_arr = self._generate_polys(k, n, t, z)
        for i, polys in enumerate(polys_arr):
            self._write_polys(
                n, t, polys, append=False, prefix=f"{self.file_prefix}_{i}"
            )

    def _generate_polys(self, k, n, t, z):
        b = self.field.random().value
        powers = [b]
        for _ in range(1, k):
            powers.append(powers[-1] * b)

        return [[self.poly.random(t, power) for power in powers] for _ in range(z)]

    def _get_value(self, context, key, pid):
        file_name = (
            f"{self.file_prefix}_{pid}_{context.N}_{context.t}-{context.myid}" f".share"
        )
        return list(map(context.Share, self._read_preprocessing_file(file_name))), 0

    def _refresh_cache(self):
        pass


class SharePreProcessing(PreProcessingMixin):
    preprocessing_name = PreProcessingConstants.SHARES.value
    _preprocessing_stride = 1

    def generate_values(self, k, n, t, x, append=False):
        sid = uuid4().hex
        polys = self._generate_polys(x, n, t)
        self._write_polys(n, t, polys, prefix=f"{self.file_prefix}_{sid}")
        return sid

    def _generate_polys(self, x, n, t):
        return [self.poly.random(t, x)]

    def _get_value(self, context, key, sid, t=None):
        if t is None:
            t = context.t
        file_name = self.build_filename(
            context.N, t, context.myid, prefix=f"{self.file_prefix}_{sid}"
        )
        values = self._read_preprocessing_file(file_name)
        return context.Share(values[0], t), 0

    def _refresh_cache(self):
        pass


class RandomPreProcessing(PreProcessingMixin):
    preprocessing_name = PreProcessingConstants.RANDS.value
    _preprocessing_stride = 1

    def _generate_polys(self, k, n, t):
        return [self.poly.random(t) for _ in range(k)]

    def _get_value(self, context, key, t=None):
        t = t if t is not None else context.t
        assert self.count[key] >= 1
        return context.Share(next(self.cache[key]), t), 1


class SimplePreProcessing(PreProcessingMixin):
    """ Subclass of PreProcessingMixin to be used in the trivial case
    where the only thing required to get a value is to read _preprocessing_stride
    values, turn them in to shares, and return a tuple of them.

    Subclasses of this class must only overwrite _generate_polys
    """

    def _get_value(self, context, key):
        assert self.count[key] >= self._preprocessing_stride, (
            f"Expected "
            f"{self._preprocessing_stride} elements of {self.preprocessing_name}, "
            f"but found only {self.count[key]}"
        )

        values = tuple(
            context.Share(next(self.cache[key]))
            for _ in range(self._preprocessing_stride)
        )

        if len(values) == 1:
            values = values[0]

        return values, self._preprocessing_stride


class CubePreProcessing(SimplePreProcessing):
    preprocessing_name = PreProcessingConstants.CUBES.value
    _preprocessing_stride = 3

    def _generate_polys(self, k, n, t):
        polys = []
        for _ in range(k):
            a = self.field.random()
            b = a * a
            c = a * b
            polys += [self.poly.random(t, v) for v in (a, b, c)]

        return polys


class TriplePreProcessing(SimplePreProcessing):
    preprocessing_name = PreProcessingConstants.TRIPLES.value
    _preprocessing_stride = 3

    def _generate_polys(self, k, n, t):
        polys = []
        for _ in range(k):
            a = self.field.random()
            b = self.field.random()
            c = a * b
            polys += [self.poly.random(t, v) for v in (a, b, c)]

        return polys


class ZeroPreProcessing(SimplePreProcessing):
    preprocessing_name = PreProcessingConstants.ZEROS.value
    _preprocessing_stride = 1

    def _generate_polys(self, k, n, t):
        return [self.poly.random(t, 0) for _ in range(k)]


class BitPreProcessing(SimplePreProcessing):
    preprocessing_name = PreProcessingConstants.BITS.value
    _preprocessing_stride = 1

    def _generate_polys(self, k, n, t):
        return [self.poly.random(t, randint(0, 1)) for _ in range(k)]


class SignedBitPreProcessing(SimplePreProcessing):
    preprocessing_name = PreProcessingConstants.ONE_MINUS_ONE.value
    _preprocessing_stride = 1

    def _generate_polys(self, k, n, t):
        return [self.poly.random(t, randint(0, 1) * 2 - 1) for _ in range(k)]


class PreProcessedElements:
    """ Main accessor of preprocessing
    This class is a singleton, that only has one object per field being
    preprocessed for.
    """

    DEFAULT_DIRECTORY = PreProcessingConstants.SHARED_DATA_DIR.value
    DEFAULT_FIELD = GF(Subgroup.BLS12_381)

    _cached_elements = {}

    def __new__(cls, append=True, data_directory=None, field=None):
        """ Called when a new PreProcessedElements is created.
        This creates a multiton based on the directory used in preprocessing
        """
        if data_directory is None:
            data_directory = cls.DEFAULT_DIRECTORY

        return PreProcessedElements._cached_elements.setdefault(
            data_directory, super(PreProcessedElements, cls).__new__(cls)
        )

    def __init__(self, append=True, data_directory=None, field=None):
        """
        args:
            field: GF to use when generating preprocessing
            append: whether or not we should append to existing preprocessing when
                generating, or if we should overwrite existing preprocessing.
            data_dir_name: directory name to write preprocessing to.
        """
        if data_directory is None:
            data_directory = PreProcessedElements.DEFAULT_DIRECTORY

        if field is None:
            field = PreProcessedElements.DEFAULT_FIELD

        self.field = field
        self.poly = polynomials_over(field)

        self.data_directory = data_directory
        self._init_data_dir()

        self._ready_file = (
            f"{self.data_directory}" f"{PreProcessingConstants.READY_FILE_NAME}"
        )

        self._append = append

        # Instantiate preprocessing mixins
        self._triples = TriplePreProcessing(self.field, self.poly, self.data_directory)
        self._cubes = CubePreProcessing(self.field, self.poly, self.data_directory)
        self._zeros = ZeroPreProcessing(self.field, self.poly, self.data_directory)
        self._rands = RandomPreProcessing(self.field, self.poly, self.data_directory)
        self._bits = BitPreProcessing(self.field, self.poly, self.data_directory)
        self._powers = PowersPreProcessing(self.field, self.poly, self.data_directory)
        self._shares = SharePreProcessing(self.field, self.poly, self.data_directory)
        self._one_minus_ones = SignedBitPreProcessing(
            self.field, self.poly, self.data_directory
        )
        self._double_shares = DoubleSharingPreProcessing(
            self.field, self.poly, self.data_directory
        )
        self._share_bits = ShareBitsPreProcessing(
            self.field, self.poly, self.data_directory
        )

    @classmethod
    def reset_cache(cls):
        """ Reset the class-wide cache of PreProcessedElements objects
        """
        cls._cached_elements = {}

    def _init_data_dir(self):
        """ Ensures that the data directory exists.
        """
        makedirs(self.data_directory, exist_ok=True)

    def clear_preprocessing(self):
        """ Delete all things from the preprocessing folder
        """
        rmtree(
            self.data_directory,
            onerror=lambda f, p, e: logging.debug(
                f"Error deleting data directory: {e}"
            ),
        )

        self._init_data_dir()

    async def wait_for_preprocessing(self, timeout=1):
        """ Block until the ready file is created
        """
        while not os.path.exists(self._ready_file):
            logging.info(f"waiting for preprocessing {self._ready_file}")
            await asyncio.sleep(timeout)

    def preprocessing_done(self):
        """ Create a ready file. This unblocks any calls to wait_for_preprocessing
        """
        os.mknod(self._ready_file)

    def _generate(self, mixin, k, n, t, *args, **kwargs):
        """ Generate k elements with given n, t values for the given kind of
        preprocessing.
        If we already have preprocessing for that kind, we only generate enough
        such that we have k elements cached.
        """
        if self._append:
            k -= mixin.min_count(n, t)

        if k > 0:
            return mixin.generate_values(k, n, t, *args, append=self._append, **kwargs)

    def generate_triples(self, k, n, t):
        return self._generate(self._triples, k, n, t)

    def generate_cubes(self, k, n, t):
        return self._generate(self._cubes, k, n, t)

    def generate_zeros(self, k, n, t):
        return self._generate(self._zeros, k, n, t)

    def generate_rands(self, k, n, t):
        return self._generate(self._rands, k, n, t)

    def generate_bits(self, k, n, t):
        return self._generate(self._bits, k, n, t)

    def generate_one_minus_ones(self, k, n, t):
        return self._generate(self._one_minus_ones, k, n, t)

    def generate_double_shares(self, k, n, t):
        return self._generate(self._double_shares, k, n, t)

    def generate_share_bits(self, k, n, t):
        return self._generate(self._share_bits, k, n, t)

    def generate_powers(self, k, n, t, z):
        return self._generate(self._powers, k, n, t, z)

    def generate_share(self, n, t, *args, **kwargs):
        return self._generate(self._shares, 1, n, t, *args, **kwargs)

    ## Preprocessing retrieval methods:

    def get_triples(self, context):
        return self._triples.get_value(context)

    def get_cubes(self, context):
        return self._cubes.get_value(context)

    def get_zero(self, context):
        return self._zeros.get_value(context)

    def get_rand(self, context, t=None):
        return self._rands.get_value(context, t)

    def get_bit(self, context):
        return self._bits.get_value(context)

    def get_powers(self, context, z):
        return self._powers.get_value(context, z)

    def get_share(self, context, sid, t=None):
        return self._shares.get_value(context, sid, t)

    def get_one_minus_ones(self, context):
        return self._one_minus_ones.get_value(context)

    def get_double_shares(self, context):
        return self._double_shares.get_value(context)

    def get_share_bits(self, context):
        return self._share_bits.get_value(context)
