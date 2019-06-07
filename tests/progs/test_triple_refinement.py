import asyncio
from pytest import mark
from honeybadgermpc.progs.triple_refinement import refine_triples


@mark.asyncio
@mark.parametrize("n, t, k", [(4, 1, 3), (4, 1, 4), (7, 2, 5), (7, 2, 7)])
async def test_triple_refinement(n, t, k, test_runner):
    async def _prog(context):
        _a, _b, _c = [], [], []
        # Every party needs its share of all the `N` triples' shares
        for _ in range(k):
            p, q, pq = context.preproc.get_triples(context)
            _a.append(p.v.value), _b.append(q.v.value), _c.append(pq.v.value)
        p, q, pq = await refine_triples(context, _a, _b, _c)

        async def _open(x):
            return await context.ShareArray(x).open()

        p, q, pq = await asyncio.gather(*[_open(p), _open(q), _open(pq)])
        assert len(p) == len(q) == len(pq) == (k - 2 * t + 1) // 2
        for d, e, de in zip(p, q, pq):
            assert d * e == de

    await test_runner(_prog, n, t, ["triples"], n * k)
