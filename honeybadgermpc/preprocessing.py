import logging
import asyncio
import os
from uuid import uuid4
from random import randint, Random
from os import makedirs
from .field import GF
from .polynomial import polynomials_over, EvalPoint
from .ntl.helpers import vandermonde_batch_evaluate
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


class AWSPreProcessedElements(object):
    def __init__(self, n, t, my_id, seed, use_power_of_omega=True):
        logging.info("USING SEED: %d", seed)
        self.seed = seed
        self.t = t
        self.field = GF(Subgroup.BLS12_381)
        self.poly = polynomials_over(self.field)
        self.eval_point = EvalPoint(self.field, n, use_fft=use_power_of_omega)
        if use_power_of_omega:
            self.my_point = pow(self.eval_point.omega, my_id)
        else:
            self.my_point = my_id+1

    def horner(self, coefficients, x):
        acc = 0
        for c in reversed(coefficients):
            acc = acc * x + c
        return acc

    def _get_rand(self):
        while True:
            v = self.field.random(self.seed)
            self.seed += 1
            random_poly = self.poly.random(self.t, v, seed=self.seed)
            self.seed += self.t+1
            yield self.horner(random_poly.coeffs, self.my_point)

    def get_rand(self, k):
        rands = [next(self._get_rand()) for i in range(k)]
        return iter(rands)

    def _get_one_minus_one_rand(self):
        while True:
            v = Random(self.seed).randint(0, 1)*2 - 1
            self.seed += 1
            random_poly = self.poly.random(self.t, v, seed=self.seed)
            self.seed += self.t+1
            yield self.horner(random_poly.coeffs, self.my_point)

    def get_one_minus_one_rand(self, k):
        one_minus_one_rands = [next(self._get_one_minus_one_rand()) for i in range(k)]
        return iter(one_minus_one_rands)

    def _get_triple(self):
        while True:
            a = self.field(self.seed)
            self.seed += 1
            random_poly_a = self.poly.random(self.t, a, seed=self.seed)
            self.seed += self.t+1
            b = self.field(self.seed)
            self.seed += 1
            random_poly_b = self.poly.random(self.t, b, seed=self.seed)
            self.seed += self.t+1
            ab = a*b
            random_poly_ab = self.poly.random(self.t, ab, seed=self.seed)
            self.seed += self.t+1
            yield (self.horner(random_poly_a.coeffs, self.my_point),
                   self.horner(random_poly_b.coeffs, self.my_point),
                   self.horner(random_poly_ab.coeffs, self.my_point))

    def get_triple(self, k):
        triples = [next(self._get_triple()) for _ in range(k)]
        return iter(triples)

    def _get_powers(self, k):
        b = self.field.random(self.seed).value
        self.seed += 1
        powers = [None] * k
        powers[0] = b
        for i in range(1, k):
            powers[i] = powers[i-1] * b
        while True:
            shares = [None]*k
            for i in range(k):
                random_poly = self.poly.random(self.t, powers[i], seed=self.seed)
                self.seed += self.t + 1
                shares[i] = self.horner(random_poly.coeffs, self.my_point)
            yield shares

    def get_powers(self, k, z):
        powers = [next(self._get_powers(k)) for _ in range(z)]
        return iter(powers)


