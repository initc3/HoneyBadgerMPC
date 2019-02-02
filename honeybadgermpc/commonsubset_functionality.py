import asyncio
import logging


class ACSFunctionality(object):
    def __init__(self, sid, n, f):
        self.sid = sid
        self.N = n
        self.f = f
        self.inputs = [asyncio.Future() for _ in range(n)]
        self.outputs = [asyncio.Future() for _ in range(n)]

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


def common_subset_ideal_protocol(n, f):
    class ACSIdealProtocol(object):
        _instances = {}     # mapping from (sid,myid) to functionality shared state

        def __init__(self, sid, myid):
            # Create the ideal functionality if not already present
            if sid not in ACSIdealProtocol._instances:
                ACSIdealProtocol._instances[sid] = ACSFunctionality(sid, n, f)
            f_acs = ACSIdealProtocol._instances[sid]

            # Every party can provide one input
            self.input = f_acs.inputs[myid]

            # The output is a future
            self.output = f_acs.outputs[myid]
    return ACSIdealProtocol


async def _test_acs_ideal(sid='sid', n=4, f=1):
    acs = common_subset_ideal_protocol(n, f)
    parties = [acs(sid, i) for i in range(n)]

    # Provide input
    # for i in range(N-1): # if set to N-1, will still succeed, but N-2 fails
    for i in range(n):
        parties[i].input.set_result('hi'+str(i))

    # Now can await output from each ACS protocol
    for i in range(n):
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
