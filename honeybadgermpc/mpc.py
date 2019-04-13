import asyncio
import logging
from collections import defaultdict
from .polynomial import polynomials_over
from .field import GF, GFElement
from .polynomial import EvalPoint
from .router import simple_router
from .program_runner import ProgramRunner
from .robust_reconstruction import robust_reconstruct
from .batch_reconstruction import batch_reconstruct
from .elliptic_curve import Subgroup
from .preprocessing import PreProcessedElements
from .mixins import MixinOpName
from .config import ConfigVars


class NotEnoughShares(Exception):
    pass


class BatchReconstructionFailed(Exception):
    pass


class Mpc(object):

    def __init__(self, sid, n, t, myid, pid, send, recv, prog, config, **prog_args):
        # Parameters for robust MPC
        # Note: tolerates min(t,N-t) crash faults
        assert type(n) is int and type(t) is int
        assert t < n
        self.sid = sid
        self.N = n
        self.t = t
        self.myid = myid
        self.pid = pid
        self.field = GF(Subgroup.BLS12_381)
        self.poly = polynomials_over(self.field)
        self.config = config

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

        # A task representing the opened values
        # { shareid => Future (field list(field)) }
        self._openings = {}

        # Store opened shares until ready to reconstruct
        # playerid => { [shareid => Future share] }
        self._share_buffers = tuple(defaultdict(asyncio.Future)
                                    for _ in range(n))

        # Batch reconstruction is handled slightly differently,
        # We'll create a separate queue for received values
        # { shareid => Queue() }
        self._sharearray_buffers = defaultdict(asyncio.Queue)

        self.Share, self.ShareArray = share_in_context(self)

    async def open_share(self, share):
        """ Given secret-shared value share, open the value by
        broadcasting our local share, and then receive the likewise
        broadcasted local shares from other nodes, and finally reconstruct
        the secret shared value.
        """

        # Choose the shareid based on the order this is called
        shareid = len(self._openings)
        t = share.t if share.t is not None else self.t

        # Broadcast share
        for j in range(self.N):
            value_to_share = share.v

            # Send random data if meant to induce faults
            if (ConfigVars.Reconstruction in self.config
                    and self.config[ConfigVars.Reconstruction].induce_faults):
                logging.debug("[FAULT][RobustReconstruct] Sending random share.")
                value_to_share = self.field.random()

            # 'S' is for single shares
            self.send(j, ('S', shareid, value_to_share))

        # Set up the buffer of received shares
        share_buffer = [self._share_buffers[i][shareid] for i in range(self.N)]

        point = EvalPoint(self.field, self.N, use_fft=False)

        # Create polynomial that reconstructs the shared value by evaluating at 0
        opening = robust_reconstruct(
            share_buffer, self.field, self.N, t, point)
        self._openings[shareid] = opening

        p, _ = await opening

        # Return reconstructed point
        return p(self.field(0))

    def open_share_array(self, sharearray):
        # Choose the shareid based on the order this is called
        shareid = len(self._openings)

        # Creates unique send function based on the share to open
        def _send(j, o):
            (tag, share) = o
            self.send(j, (tag, shareid, share))

        # Receive function from the respective queue for this node
        _recv = self._sharearray_buffers[shareid].get

        # Generate reconstructed array of shares
        opening = batch_reconstruct([s.v for s in sharearray._shares],
                                    self.field.modulus,
                                    sharearray.t,
                                    self.N,
                                    self.myid,
                                    _send,
                                    _recv,
                                    config=self.config.get(ConfigVars.Reconstruction),
                                    debug=True)
        self._openings[shareid] = opening
        return opening

    async def _run(self):
        # Run receive loop as background task, until self.prog finishes
        # Cancel the background task, even if there's an exception
        bgtask = asyncio.create_task(self._recvloop())
        result = asyncio.create_task(self.prog(self, **self.prog_args))
        await asyncio.wait((bgtask, result), return_when=asyncio.FIRST_COMPLETED)

        if result.done():
            bgtask.cancel()
            return result.result()
        else:
            logging.info(f'bgtask exception: {bgtask.exception()}')
            raise bgtask.exception()
            # FIXME: This code is unreachable and needs to be investigated
            bgtask.cancel()
            return await result

    async def _recvloop(self):
        """Background task to continually receive incoming shares, and
        put the received share in the appropriate buffer. In the case
        of a single share this puts it into self._share_buffers, otherwise,
        it gets enqueued in the appropriate self._sharearray_buffers.
        """
        while True:
            (j, (tag, shareid, share)) = await self.recv()

            # Sort into single or batch
            if tag == 'S':
                assert type(share) is GFElement, "?"
                buf = self._share_buffers[j]

                # Assert there is not an R1 or R2 value either
                assert shareid not in self._sharearray_buffers

                # Assert that there is not an element already
                if buf[shareid].done():
                    logging.info(f'redundant share: {j} {(tag, shareid)}')
                    raise AssertionError(f"Received a redundant share: {shareid}")

                buf[shareid].set_result(share)

            elif tag in ('R1', 'R2'):
                assert type(share) is list

                # Assert there is not an 'S' value here
                assert shareid not in self._share_buffers[j]

                # Forward to the right queue
                self._sharearray_buffers[shareid].put_nowait((j, (tag, share)))

        return True