class PreProcessedElements(object):
    def __init__(self):
        self.field = GF(Subgroup.BLS12_381)
        self.poly = polynomials_over(self.field)
        self._triples = {}
        self._cubes = {}
        self._zeros = {}
        self._rands = {}
        self._bits = {}
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

    def _write_shares_to_file(self, f, degree, myid, shares):
        content = f"{self.field.modulus}\n{degree}\n{myid}\n"
        for share in shares:
            content += f"{share.value}\n"
        f.write(content)

    def _write_polys(self, file_name_prefix, n, t, polys):
        polys = [[coeff.value for coeff in poly.coeffs] for poly in polys]
        all_shares = vandermonde_batch_evaluate(
            list(range(1, n+1)), polys, self.field.modulus)
        for i in range(n):
            shares = [self.field(s[i]) for s in all_shares]
            with open('%s_%d_%d-%d.share' % (file_name_prefix, n, t, i), 'w') as f:
                self._write_shares_to_file(f, t, i, shares)

    def _create_sharedata_dir_if_not_exists(self):
        makedirs(PreProcessingConstants.SHARED_DATA_DIR, exist_ok=True)

    def generate_triples(self, k, n, t):
        self._create_sharedata_dir_if_not_exists()
        polys = []
        for _ in range(k):
            a = self.field.random()
            b = self.field.random()
            c = a*b
            polys.append(self.poly.random(t, a))
            polys.append(self.poly.random(t, b))
            polys.append(self.poly.random(t, c))
        self._write_polys(PreProcessingConstants.TRIPLES_FILE_NAME_PREFIX, n, t, polys)

    def generate_cubes(self, k, n, t):
        self._create_sharedata_dir_if_not_exists()
        polys = []
        for _ in range(k):
            a1 = self.field.random()
            a2 = a1*a1
            a3 = a1*a2
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
        polys = [self.poly.random(t, randint(0, 1)*2 - 1) for _ in range(k)]
        self._write_polys(
            PreProcessingConstants.ONE_MINUS_ONE_FILE_NAME_PREFIX, n, t, polys)

    def generate_powers(self, k, n, t, z):
        self._create_sharedata_dir_if_not_exists()
        b = self.field.random().value

        # Since we need all powers, multiplication
        # is faster than using the pow() function.
        powers = [None] * k
        powers[0] = b
        for i in range(1, k):
            powers[i] = powers[i-1] * b
        for i in range(z):
            polys = [self.poly.random(t, power) for power in powers]
            self._write_polys(
                f"{PreProcessingConstants.POWERS_FILE_NAME_PREFIX}_{i}", n, t, polys)

    def generate_double_shares(self, k, n, t):
        self._create_sharedata_dir_if_not_exists()
        polys = []
        for _ in range(k):
            r = self.field.random()
            polys.append(self.poly.random(t, r))
            polys.append(self.poly.random(2*t, r))
        self._write_polys(
            PreProcessingConstants.DOUBLE_SHARES_FILE_NAME_PREFIX, n, t, polys)

    def generate_share(self, x, n, t):
        self._create_sharedata_dir_if_not_exists()
        sid = uuid4().hex
        polys = [self.poly.random(t, x)]
        self._write_polys(
            f"{PreProcessingConstants.SHARES_FILE_NAME_PREFIX}_{sid}", n, t, polys)
        return sid

    def get_triple(self, ctx):
        key = (ctx.myid, ctx.N, ctx.t)
        if key not in self._triples:
            file_suffix = f"_{ctx.N}_{ctx.t}-{ctx.myid}.share"
            file_path = f"{PreProcessingConstants.TRIPLES_FILE_NAME_PREFIX}{file_suffix}"
            self._triples[key] = iter(self._read_share_values_from_file(file_path))
        a = ctx.Share(next(self._triples[key]))
        b = ctx.Share(next(self._triples[key]))
        ab = ctx.Share(next(self._triples[key]))
        return a, b, ab

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
                self._read_share_values_from_file(fpath))
        return ctx.Share(next(self._one_minus_one_rands[key]))

    def get_powers(self, ctx, pid):
        file_suffix = f"_{pid}_{ctx.N}_{ctx.t}-{ctx.myid}.share"
        return list(map(ctx.Share, self._read_share_values_from_file(
            f"{PreProcessingConstants.POWERS_FILE_NAME_PREFIX}{file_suffix}")))

    def get_share(self, ctx, sid, t=None):
        if t is None:
            t = ctx.t
        file_suffix = f"_{sid}_{ctx.N}_{t}-{ctx.myid}.share"
        share_values = self._read_share_values_from_file(
            f"{PreProcessingConstants.SHARES_FILE_NAME_PREFIX}{file_suffix}")
        return ctx.Share(share_values[0], t)

    def get_double_share(self, ctx):
        key = (ctx.myid, ctx.N, ctx.t)
        if key not in self._double_shares:
            suffix = f"_{ctx.N}_{ctx.t}-{ctx.myid}.share"
            path = f"{PreProcessingConstants.DOUBLE_SHARES_FILE_NAME_PREFIX}{suffix}"
            self._double_shares[key] = iter(self._read_share_values_from_file(path))
        r_t = ctx.Share(next(self._double_shares[key]))
        r_2t = ctx.Share(next(self._double_shares[key]), 2*ctx.t)
        return r_t, r_2t


async def wait_for_preprocessing():
    while not os.path.exists(f"{PreProcessingConstants.SHARED_DATA_DIR}READY"):
        logging.info(
            f"waiting for preprocessing {PreProcessingConstants.READY_FILE_NAME}")
        await asyncio.sleep(1)


def preprocessing_done():
    os.mknod(PreProcessingConstants.READY_FILE_NAME)
