from pytest import mark
import asyncio


@mark.asyncio
async def test_triple_refinement(test_preprocessing):
    from honeybadgermpc.mpc import TaskProgramRunner
    from honeybadgermpc.progs.triple_refinement import refine_triples

    n, t = 7, 2

    test_preprocessing.generate("triples", n, t)

    async def _prog(context):
        _a, _b, _c = [], [], []
        # Every party needs its share of all the `N` triples' shares
        for _ in range(context.N):
            p, q, pq = test_preprocessing.elements.get_triple(context)
            _a.append(p.v.value), _b.append(q.v.value), _c.append(pq.v.value)
        a, b, ab = await refine_triples(context, _a, _b, _c)
        p = await asyncio.gather(*map(lambda x: x.open(), a))
        q = await asyncio.gather(*map(lambda x: x.open(), b))
        pq = await asyncio.gather(*map(lambda x: x.open(), ab))
        assert len(p) == len(q) == len(pq), "Invalid number of values generated"
        for d, e, de in zip(p, q, pq):
            # print("\n[%d] %d * %d == %d" % (context.myid, d, e, de))
            assert d * e == de

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    await program_runner.join()