###############
# Share class
###############

def share_in_context(context):
    class GFElementFuture(asyncio.Future):
        """Represents a future for GFElement. Allows for arithmetic operations
        to be stacked on top of the future value of this for when the value is resolved

        TODO: Add more methods from GFElement to GFElementFuture
            https://github.com/initc3/HoneyBadgerMPC/issues/245
        """

        def __add__(self, other):
            return self.__binop_field(other, lambda a, b: a + b)

        __radd__ = __add__

        def __sub__(self, other):
            return self.__binop_field(other, lambda a, b: a - b)

        def __rsub__(self, other):
            return self.__binop_field(other, lambda a, b: -a + b)

        def __mul__(self, other):
            return self.__binop_field(other, lambda a, b: a * b)

        def __binop_field(self, other, op):
            """Stacks the application of a function to the resolved value of
            this future GFElement
            """

            if isinstance(other, int):
                other = context.field(other)

            if not isinstance(other, (GFElement, GFElementFuture)):
                return NotImplemented

            res = GFElementFuture()

            if isinstance(other, GFElementFuture):
                asyncio.gather(self, other).add_done_callback(
                    lambda _: res.set_result(op(self.result(), other.result())))
            else:
                self.add_done_callback(
                    lambda _: res.set_result(op(self.result(), other)))

            return res

    class Share(object):
        """Represents a local share of a secret-shared GFElement
        """

        def __init__(self, v, t=None):
            # v is the local value of the share
            if type(v) is int:
                v = context.field(v)
            assert isinstance(v, (GFElement, GFElementFuture))
            self.v = v
            self.t = context.t if t is None else t

        # Publicly reconstruct a shared value
        def open(self):
            """Publicly reconstruct this secret-shared value

            output:
                GFElementFuture that resolves to the shared value
            """
            res = GFElementFuture()

            if isinstance(self.v, asyncio.Future):
                def cb1(v):
                    opening = asyncio.ensure_future(
                        context.open_share(Share(v.result())))
                    opening.add_done_callback(lambda f: res.set_result(f.result()))

                self.v.add_done_callback(cb1)
            else:
                # Wraps the open_share coroutine in a Task
                opening = asyncio.ensure_future(context.open_share(self))

                # Make res resolve to the opened value
                opening.add_done_callback(lambda f: res.set_result(f.result()))

            return res

        # Linear combinations of shares can be computed directly
        def __add__(self, other):
            if isinstance(other, GFElement):
                return Share(self.v + other, self.t)
            elif isinstance(other, Share):
                if self.t != other.t:
                    raise ValueError(
                        f"Shares can't be added to other shares with differing t \
                            values ({self.t} {other.t})")

                return Share(self.v + other.v, self.t)

            return NotImplemented

        __radd__ = __add__

        def __neg__(self):
            return Share(-self.v), self.t

        def __sub__(self, other):
            if isinstance(other, GFElement):
                return Share(self.v - other, self.t)
            elif isinstance(other, Share):
                if self.t == other.t:
                    return Share(self.v - other.v, self.t)

                raise ValueError(
                    f"Shares must have same t value to subtract: \
                        ({self.t} {other.t})")

            return NotImplemented

        def __rsub__(self, other):
            if isinstance(other, GFElement):
                return Share(-self.v + other, self.t)

            return NotImplemented

        def __mul__(self, other):
            if isinstance(other, (int, GFElement)):
                return Share(self.v * other, self.t)

            if not isinstance(other, Share):
                return NotImplemented
            elif MixinOpName.MultiplyShare not in context.config:
                return NotImplemented

            if self.t != other.t:
                raise ValueError(
                    f"Shares with differing t values cannot be multiplied \
                        ({self.t} {other.t})")

            res = ShareFuture()

            product = asyncio.ensure_future(
                context.config[MixinOpName.MultiplyShare](context, self, other))
            product.add_done_callback(lambda p: res.set_result(p.result()))

            return res

        def __rmul__(self, other):
            if isinstance(other, (int, GFElement)):
                return Share(self.v * other, self.t)

            return NotImplemented

        def __div__(self, other):
            if not isinstance(other, Share):
                return NotImplemented
            elif MixinOpName.InvertShare not in context.config:
                return NotImplemented

            if self.t != other.t:
                raise ValueError(
                    f"Cannot divide shares with differing t values ({self.t} {other.t})")

            res = ShareFuture()

            inverted = asyncio.ensure_future(
                context.config[MixinOpName.InvertShare](context, other))
            inverted.add_done_callback(lambda i: res.set_result(i.result()))

            return res * self

        __truediv__ = __floordiv__ = __div__

        def __str__(self):
            return '{%d}' % (self.v)

    class ShareFuture(asyncio.Future):
        def __add__(self, other):
            return self.__binop_share(other, lambda a, b: a + b)

        __radd__ = __add__

        def __sub__(self, other):
            return self.__binop_share(other, lambda a, b: a - b)

        def __rsub__(self, other):
            return self.__binop_share(other, lambda a, b: b - a)

        def __mul__(self, other):
            return self.__binop_share(other, lambda a, b: a * b)

        __rmul__ = __mul__

        def __div__(self, other):
            return self.__binop_share(other, lambda a, b: a / b)

        __truediv__ = __floordiv__ = __div__

        def __rdiv__(self, other):
            return self.__binop_share(other, lambda a, b: b / a)

        __rtruediv__ = __rfloordiv__ = __rdiv__

        def __binop_share(self, other, op):
            """Stacks the application of a function to the resolved value
            of this future with another value, which may or may not be a
            future as well.
            """

            if isinstance(other, int):
                other = context.field(other)

            res = ShareFuture()

            def cb(r):
                """Callback first applies the function to the resolved
                values, and if the resulting value is a future, we add
                a callback to that value to populate res when it's resolved,
                otherwise, directly sets the result of res with the result of
                invoking op.
                """

                if isinstance(other, asyncio.Future):
                    op_res = op(self.result(), other.result())
                else:
                    op_res = op(self.result(), other)

                if isinstance(op_res, asyncio.Future):
                    op_res.add_done_callback(lambda f: res.set_result(f.result()))
                else:
                    res.set_result(op_res)

            if isinstance(other, (ShareFuture, GFElementFuture)):
                asyncio.gather(self, other).add_done_callback(cb)
            elif isinstance(other, (Share, GFElement)):
                self.add_done_callback(cb)
            else:
                return NotImplemented

            return res

        def open(self):
            """Returns a future that resolves to the opened
            value of this share
            """
            res = GFElementFuture()

            # Adds 2 layers of callbacks-- one to open the share when
            # it resolves, and the next to set the value of res when opening
            # resolves
            self.add_done_callback(
                lambda _: self.result().open().add_done_callback(
                    lambda sh: res.set_result(sh.result())))

            return res

    class ShareArray(object):
        def __init__(self, values, t=None):
            # Initialized with a list of share objects
            self.t = context.t if t is None else t
            for i, value in enumerate(values):
                if isinstance(value, int) or isinstance(value, GFElement):
                    values[i] = context.Share(value, self.t)
                assert type(values[i]) is Share
            self._shares = values

        def open(self):
            # TODO: make a list of GFElementFutures?
            # res = GFElementFuture()
            res = asyncio.Future()

            def cb(f): return res.set_result(f.result())
            opening = asyncio.create_task(context.open_share_array(self))
            opening.add_done_callback(cb)
            return res

        def __add__(self, other):
            if isinstance(other, list):
                result = []
                for (a, b) in zip(self._shares, other):
                    assert type(b) is GFElement, type(b)
                    result.append(a+b)
                return ShareArray(result, self.t)
            if isinstance(other, ShareArray):
                assert self.t == other.t
                assert len(self._shares) == len(other._shares)
                return ShareArray(
                    [(a+b) for (a, b) in zip(self._shares, other._shares)], self.t)
            raise NotImplementedError

        def __sub__(self, other):
            if isinstance(other, ShareArray):
                assert self.t == other.t
                assert len(self._shares) == len(other._shares)
                return ShareArray(
                    [(a-b) for (a, b) in zip(self._shares, other._shares)], self.t)

        def __mul__(self, other):
            if MixinOpName.MultiplyShareArray in context.config:
                assert type(other) is ShareArray
                return context.config[MixinOpName.MultiplyShareArray](
                    context, self, other)
            else:
                raise NotImplementedError

        def __div__(self, other):
            if MixinOpName.InvertShareArray not in context.config:
                raise NotImplementedError
            elif MixinOpName.MultiplyShareArray not in context.config:
                raise NotImplementedError

            async def divide(curr, other):
                other_inverted = await(
                    context.config[MixinOpName.InvertShareArray](context, other))

                multiplier = context.config[MixinOpName.MultiplyShareArray]
                return await(multiplier(context, curr, other_inverted))

            return divide(self, other)

        __truediv__ = __floordiv__ = __div__

    return Share, ShareArray


