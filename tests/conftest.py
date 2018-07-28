import os
import random

from pytest import fixture


@fixture
def sharedata_tmpdir(tmpdir):
    return tmpdir.mkdir('sharedata')


@fixture
def zeros_files_prefix(sharedata_tmpdir):
    return os.path.join(sharedata_tmpdir, 'test_zeros')


@fixture
def random_files_prefix(sharedata_tmpdir):
    return os.path.join(sharedata_tmpdir, 'test_random')


@fixture
def triples_files_prefix(sharedata_tmpdir):
    return os.path.join(sharedata_tmpdir, 'test_triples')


@fixture
# TODO check whether there could be a better name for this fixture,
# e.g.: bls12_381_field?
def GaloisField():
    from honeybadgermpc.field import GF
    return GF(0x73eda753299d7d483339d80809a1d80553bda402fffe5bfeffffffff00000001)


@fixture
def Polynomial(GaloisField):
    from honeybadgermpc.polynomial import polynomialsOver
    return polynomialsOver(GaloisField)


@fixture(params=({'k': 1000, 't': 2},))
def zero_polys(request, Polynomial):
    k = request.param['k']
    t = request.param['t']
    return [Polynomial.random(t, 0) for _ in range(k)]


@fixture(params=({'k': 1000, 't': 2},))
def random_polys(request, GaloisField, Polynomial):
    k = request.param['k']
    t = request.param['t']
    return [Polynomial.random(t, random.randint(0, GaloisField.modulus-1))
            for _ in range(k)]


@fixture(params=(1000,))
def triples_fields(request, GaloisField, Polynomial):
    k = request.param
    fields_batch = []
    for _ in range(k):
        a = GaloisField(random.randint(0, GaloisField.modulus-1))
        b = GaloisField(random.randint(0, GaloisField.modulus-1))
        c = a*b
        fields_batch.append((a, b, c))
    return fields_batch


@fixture(params=(2,))
def triples_polys(request, triples_fields, Polynomial):
    t = request.param
    return [
        Polynomial.random(t, field) for triple in triples_fields for field in triple
    ]


@fixture(params=({'N': 3, 't': 2},))
def zeros_shares_files(request, GaloisField, zero_polys, zeros_files_prefix):
    from honeybadgermpc.passive import write_polys
    N = request.param['N']
    t = request.param['t']
    write_polys(zeros_files_prefix, GaloisField.modulus, N, t, zero_polys)


@fixture(params=({'N': 3, 't': 2},))
def random_shares_files(request, GaloisField, random_polys, random_files_prefix):
    from honeybadgermpc.passive import write_polys
    N = request.param['N']
    t = request.param['t']
    write_polys(random_files_prefix, GaloisField.modulus, N, t, random_polys)


@fixture(params=({'N': 3, 't': 2},))
def triples_shares_files(request, GaloisField, triples_polys, triples_files_prefix):
    from honeybadgermpc.passive import write_polys
    N = request.param['N']
    t = request.param['t']
    write_polys(
        triples_files_prefix, GaloisField.modulus, N, t, triples_polys)
