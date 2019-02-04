import asyncio
import random

from pytest import fixture


@fixture
def galois_field():
    from honeybadgermpc.field import GF
    from honeybadgermpc.elliptic_curve import Subgroup
    return GF.get(Subgroup.BLS12_381)


@fixture
def polynomial(galois_field):
    from honeybadgermpc.polynomial import polynomials_over
    return polynomials_over(galois_field)


@fixture(params=(1,))
def triples_polys(request, triples_fields, polynomial):
    t = request.param
    return [
        polynomial.random(t, field) for triple in triples_fields for field in triple
    ]


class TestPreProcessing():
    def __init__(self):
        from honeybadgermpc.preprocessing import PreProcessedElements
        self.cache = {}
        self.elements = PreProcessedElements()

    def generate(self, kind, n, t, arg=None):
        if kind in ["zeros", "triples", "rands", "oneminusone"]:
            if (kind, n, t) in self.cache:
                return
            self.cache[(kind, n, t)] = True
            if kind == "zeros":
                self.elements.generate_zeros(1000, n, t)
            elif kind == "triples":
                self.elements.generate_triples(1000, n, t)
            elif kind == "rands":
                self.elements.generate_rands(1000, n, t)
            elif kind == "oneminusone":
                self.elements.generate_one_minus_one_rands(1000, n, t)
        elif kind == "powers":
            if (kind, n, t) not in self.cache:
                power_id = self.elements.generate_powers(arg, n, t)
                self.cache[(kind, n, t)] = power_id
            return self.cache[(kind, n, t)]
        elif kind == "share":
            return self.elements.generate_share(arg, n, t)


@fixture(scope="session")
def test_preprocessing():
    return TestPreProcessing()


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
