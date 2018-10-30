from pytest import mark


@mark.asyncio
async def test():
    from honeybadgermpc.secretshare_functionality import test1
    await test1()
