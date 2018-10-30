from pytest import mark


@mark.asyncio
async def test_sharesingle_ideal_():
    from honeybadgermpc.rand_functionality import _test_sharesingle_ideal
    await _test_sharesingle_ideal()
