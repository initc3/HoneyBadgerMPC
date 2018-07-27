import asyncio

from pytest import mark


@mark.asyncio
async def test(event_loop):
    from honeybadgermpc.secretshare_functionality import test1
    await test1()
