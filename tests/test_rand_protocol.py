from pytest import mark


@mark.asyncio
async def test_naive_():
    from honeybadgermpc.rand_protocol import _test_naive
    await _test_naive()


@mark.asyncio
async def test_rand_():
    from honeybadgermpc.rand_protocol import _test_rand
    await _test_rand()
