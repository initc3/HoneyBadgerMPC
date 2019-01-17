import asyncio
import logging


class ACS_Functionality(object):
    def __init__(self, sid, N, f):
        self.sid = sid
        self.N = N
        self.f = f
        self.inputs = [asyncio.Future() for _ in range(N)]
        self.outputs = [asyncio.Future() for _ in range(N)]

        # Create output promises, even though we don't have input yet
        self._task = asyncio.ensure_future(self._run())

    async def _run(self):
        # Wait for at least N-f inputs to arrive
        pending = set(self.inputs)
        ready = set()
        while len(ready) < self.N - self.f:
            done, pending = await asyncio.wait(
                pending, return_when=asyncio.FIRST_COMPLETED)
            ready.update(done)

        logging.info('ACS_Functionality done')
        out = [inp.result() if inp.done() else None for inp in self.inputs]

        for i in range(self.N):
            # TODO: this needs to be made into an "eventually send"
            self.outputs[i].set_result(out)


def CommonSubset_IdealProtocol(N, f):
    class ACS_IdealProtocol(object):
        _instances = {}     # mapping from (sid,myid) to functionality shared state

        def __init__(self, sid, myid):
            # Create the ideal functionality if not already present
            if sid not in ACS_IdealProtocol._instances:
                ACS_IdealProtocol._instances[sid] = ACS_Functionality(sid, N, f)
            F_ACS = ACS_IdealProtocol._instances[sid]

            # Every party can provide one input
            self.input = F_ACS.inputs[myid]

            # The output is a future
            self.output = F_ACS.outputs[myid]
    return ACS_IdealProtocol


async def _test_acs_ideal(sid='sid', N=4, f=1):
    ACS = CommonSubset_IdealProtocol(N, f)
    parties = [ACS(sid, i) for i in range(N)]

    # Provide input
    # for i in range(N-1): # if set to N-1, will still succeed, but N-2 fails
    for i in range(N):
        parties[i].input.set_result('hi'+str(i))

    # Now can await output from each ACS protocol
    for i in range(N):
        await parties[i].output
        logging.info(f"{i} {parties[i].output}")


def test_acs_ideal():
    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    loop.set_debug(True)
    try:
        loop.run_until_complete(_test_acs_ideal())
    finally:
        loop.close()


if __name__ == '__main__':
    test_acs_ideal()
