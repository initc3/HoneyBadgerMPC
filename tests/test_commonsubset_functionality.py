from pytest import mark


@mark.asyncio
async def test_acs_ideal_():
    from honeybadgermpc.commonsubset_functionality import _test_acs_ideal
    await _test_acs_ideal()
