from pytest import mark


@mark.asyncio
async def test_rand_():
    from honeybadgermpc.rand_batch import _test_rand
    await _test_rand()
