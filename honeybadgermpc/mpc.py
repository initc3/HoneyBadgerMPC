from honeybadgermpc.progs.mixins.dataflow import (
    Share,
    ShareArray,
    ShareFuture,
    GFElementFuture,
)
import asyncio
import logging
from .polynomial import polynomials_over
from .field import GF
from .router import SimpleRouter
from .program_runner import ProgramRunner
from .elliptic_curve import Subgroup
from .preprocessing import PreProcessedElements
from .config import ConfigVars
from .exceptions import HoneyBadgerMPCError

from .progs.mixins.share_manager import SingleShareManager


class Mpc(object):
    def __init__(
        self, sid, n, t, myid, send, recv, prog, config, preproc=None, **prog_args
    ):
        """ Initialization for MPC context
        args:
            sid (str): Identifier of this MPC context
            n (int): Number of nodes used to run program
            t (int): Number of faults tolerable in MPC program
            myid (int): Id of this instance of the MPC program to run prog
            send (function): Send function to send a message to another node
            recv (function): Receive function to receive a share
            prog (function): MPC program to run
            config (object): MPC Configuration
            preproc (PreProcessedElements): Preprocessing used in running MPC Program
            prog_args (dict): Arguments to pass to MPC program
        """

        # Parameters for robust MPC
        # Note: tolerates min(t,N-t) crash faults
        assert type(n) is int and type(t) is int
        assert t < n
        self.sid = sid
        self.N = n
        self.t = t
        self.myid = myid
        self.field = GF(Subgroup.BLS12_381)
        self.poly = polynomials_over(self.field)
        self.config = config
        self.preproc = preproc if preproc is not None else PreProcessedElements()

        # send(j, o): sends object o to party j with (current sid)
        # recv(): returns (j, o) from party j
        self.send = send
        self.recv = recv

        # An Mpc program should only depend on common parameters,
        # and the values of opened shares. Opened shares will be
        # assigned an ID based on the order that share is encountered.
        # So the protocol must encounter the shares in the same order.
        self.prog = prog
        self.prog_args = prog_args

        induce_faults = (
            ConfigVars.Reconstruction in config
            and config[ConfigVars.Reconstruction].induce_faults
        )
        self._share_manager = SingleShareManager(self, induce_faults=induce_faults)

        self.Share = self._inject_context(Share)
        self.ShareFuture = self._inject_context(ShareFuture)
        self.ShareArray = self._inject_context(ShareArray)
        self.GFElementFuture = self._inject_context(GFElementFuture)

    def _inject_context(self, cls):
        return type(cls.__name__, (cls,), {"context": self})

    def call_mixin(self, name, *args, **kwargs):
        """Convenience method to check if a mixin is present, and call it if so
        args:
            name(str): Name of the mixin to call
            args(list): arguments to pass to the call to the mixin
            kwargs(dict): named arguments to pass to the call to the mixin

        outputs:
            future that resolves to the result of calling the mixin operation
        """
        if name not in self.config:
            raise NotImplementedError(f"Mixin {name} not present!")

        return asyncio.create_task(self.config[name](self, *args, **kwargs))

    def open_share(self, share):
        """ Given secret-shared value share, open the value by
        broadcasting our local share, and then receive the likewise
        broadcasted local shares from other nodes, and finally reconstruct
        the secret shared value.

        args:
            share (Share): Secret shared value to open

        outputs:
            Future that resolves to GFElement value of the share.
        """
        return self._share_manager.open_share(share)

    def open_share_array(self, share_array):
        """ Given array of secret shares, opens them in a batch
        and returns their plaintext values.

        args:
            sharearray (ShareArray): shares to open

        outputs:
            Future, which will resolve to an array of GFElements
        """
        return self._share_manager.open_share_array(share_array)

    async def _run(self):
        # Run receive loop as background task, until self.prog finishes
        # Cancel the background task, even if there's an exception
        bgtask = asyncio.create_task(self._share_manager.receive_loop())
        result = asyncio.create_task(self.prog(self, **self.prog_args))
        await asyncio.wait((bgtask, result), return_when=asyncio.FIRST_COMPLETED)

        # bgtask should not exit early-- this should correspond to an error
        if bgtask.done():
            logging.error("Background task finished before prog")

            bg_exception = bgtask.exception()
            if not result.done():
                result.cancel()

            if bg_exception is None:
                raise HoneyBadgerMPCError("background task finished before prog!")
            else:
                raise bg_exception

        bgtask.cancel()
        return result.result()


