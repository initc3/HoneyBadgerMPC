from pytest import mark
from honeybadgermpc.utils.misc import wrap_send
from random import randint
import asyncio


def test_wrap_send():
    test_dest, test_message = None, None

    def _send(dest, message):
        nonlocal test_dest, test_message
        test_dest = dest
        test_message = message

    wrapped = wrap_send("hello", _send)
    wrapped(1, "world")
    assert (test_dest, test_message) == (1, ("hello", "world"))


@mark.asyncio
async def test_pool():
    from honeybadgermpc.utils.task_pool import TaskPool

    max_tasks = 4

    async def work(q, max_tasks):
        assert q.qsize() <= max_tasks
        q.put_nowait(None)
        await asyncio.sleep(randint(0, 3) * 0.2)
        await q.get()

    pool = TaskPool(max_tasks)
    q = asyncio.Queue()
    for _ in range(10):
        pool.submit(work(q, max_tasks))
    await pool.close()
