import asyncio
from pytest import mark
from itertools import chain
from honeybadgermpc.progs.triple_refinement import refine_triples


@mark.asyncio
@mark.parametrize("n, t, k", [(4, 1, 3), (4, 1, 4), (7, 2, 5), (7, 2, 7)])
async def test_triple_refinement(n, t, k, test_preprocessing, test_runner):
    num_batches = 3

    async def _prog(context):
        a_batches, b_batches, c_batches = [], [], []
        for _ in range(num_batches):
            _a, _b, _c = [], [], []
            # Every party needs its share of all the `N` triples' shares
            for _ in range(k):
                p, q, pq = test_preprocessing.elements.get_triple(context)
                _a.append(p.v.value), _b.append(q.v.value), _c.append(pq.v.value)
            a_batches.append(_a)
            b_batches.append(_b)
            c_batches.append(_c)
        # await refine_triples(context, k, A, B, C)
        p, q, pq = await refine_triples(context, k, a_batches, b_batches, c_batches)
        p = list(chain.from_iterable(p))
        q = list(chain.from_iterable(q))
        pq = list(chain.from_iterable(pq))
        async def _open(x): return await context.ShareArray(x).open(False)
        p, q, pq = await asyncio.gather(*[_open(p), _open(q), _open(pq)])
        assert len(p) == len(q) == len(pq) == ((k-2*t+1)//2)*num_batches
        for d, e, de in zip(p, q, pq):
            assert d * e == de

    await test_runner(_prog, n, t, ["triples"], n*k*num_batches)
