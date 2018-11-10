from pytest import mark
from random import randint
import asyncio


@mark.asyncio
async def test_pool():
    from honeybadgermpc.task_pool import TaskPool

    max_tasks = 4

    async def work(q, max_tasks):
        assert q.qsize() <= max_tasks
        q.put_nowait(None)
        await asyncio.sleep(randint(0, 3)*0.2)
        await q.get()

    pool = TaskPool(max_tasks)
    q = asyncio.Queue()
    for _ in range(10):
        pool.submit(work(q, max_tasks))
    await pool.close()
