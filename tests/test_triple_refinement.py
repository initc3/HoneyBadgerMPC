from pytest import mark
import asyncio


@mark.asyncio
async def test_triple_refinement(triples_files_prefix):
    from honeybadgermpc.mpc import TaskProgramRunner, generate_test_triples
    from honeybadgermpc.triple_refinement import refine_triples

    N, t = 7, 2
    # FIXME: This needs to be replaced with a fixture
    generate_test_triples(triples_files_prefix, N, N, t)

    async def _prog(context):
        filename = f'{triples_files_prefix}-{context.myid}.share'
        triple_shares = context.read_shares(open(filename))
        _a, _b, _c = [], [], []
        # Every party needs its share of all the `N` triples' shares
        for i in range(0, 3 * context.N, 3):
            p, q, pq = triple_shares[i:i+3]
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
