from pytest import mark
import asyncio


@mark.asyncio
async def test_triple_refinement(triples_files_prefix):
    from honeybadgermpc.mpc import TaskProgramRunner
    from honeybadgermpc.triple_refinement import refine_triples
    from honeybadgermpc.preprocessing import PreProcessedElements

    N, t = 7, 2
    pp_elements = PreProcessedElements()
    pp_elements.generate_triples(N, N, t)

    async def _prog(context):
        _a, _b, _c = [], [], []
        # Every party needs its share of all the `N` triples' shares
        for _ in range(0, 3 * context.N, 3):
            p, q, pq = pp_elements.get_triple(context)
            _a.append(p.v), _b.append(q.v), _c.append(pq.v)
        a, b, ab = await refine_triples(context, _a, _b, _c)
        p = await asyncio.gather(*map(lambda x: x.open(), a))
        q = await asyncio.gather(*map(lambda x: x.open(), b))
        pq = await asyncio.gather(*map(lambda x: x.open(), ab))
        assert len(p) == len(q) == len(pq), "Invalid number of values generated"
        for d, e, de in zip(p, q, pq):
            # print("\n[%d] %d * %d == %d" % (context.myid, d, e, de))
            assert d * e == de

    programRunner = TaskProgramRunner(N, t)
    programRunner.add(_prog)
    await programRunner.join()
