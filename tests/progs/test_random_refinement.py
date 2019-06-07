from pytest import mark
from honeybadgermpc.progs.random_refinement import refine_randoms


@mark.parametrize("n, t, k", [(4, 1, 3), (4, 1, 4), (7, 2, 5)])
@mark.asyncio
async def test_random_refinement(n, t, k, galois_field, polynomial, test_runner):
    async def _prog(context):
        random_shares = [context.preproc.get_rand(context).v.value for i in range(k)]
        refined_random_shares = refine_randoms(n, t, galois_field, random_shares)
        assert len(refined_random_shares) == k - t
        randoms = await context.ShareArray(refined_random_shares).open()
        return tuple(randoms)

    randoms = await test_runner(_prog, n, t, ["rands"], n * k)

    assert len(randoms) == n
    assert len(set(randoms)) == 1
