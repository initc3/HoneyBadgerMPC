import asyncio
import os
import random

from pytest import fixture


@fixture
def sharedatadir():
    os.makedirs('sharedata', exist_ok=True)


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
def galois_field():
    from honeybadgermpc.field import GF
    return GF.get(0x73eda753299d7d483339d80809a1d80553bda402fffe5bfeffffffff00000001)


@fixture
def polynomial(galois_field):
    from honeybadgermpc.polynomial import polynomials_over
    return polynomials_over(galois_field)


@fixture(params=({'k': 1000, 't': 1},))
def zero_polys(request, polynomial):
    k = request.param['k']
    t = request.param['t']
    return [polynomial.random(t, 0) for _ in range(k)]


@fixture(params=({'k': 1000, 't': 1},))
def random_polys(request, galois_field, polynomial):
    k = request.param['k']
    t = request.param['t']
    return [polynomial.random(t, random.randint(0, galois_field.modulus-1))
            for _ in range(k)]


@fixture(params=(1000,))
def triples_fields(request, galois_field, polynomial):
    k = request.param
    fields_batch = []
    for _ in range(k):
        a = galois_field(random.randint(0, galois_field.modulus-1))
        b = galois_field(random.randint(0, galois_field.modulus-1))
        c = a*b
        fields_batch.append((a, b, c))
    return fields_batch


@fixture(params=(1,))
def triples_polys(request, triples_fields, polynomial):
    t = request.param
    return [
        polynomial.random(t, field) for triple in triples_fields for field in triple
    ]


@fixture(params=({'N': 3, 't': 1},))
def zeros_shares_files(request, galois_field, zero_polys, zeros_files_prefix):
    from honeybadgermpc.mpc import write_polys
    n = request.param['N']
    t = request.param['t']
    write_polys(zeros_files_prefix, galois_field.modulus, n, t, zero_polys)


@fixture(params=({'N': 3, 't': 1},))
def random_shares_files(request, galois_field, random_polys, random_files_prefix):
    from honeybadgermpc.mpc import write_polys
    n = request.param['N']
    t = request.param['t']
    write_polys(random_files_prefix, galois_field.modulus, n, t, random_polys)


@fixture(params=({'N': 3, 't': 1},))
def triples_shares_files(request, galois_field, triples_polys, triples_files_prefix):
    from honeybadgermpc.mpc import write_polys
    n = request.param['N']
    t = request.param['t']
    write_polys(
        triples_files_prefix, galois_field.modulus, n, t, triples_polys)


@fixture
def simple_router():

    def _simple_router(n):
        """
        Builds a set of connected channels

        :return: broadcasting and receiving functions: ``(sends, receives)``
        :rtype: tuple
        """
        # Create a mailbox for each party
        mbox = [asyncio.Queue() for _ in range(n)]

        def make_send(i):
            def _send(j, o):
                # print('SEND %8s [%2d -> %2d]' % (o[0], i, j))
                # random delay
                asyncio.get_event_loop().call_later(
                    random.random()*1, mbox[j].put_nowait, (i, o))
            return _send

        def make_recv(j):
            async def _recv():
                i, o = await mbox[j].get()
                # print('RECV %8s [%2d -> %2d]' % (o[0], i, j))
                return i, o
            return _recv

        sends = {}
        receives = {}
        for i in range(n):
            sends[i] = make_send(i)
            receives[i] = make_recv(i)
        return (sends, receives)

    return _simple_router
