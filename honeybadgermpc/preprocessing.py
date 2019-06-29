import logging
import asyncio
import os
from uuid import uuid4
from random import randint
from os import makedirs
from .field import GF
from .polynomial import polynomials_over
from .ntl import vandermonde_batch_evaluate
from .elliptic_curve import Subgroup


class PreProcessingConstants(object):
    SHARED_DATA_DIR = "sharedata/"
    TRIPLES_FILE_NAME_PREFIX = f"{SHARED_DATA_DIR}triples"
    CUBES_FILE_NAME_PREFIX = f"{SHARED_DATA_DIR}cubes"
    ZEROS_FILE_NAME_PREFIX = f"{SHARED_DATA_DIR}zeros"
    RANDS_FILE_NAME_PREFIX = f"{SHARED_DATA_DIR}rands"
    BITS_FILE_NAME_PREFIX = f"{SHARED_DATA_DIR}bits"
    POWERS_FILE_NAME_PREFIX = f"{SHARED_DATA_DIR}powers"
    SHARES_FILE_NAME_PREFIX = f"{SHARED_DATA_DIR}specific_share"
    ONE_MINUS_ONE_FILE_NAME_PREFIX = f"{SHARED_DATA_DIR}one_minus_one"
    DOUBLE_SHARES_FILE_NAME_PREFIX = f"{SHARED_DATA_DIR}double_shares"
    READY_FILE_NAME = f"{SHARED_DATA_DIR}READY"
    SHARE_BITS_FILE_NAME_PREFIX = f"{SHARED_DATA_DIR}share_bits"


async def wait_for_preprocessing():
    while not os.path.exists(f"{PreProcessingConstants.SHARED_DATA_DIR}READY"):
        logging.info(
            f"waiting for preprocessing {PreProcessingConstants.READY_FILE_NAME}"
        )
        await asyncio.sleep(1)


def clear_preprocessing():
    import shutil

    try:
        shutil.rmtree(f"{PreProcessingConstants.SHARED_DATA_DIR}")
    except FileNotFoundError:
        pass  # not a problem


def preprocessing_done():
    os.mknod(PreProcessingConstants.READY_FILE_NAME)