class TaskProgramRunner(ProgramRunner):
    def __init__(self, n, t, config={}):
        self.N, self.t, self.pid = n, t, 0
        self.config = config
        self.tasks = []
        self.loop = asyncio.get_event_loop()

    def add(self, program, **kwargs):
        sends, recvs = simple_router(self.N)
        for i in range(self.N):
            context = Mpc(
                'sid',
                self.N,
                self.t,
                i,
                self.pid,
                sends[i],
                recvs[i],
                program,
                self.config,
                **kwargs,
            )
            self.tasks.append(self.loop.create_task(context._run()))
        self.pid += 1

    async def join(self):
        return await asyncio.gather(*self.tasks)


###############
# Test programs
###############

async def test_batchopening(context):
    pp_elements = PreProcessedElements()
    # Demonstrates use of ShareArray batch interface
    xs = [pp_elements.get_zero(context) + context.Share(i) for i in range(100)]
    xs = context.ShareArray(xs)
    xs_ = await xs.open()
    for i, x in enumerate(xs_):
        assert x.value == i
    logging.info("[%d] Finished batch opening" % (context.myid,))


async def test_prog1(context):
    pp_elements = PreProcessedElements()
    # Example of Beaver multiplication
    x = pp_elements.get_zero(context) + context.Share(10)
    # x = context.Share(10)
    y = pp_elements.get_zero(context) + context.Share(15)
    # y = context.Share(15)

    a, b, ab = pp_elements.get_triple(context)
    # assert await a.open() * await b.open() == await ab.open()

    d = (x - a).open()
    e = (y - b).open()
    await d
    await e

    # This is a random share of x*y
    logging.info(f'type(d): {type(d)}')
    logging.info(f'type(b): {type(b)}')
    xy = d*e + d*b + e*a + ab

    logging.info(f'type(x): {type(x)}')
    logging.info(f'type(y): {type(y)}')
    logging.info(f'type(xy): {type(xy)}')
    x_, y_, xy_ = await x.open(), await y.open(), await xy.open()
    assert x_ * y_ == xy_

    logging.info(f"[{context.myid}] Finished {x_}, {y_}, {xy_}")


async def test_prog2(context):
    pp_elements = PreProcessedElements()
    shares = [pp_elements.get_zero(context) for _ in range(1000)]
    for share in shares[:100]:
        s = await share.open()
        assert s == 0
    logging.info('[%d] Finished' % (context.myid,))

    # Batch version
    arr = context.ShareArray(shares[:100])
    for s in await arr.open():
        assert s == 0, s
    logging.info('[%d] Finished batch' % (context.myid,))


def handle_async_exception(loop, ctx):
    logging.info(f'handle_async_exception: {ctx}')


# Run some test cases
if __name__ == '__main__':
    pp_elements = PreProcessedElements()
    logging.info('Generating random shares of zero in sharedata/')
    pp_elements.generate_zeros(1000, 3, 1)
    logging.info('Generating random shares in sharedata/')
    pp_elements.generate_rands(1000, 3, 1)
    logging.info('Generating random shares of triples in sharedata/')
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
