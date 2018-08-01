import asyncio
import random
"""
Ideal functionality for Random Share
This protocol returns a single random share
"""


class ShareSingle_Functionality(object):
    def __init__(self, sid, N, f):
        self.sid = sid
        self.N = N
        self.f = f
        self.outputs = [asyncio.Future() for _ in range(N)]

        # Create output promises, even though we don't have input yet
        self._task = asyncio.ensure_future(self._run())

    async def _run(self):
        # TODO: get between 1 and N-t from the adversary
        v = [random.randint(0, 1000) for i in range(self.N)]
        for i in range(self.N):
            # TODO: this needs to be made into an "eventually send"
            self.outputs[i].set_result(v)


class ShareSingle_IdealProtocol(object):
    _instances = {}     # mapping from (sid,myid) to functionality shared state

    def __init__(self, sid, N, f, myid):
        # Create the ideal functionality if not already present
        if sid not in ShareSingle_IdealProtocol._instances:
            ShareSingle_IdealProtocol._instances[sid] = \
                ShareSingle_Functionality(sid, N, f)

        # The output is a future
        F_SS = ShareSingle_IdealProtocol._instances[sid]
        self.output = F_SS.outputs[myid]


async def _test_sharesingle_ideal(sid='sid', N=4, f=1):
    ShareSingle_IdealProtocol._instances = {}   # Clear state
    parties = [ShareSingle_IdealProtocol(sid, N, f, i) for i in range(N)]

    # Now can await output from each ShareSingle protocol
    for i in range(N):
        await parties[i].output
        print(i, parties[i].output)


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