class PreProcessedElements(object):
    def __init__(self):
        self.field = GF(Subgroup.BLS12_381)
        self.poly = polynomials_over(self.field)
        self._bit_length = self.field.modulus.bit_length()
        self._triples = {}
        self._cubes = {}
        self._zeros = {}
        self._rands = {}
        self._bits = {}
        self._share_bits = {}
        self._one_minus_one_rands = {}
        self._double_shares = {}

    def _read_share_values_from_file(self, file_name):
        with open(file_name, "r") as f:
            lines = iter(f)

            # first line: field modulus
            modulus = int(next(lines))
            assert self.field.modulus == modulus

            # skip 2nd and 3rd line - share degree and id
            next(lines), next(lines)

            # remaining lines: shared values
            return [int(line) for line in lines]

    def _read_share_bit_values_from_file(self, file_name):
        """ Given a file written using _write_share_bits_to_file, read the
        file and return a list of tuples of shares with a list of their bit-sharings.

        args:
            file_name (str): filename to read from

        output:
            Returns a list of tuples, where the first element of each tuple is
            the value of a share, and the second element is a list of values of
            the shares that compose the bitwise sharing of the share.
            Note: bits are given LSB first
        """
        values = self._read_share_values_from_file(file_name)
        assert len(values) % (self._bit_length + 1) == 0

        stride = self._bit_length + 1
        share_bits = [
            (values[i * stride], values[i * stride + 1 : (i + 1) * stride])
            for i in range(len(values) // stride)
        ]

        return share_bits

    def _write_shares_to_file(self, f, degree, myid, shares):
        """ Given a list of field elements representing shares,
        write their values to file f.

        args:
            f (file): file to write shares to
            degree (int): degree of polynomial used to generate shares
            myid (int): id the shares belong to
            shares (list): list of GFElements representing share values
        """
        content = f"{self.field.modulus}\n{degree}\n{myid}\n"
        for share in shares:
            content += f"{share.value}\n"

        f.write(content)

    def _create_sharedata_dir_if_not_exists(self):
        makedirs(PreProcessingConstants.SHARED_DATA_DIR, exist_ok=True)

    ##############################
    # MPC program access to shares
    ##############################

    def get_triple(self, ctx):
        key = (ctx.myid, ctx.N, ctx.t)
        if key not in self._triples:
            file_suffix = f"_{ctx.N}_{ctx.t}-{ctx.myid}.share"
            file_path = (
                f"{PreProcessingConstants.TRIPLES_FILE_NAME_PREFIX}{file_suffix}"
            )
            self._triples[key] = iter(self._read_share_values_from_file(file_path))
        try:
            a = ctx.Share(next(self._triples[key]))
            b = ctx.Share(next(self._triples[key]))
            ab = ctx.Share(next(self._triples[key]))
            return a, b, ab
        except StopIteration:
            print("STOP ITERATION TRIPLES")
            raise StopIteration(f"preprocess underrun: TRIPLES")

    def get_cube(self, ctx):
        key = (ctx.myid, ctx.N, ctx.t)
        if key not in self._cubes:
            file_suffix = f"_{ctx.N}_{ctx.t}-{ctx.myid}.share"
            file_path = f"{PreProcessingConstants.CUBES_FILE_NAME_PREFIX}{file_suffix}"
            self._cubes[key] = iter(self._read_share_values_from_file(file_path))
        a1 = ctx.Share(next(self._cubes[key]))
        a2 = ctx.Share(next(self._cubes[key]))
        a3 = ctx.Share(next(self._cubes[key]))
        return a1, a2, a3

    def get_zero(self, ctx):
        key = (ctx.myid, ctx.N, ctx.t)
        if key not in self._zeros:
            file_suffix = f"_{ctx.N}_{ctx.t}-{ctx.myid}.share"
            file_path = f"{PreProcessingConstants.ZEROS_FILE_NAME_PREFIX}{file_suffix}"
            self._zeros[key] = iter(self._read_share_values_from_file(file_path))
        return ctx.Share(next(self._zeros[key]))

    def get_rand(self, ctx, t=None):
        t = t if t is not None else ctx.t
        key = (ctx.myid, ctx.N, t)
        if key not in self._rands:
            file_suffix = f"_{ctx.N}_{t}-{ctx.myid}.share"
            file_path = f"{PreProcessingConstants.RANDS_FILE_NAME_PREFIX}{file_suffix}"
            self._rands[key] = iter(self._read_share_values_from_file(file_path))
        return ctx.Share(next(self._rands[key]), t)

    def get_bit(self, ctx):
        key = (ctx.myid, ctx.N, ctx.t)
        if key not in self._bits:
            file_suffix = f"_{ctx.N}_{ctx.t}-{ctx.myid}.share"
            file_path = f"{PreProcessingConstants.BITS_FILE_NAME_PREFIX}{file_suffix}"
            self._bits[key] = iter(self._read_share_values_from_file(file_path))
        return ctx.Share(next(self._bits[key]))

    def get_one_minus_one_rand(self, ctx):
        file_suffix = f"_{ctx.N}_{ctx.t}-{ctx.myid}.share"
        fpath = f"{PreProcessingConstants.ONE_MINUS_ONE_FILE_NAME_PREFIX}{file_suffix}"
        key = (ctx.myid, ctx.N, ctx.t)
        if key not in self._one_minus_one_rands:
            self._one_minus_one_rands[key] = iter(
                self._read_share_values_from_file(fpath)
            )
        try:
            return ctx.Share(next(self._one_minus_one_rands[key]))
        except StopIteration:
            print("STOP ITERATION ONE_MINUS_ONE")
            raise StopIteration(f"preprocess underrun: ONE_MINUS_ONE")

    def get_powers(self, ctx, pid):
        file_suffix = f"_{pid}_{ctx.N}_{ctx.t}-{ctx.myid}.share"
        return list(
            map(
                ctx.Share,
                self._read_share_values_from_file(
                    f"{PreProcessingConstants.POWERS_FILE_NAME_PREFIX}{file_suffix}"
                ),
            )
        )

    def get_share(self, ctx, sid, t=None):
        if t is None:
            t = ctx.t
        file_suffix = f"_{sid}_{ctx.N}_{t}-{ctx.myid}.share"
        share_values = self._read_share_values_from_file(
            f"{PreProcessingConstants.SHARES_FILE_NAME_PREFIX}{file_suffix}"
        )
        return ctx.Share(share_values[0], t)

    def get_double_share(self, ctx):
        key = (ctx.myid, ctx.N, ctx.t)
        if key not in self._double_shares:
            suffix = f"_{ctx.N}_{ctx.t}-{ctx.myid}.share"
            path = f"{PreProcessingConstants.DOUBLE_SHARES_FILE_NAME_PREFIX}{suffix}"
            self._double_shares[key] = iter(self._read_share_values_from_file(path))
        r_t = ctx.Share(next(self._double_shares[key]))
        r_2t = ctx.Share(next(self._double_shares[key]), 2 * ctx.t)
        return r_t, r_2t

    def get_share_bits(self, ctx):
        key = (ctx.myid, ctx.N, ctx.t)
        if key not in self._share_bits:
            suffix = f"_{ctx.N}_{ctx.t}-{ctx.myid}.share"
            path = f"{PreProcessingConstants.SHARE_BITS_FILE_NAME_PREFIX}{suffix}"
            self._share_bits[key] = iter(self._read_share_bit_values_from_file(path))

        share_val, bit_vals = next(self._share_bits[key])
        share = ctx.Share(share_val)
        bits = [ctx.Share(val) for val in bit_vals]

        return share, bits

    #########################
    # Store the Preprocessing
    #########################

    def write_shares(self, ctx, file_name_prefix, degree, shares):
        with open(
            "%s_%d_%d-%d.share" % (file_name_prefix, ctx.N, ctx.t, ctx.myid), "w"
        ) as f:
            self._write_shares_to_file(f, degree, ctx.myid, shares)

    def write_triples(self, ctx, triples):
        trips = []
        for a, b, ab in triples:
            trips += (a, b, ab)
        prefix = PreProcessingConstants.TRIPLES_FILE_NAME_PREFIX
        self.write_shares(ctx, prefix, ctx.t, trips)

    def write_one_minus_one(self, ctx, shares):
        prefix = PreProcessingConstants.ONE_MINUS_ONE_FILE_NAME_PREFIX
        self.write_shares(ctx, prefix, ctx.t, shares)

    ####################
    # Fake Preprocessing
    ####################
    """
    Only use generate_{preproctype} to create fake preprocessing,
    useful for local experiments for just the online phase.
    """

    def _write_polys(self, file_name_prefix, n, t, polys):
        polys = [[coeff.value for coeff in poly.coeffs] for poly in polys]
        all_shares = vandermonde_batch_evaluate(
            list(range(1, n + 1)), polys, self.field.modulus
        )
        for i in range(n):
            shares = [self.field(s[i]) for s in all_shares]
            # with open(f'{file_name_prefix}_{n}_{t}_{i}.share', 'w') as f:
            with open("%s_%d_%d-%d.share" % (file_name_prefix, n, t, i), "w") as f:
                self._write_shares_to_file(f, t, i, shares)

    def generate_triples(self, k, n, t):
        self._create_sharedata_dir_if_not_exists()
        polys = []
        for _ in range(k):
            a = self.field.random()
            b = self.field.random()
            c = a * b
            polys.append(self.poly.random(t, a))
            polys.append(self.poly.random(t, b))
            polys.append(self.poly.random(t, c))
        self._write_polys(PreProcessingConstants.TRIPLES_FILE_NAME_PREFIX, n, t, polys)

    def generate_cubes(self, k, n, t):
        self._create_sharedata_dir_if_not_exists()
        polys = []
        for _ in range(k):
            a1 = self.field.random()
            a2 = a1 * a1
            a3 = a1 * a2
            polys.append(self.poly.random(t, a1))
            polys.append(self.poly.random(t, a2))
            polys.append(self.poly.random(t, a3))
        self._write_polys(PreProcessingConstants.CUBES_FILE_NAME_PREFIX, n, t, polys)

    def generate_zeros(self, k, n, t):
        self._create_sharedata_dir_if_not_exists()
        polys = [self.poly.random(t, 0) for _ in range(k)]
        self._write_polys(PreProcessingConstants.ZEROS_FILE_NAME_PREFIX, n, t, polys)

    def generate_rands(self, k, n, t):
        self._create_sharedata_dir_if_not_exists()
        polys = [self.poly.random(t) for _ in range(k)]
        self._write_polys(PreProcessingConstants.RANDS_FILE_NAME_PREFIX, n, t, polys)

    def generate_bits(self, k, n, t):
        self._create_sharedata_dir_if_not_exists()
        polys = [self.poly.random(t, randint(0, 1)) for _ in range(k)]
        self._write_polys(PreProcessingConstants.BITS_FILE_NAME_PREFIX, n, t, polys)

    def generate_one_minus_one_rands(self, k, n, t):
        self._create_sharedata_dir_if_not_exists()
        polys = [self.poly.random(t, randint(0, 1) * 2 - 1) for _ in range(k)]
        self._write_polys(
            PreProcessingConstants.ONE_MINUS_ONE_FILE_NAME_PREFIX, n, t, polys
        )

    def generate_powers(self, k, n, t, z):
        self._create_sharedata_dir_if_not_exists()
        b = self.field.random().value

        # Since we need all powers, multiplication
        # is faster than using the pow() function.
        powers = [None] * k
        powers[0] = b
        for i in range(1, k):
            powers[i] = powers[i - 1] * b
        for i in range(z):
            polys = [self.poly.random(t, power) for power in powers]
            self._write_polys(
                f"{PreProcessingConstants.POWERS_FILE_NAME_PREFIX}_{i}", n, t, polys
            )

    def generate_double_shares(self, k, n, t):
        self._create_sharedata_dir_if_not_exists()
        polys = []
        for _ in range(k):
            r = self.field.random()
            polys.append(self.poly.random(t, r))
            polys.append(self.poly.random(2 * t, r))
        self._write_polys(
            PreProcessingConstants.DOUBLE_SHARES_FILE_NAME_PREFIX, n, t, polys
        )

    def generate_share(self, x, n, t):
        self._create_sharedata_dir_if_not_exists()
        sid = uuid4().hex
        polys = [self.poly.random(t, x)]
        self._write_polys(
            f"{PreProcessingConstants.SHARES_FILE_NAME_PREFIX}_{sid}", n, t, polys
        )
        return sid

    def generate_share_bits(self, k, n, t):
        """ Generates random shares, alongside their bitwise sharings.

        args:
            k (int): number of shares to generate
            n (int): number of parties to generate shares for
            t (int): degree of polynomial to use when generating shares
        """
        self._create_sharedata_dir_if_not_exists()
        polys = []
        for _ in range(k):
            r = self.field.random()
            r_bits = [
                self.field(b)
                for b in map(
                    int, reversed(f"{{0:0{self._bit_length}b}}".format(r.value))
                )
            ]

            polys.append(self.poly.random(t, r))
            for b in r_bits:
                polys.append(self.poly.random(t, b))

        self._write_polys(
            PreProcessingConstants.SHARE_BITS_FILE_NAME_PREFIX, n, t, polys
        )
