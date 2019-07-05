from honeybadgermpc.progs.mixins.dataflow import (
    Share,
    ShareArray,
    ShareFuture,
    GFElementFuture,
)
import asyncio
import logging
from collections import defaultdict
from .polynomial import polynomials_over
from .field import GF, GFElement
from .polynomial import EvalPoint
from .router import SimpleRouter
from .program_runner import ProgramRunner
from .robust_reconstruction import robust_reconstruct
from .batch_reconstruction import batch_reconstruct
from .elliptic_curve import Subgroup
from .preprocessing import PreProcessedElements
from .config import ConfigVars
from .exceptions import HoneyBadgerMPCError


class Mpc(object):
    def __init__(
        self, sid, n, t, myid, send, recv, prog, config, preproc=None, **prog_args
    ):
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

        # Counter that increments by 1 every time you access it
        # This will be used to assign ids to shares.
        self._share_id = 0

        # Store opened shares until ready to reconstruct
        # playerid => { [shareid => Future share] }
        self._share_buffers = tuple(defaultdict(asyncio.Future) for _ in range(n))

        # Batch reconstruction is handled slightly differently,
        # We'll create a separate queue for received values
        # { shareid => Queue() }
        self._sharearray_buffers = defaultdict(asyncio.Queue)

        # Dynamically create concrete subclasses of the classes using ourself as
        # their context property
        self.Share = type("Share", (Share,), {"context": self})
        self.ShareFuture = type("ShareFuture", (ShareFuture,), {"context": self})
        self.ShareArray = type("ShareArray", (ShareArray,), {"context": self})
        self.GFElementFuture = type(
            "GFElementFuture", (GFElementFuture,), {"context": self}
        )

    def _get_share_id(self):
        """Returns a monotonically increasing int value
        each time this is called
        """
        share_id = self._share_id
        self._share_id += 1
        return share_id

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
            Future that resolves to the plaintext value of the share.
        """

        res = asyncio.Future()

        # Choose the shareid based on the order this is called
        shareid = self._get_share_id()
        t = self.t
        degree = t if share.t is None else share.t

        # Broadcast share
        for dest in range(self.N):
            value_to_share = share.v

            # Send random data if meant to induce faults
            if (
                ConfigVars.Reconstruction in self.config
                and self.config[ConfigVars.Reconstruction].induce_faults
            ):
                logging.debug("[FAULT][RobustReconstruct] Sending random share.")
                value_to_share = self.field.random()

            # 'S' is for single shares
            self.send(dest, ("S", shareid, value_to_share))

        # Set up the buffer of received shares
        share_buffer = [self._share_buffers[i][shareid] for i in range(self.N)]

        point = EvalPoint(self.field, self.N, use_omega_powers=False)

        # Create polynomial that reconstructs the shared value by evaluating at 0
        reconstruction = asyncio.create_task(
            robust_reconstruct(share_buffer, self.field, self.N, t, point, degree)
        )

        def cb(r):
            p, errors = r.result()
            if p is None:
                logging.error(
                    f"Robust reconstruction for share (id: {shareid}) "
                    f"failed with errors: {errors}!"
                )
                res.set_exception(
                    HoneyBadgerMPCError(f"Failed to open share with id {shareid}!")
                )
            else:
                res.set_result(p(self.field(0)))

        reconstruction.add_done_callback(cb)

        # Return future that will resolve to reconstructed point
        return res

    def open_share_array(self, sharearray):
        """ Given array of secret shares, opens them in a batch
        and returns their plaintext values.

        args:
            sharearray (ShareArray): shares to open

        outputs:
            Future, which will resolve to an array of GFElements
        """
        res = asyncio.Future()
        if not sharearray._shares:
            res.set_result([])
            return res

        def cb(r):
            elements = r.result()
            if elements is None:
                logging.error(
                    f"Batch reconstruction for share_array (id: {shareid}) failed!"
                )
                res.set_exception(HoneyBadgerMPCError("Batch reconstruction failed!"))
            else:
                res.set_result(elements)

        shareid = self._get_share_id()
        t = self.t
        degree = t if sharearray.t is None else sharearray.t

        # Creates unique send function based on the share to open
        def _send(dest, o):
            (tag, share) = o
            self.send(dest, (tag, shareid, share))

        # Receive function from the respective queue for this node
        _recv = self._sharearray_buffers[shareid].get

        # Generate reconstructed array of shares
        reconstructed = asyncio.create_task(
            batch_reconstruct(
                [s.v for s in sharearray._shares],
                self.field.modulus,
                t,
                self.N,
                self.myid,
                _send,
                _recv,
                config=self.config.get(ConfigVars.Reconstruction),
                debug=True,
                degree=degree,
            )
        )

        reconstructed.add_done_callback(cb)

        return res

    async def _run(self):
        # Run receive loop as background task, until self.prog finishes
        # Cancel the background task, even if there's an exception
        bgtask = asyncio.create_task(self._recvloop())
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

    async def _recvloop(self):
        """Background task to continually receive incoming shares, and
        put the received share in the appropriate buffer. In the case
        of a single share this puts it into self._share_buffers, otherwise,
        it gets enqueued in the appropriate self._sharearray_buffers.
        """
        while True:
            (j, (tag, shareid, share)) = await self.recv()

            # Sort into single or batch
            if tag == "S":
                assert type(share) is GFElement, "?"
                buf = self._share_buffers[j]

                # Assert there is not an R1 or R2 value either
                assert shareid not in self._sharearray_buffers

                # Assert that there is not an element already
                if buf[shareid].done():
                    logging.info(f"redundant share: {j} {(tag, shareid)}")
                    raise AssertionError(f"Received a redundant share: {shareid}")

                buf[shareid].set_result(share)

            elif tag in ("R1", "R2"):
                assert type(share) is list

                # Assert there is not an 'S' value here
                assert shareid not in self._share_buffers[j]

                # Forward to the right queue
                self._sharearray_buffers[shareid].put_nowait((j, (tag, share)))

        return True


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
