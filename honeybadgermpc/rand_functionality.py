import asyncio
import random
import logging
"""
Ideal functionality for Random Share
This protocol returns a single random share
"""


class ShareSingleFunctionality(object):
    def __init__(self, sid, n, f):
        self.sid = sid
        self.N = n
        self.f = f
        self.outputs = [asyncio.Future() for _ in range(n)]

        # Create output promises, even though we don't have input yet
        self._task = asyncio.ensure_future(self._run())

    async def _run(self):
        # TODO: get between 1 and N-t from the adversary
        v = [random.randint(0, 1000) for i in range(self.N)]
        for i in range(self.N):
            # TODO: this needs to be made into an "eventually send"
            self.outputs[i].set_result(v)


class ShareSingleIdealProtocol(object):
    _instances = {}     # mapping from (sid,myid) to functionality shared state

    def __init__(self, sid, n, f, myid):
        # Create the ideal functionality if not already present
        if sid not in ShareSingleIdealProtocol._instances:
            ShareSingleIdealProtocol._instances[sid] = \
                ShareSingleFunctionality(sid, n, f)

        # The output is a future
        f_ss = ShareSingleIdealProtocol._instances[sid]
        self.output = f_ss.outputs[myid]


async def _test_sharesingle_ideal(sid='sid', n=4, f=1):
    ShareSingleIdealProtocol._instances = {}   # Clear state
    parties = [ShareSingleIdealProtocol(sid, n, f, i) for i in range(n)]

    # Now can await output from each ShareSingle protocol
    for i in range(n):
        await parties[i].output
        logging.info(f"{i} {parties[i].output}")


def test_sharesingle_ideal():
    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    loop.set_debug(True)
    try:
        loop.run_until_complete(_test_sharesingle_ideal())
    finally:
        loop.close()


if __name__ == '__main__':
    test_sharesingle_ideal()
