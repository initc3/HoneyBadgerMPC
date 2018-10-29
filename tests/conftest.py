import asyncio
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
    return GF.get(0x73eda753299d7d483339d80809a1d80553bda402fffe5bfeffffffff00000001)


@fixture
def Polynomial(GaloisField):
    from honeybadgermpc.polynomial import polynomialsOver
    return polynomialsOver(GaloisField)


@fixture(params=({'k': 1000, 't': 1},))
def zero_polys(request, Polynomial):
    k = request.param['k']
    t = request.param['t']
    return [Polynomial.random(t, 0) for _ in range(k)]


@fixture(params=({'k': 1000, 't': 1},))
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


@fixture(params=(1,))
def triples_polys(request, triples_fields, Polynomial):
    t = request.param
    return [
        Polynomial.random(t, field) for triple in triples_fields for field in triple
    ]


@fixture(params=({'N': 3, 't': 1},))
def zeros_shares_files(request, GaloisField, zero_polys, zeros_files_prefix):
    from honeybadgermpc.passive import write_polys
    N = request.param['N']
    t = request.param['t']
    write_polys(zeros_files_prefix, GaloisField.modulus, N, t, zero_polys)


@fixture(params=({'N': 3, 't': 1},))
def random_shares_files(request, GaloisField, random_polys, random_files_prefix):
    from honeybadgermpc.passive import write_polys
    N = request.param['N']
    t = request.param['t']
    write_polys(random_files_prefix, GaloisField.modulus, N, t, random_polys)


@fixture(params=({'N': 3, 't': 1},))
def triples_shares_files(request, GaloisField, triples_polys, triples_files_prefix):
    from honeybadgermpc.passive import write_polys
    N = request.param['N']
    t = request.param['t']
    write_polys(
        triples_files_prefix, GaloisField.modulus, N, t, triples_polys)


@fixture
def simple_router():

    def _simple_router(N):
        """
        Builds a set of connected channels

        :return: broadcasting and receiving functions: ``(sends, receives)``
        :rtype: tuple
        """
        # Create a mailbox for each party
        mbox = [asyncio.Queue() for _ in range(N)]

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
        for i in range(N):
            sends[i] = make_send(i)
            receives[i] = make_recv(i)
        return (sends, receives)

    return _simple_router


@fixture
def random_element():
    # TODO parametrize for `order`
    order = 17
    return random.randint(0, order)


class Runtime():
    def __init__(self, id, N, t, send, recv):
        assert type(n) in (int, long)   # noqa TODO n is undefined
        assert 3 <= k <= n  # noqa TODO fix: k is undefined
        self.N = N
        self.t = t
        self.id = id

        asyncio.get_event_loop().create_task(self._run)

    async def _run(self):
        while True:
            await asyncio.sleep(1)

    def createshare(self, val):
        s = Share(self)
        s._val = val
        return s

    def _send():
        pass


@fixture
def runtime():
    return Runtime()


class Share():
    def __init__(self, runtime):
        pass

    async def open(self, _):
        # reveal share

        # wait for shares
        pass


@fixture
def share():
    return Share()
