from pytest import mark
from itertools import chain
from progs.random_refinement import refine_randoms


@mark.parametrize("n, t, k", [(4, 1, 3), (4, 1, 4), (7, 2, 5)])
@mark.asyncio
async def test_random_refinement(
        n, t, k, galois_field, polynomial, test_preprocessing, test_runner):
    batch_size = 5

    async def _prog(context):
        unrefined_batches = [[test_preprocessing.elements.get_rand(
            context).v.value for i in range(k)] for _ in range(batch_size)]
        refined_batches = refine_randoms(n, t, k, galois_field, unrefined_batches)
        assert len(refined_batches) == batch_size
        assert all(len(batch) == k-t for batch in refined_batches)
        randoms = await context.ShareArray(
            list(chain.from_iterable(refined_batches))).open(False)
        return tuple(randoms)

    randoms = await test_runner(_prog, n, t, ["rands"], n*k*batch_size)

    assert len(randoms) == n
    assert len(set(randoms)) == 1
