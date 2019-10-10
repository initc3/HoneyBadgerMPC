# Reference: https://gist.github.com/mdellavo/6aef86f7eba778611ce3cb9464c5fae5
import asyncio
from asyncio.queues import Queue


class TaskPool(object):
    def __init__(self, num_workers):
        self.loop = asyncio.get_event_loop()
        self.tasks = Queue(loop=self.loop)
        self.workers = []
        for _ in range(num_workers):
            worker = asyncio.create_task(self.worker())
            self.workers.append(worker)

    async def worker(self):
        while True:
            future, task = await self.tasks.get()
            if task == "TERMINATOR":
                break
            result = await asyncio.wait_for(task, None, loop=self.loop)
            future.set_result(result)

    def submit(self, task):
        future = asyncio.Future(loop=self.loop)
        self.tasks.put_nowait((future, task))
        return future

    async def close(self):
        for _ in self.workers:
            self.tasks.put_nowait((None, "TERMINATOR"))
        await asyncio.gather(*self.workers, loop=self.loop)