class TaskProgramRunner(ProgramRunner):
    def __init__(self, n, t, config={}):
        self.N, self.t = n, t
        self.counter = 0
        self.config = config
        self.tasks = []
        self.loop = asyncio.get_event_loop()
        self.router = SimpleRouter(self.N)

    def add(self, program, **kwargs):
        for i in range(self.N):
            context = Mpc(
                "mpc:%d" % (self.counter,),
                self.N,
                self.t,
                i,
                self.router.sends[i],
                self.router.recvs[i],
                program,
                self.config,
                **kwargs,
            )
            self.tasks.append(self.loop.create_task(context._run()))
        self.counter += 1

    async def join(self):
        return await asyncio.gather(*self.tasks)


###############
# Test programs
###############


async def test_batchopening(context):
    # Demonstrates use of ShareArray batch interface
    xs = [context.preproc.get_zero(context) + context.Share(i) for i in range(100)]
    xs = context.ShareArray(xs)
    xs_ = await xs.open()
    for i, x in enumerate(xs_):
        assert x.value == i
    logging.info("[%d] Finished batch opening" % (context.myid,))
    return xs_


async def test_prog1(context):
    # Example of Beaver multiplication
    x = context.preproc.get_zero(context) + context.Share(10)
    # x = context.Share(10)
    y = context.preproc.get_zero(context) + context.Share(15)
    # y = context.Share(15)

    a, b, ab = context.preproc.get_triples(context)
    # assert await a.open() * await b.open() == await ab.open()

    d = (x - a).open()
    e = (y - b).open()
    await d
    await e

    # This is a random share of x*y
    logging.info(f"type(d): {type(d)}")
    logging.info(f"type(b): {type(b)}")
    xy = d * e + d * b + e * a + ab

    logging.info(f"type(x): {type(x)}")
    logging.info(f"type(y): {type(y)}")
    logging.info(f"type(xy): {type(xy)}")
    x_, y_, xy_ = await x.open(), await y.open(), await xy.open()
    assert x_ * y_ == xy_

    logging.info(f"[{context.myid}] Finished {x_}, {y_}, {xy_}")


async def test_prog2(context):
    shares = [context.preproc.get_zero(context) for _ in range(1000)]
    for share in shares[:100]:
        s = await share.open()
        assert s == 0
    logging.info("[%d] Finished" % (context.myid,))

    # Batch version
    arr = context.ShareArray(shares[:100])
    for s in await arr.open():
        assert s == 0, s
    logging.info("[%d] Finished batch" % (context.myid,))


def handle_async_exception(loop, ctx):
    logging.info(f"handle_async_exception: {ctx}")


# Run some test cases
if __name__ == "__main__":
    pp_elements = PreProcessedElements()
    logging.info("Generating random shares of zero in sharedata/")
    pp_elements.generate_zeros(1000, 3, 1)
    logging.info("Generating random shares in sharedata/")
    pp_elements.generate_rands(1000, 3, 1)
    logging.info("Generating random shares of triples in sharedata/")
    pp_elements.generate_triples(1000, 3, 1)

    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    # loop.set_exception_handler(handle_async_exception)
    # loop.set_debug(True)
    try:
        logging.info("Start")
        program_runner = TaskProgramRunner(3, 1)
        program_runner.add(test_prog1)
        program_runner.add(test_prog2)
        program_runner.add(test_batchopening)
        loop.run_until_complete(program_runner.join())
    finally:
        loop.close()
