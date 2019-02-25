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


class NotEnoughShares(Exception):
    pass


class BatchReconstructionFailed(Exception):
    pass


class Mpc(object):

    def __init__(self, sid, n, t, myid, pid, send, recv, prog, mixin_ops, **prog_args):
        # Parameters for robust MPC
        # Note: tolerates min(t,N-t) crash faults
        assert type(n) is int and type(t) is int
        assert t < n
        self.sid = sid
        self.N = n
        self.t = t
        self.myid = myid
        self.pid = pid
        self.field = GF.get(Subgroup.BLS12_381)
        self.poly = polynomials_over(self.field)
        self.mixin_ops = mixin_ops

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
        # Choose the shareid based on the order this is called
        shareid = len(self._openings)
        t = share.t if share.t is not None else self.t
        # Broadcast share
        for j in range(self.N):
            # 'S' is for single shares
            self.send(j, ('S', shareid, share.v))

        # Set up the buffer of received shares
        share_buffer = [self._share_buffers[i][shareid] for i in range(self.N)]

        point = EvalPoint(self.field, self.N, use_fft=False)
        opening = robust_reconstruct(
            share_buffer, self.field, self.N, t, point)
        self._openings[shareid] = opening
        p, _ = await opening
        return p(self.field(0))

    def open_share_array(self, sharearray):
        # Choose the shareid based on the order this is called
        shareid = len(self._openings)

        def _send(j, o):
            (tag, share) = o
            self.send(j, (tag, shareid, share))
        _recv = self._sharearray_buffers[shareid].get
        opening = batch_reconstruct([s.v for s in sharearray._shares],
                                    self.field.modulus, sharearray.t, self.N,
                                    self.myid, _send, _recv, debug=True)
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
                assert not buf[shareid].done(
                ), "Received a redundant share: %o" % shareid
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

    def _binop_field(fut, other, op):
        assert type(other) in [ShareFuture, GFElementFuture, Share, GFElement]
        if isinstance(other, ShareFuture) or isinstance(other, Share):
            res = ShareFuture()
        elif isinstance(other, GFElement) or isinstance(other, GFElementFuture):
            res = GFElementFuture()

        if isinstance(other, asyncio.Future):
            def cb(f): return res.set_result(op(fut.result(), other.result()))
            asyncio.gather(fut, other).add_done_callback(cb)
        else:
            def cb(f): return res.set_result(op(fut.result(), other))
            fut.add_done_callback(cb)
        return res

    class GFElementFuture(asyncio.Future):
        def __add__(self, other): return _binop_field(
            self, other, lambda a, b: a + b)

        def __sub__(self, other): return _binop_field(
            self, other, lambda a, b: a - b)

        def __mul__(self, other): return _binop_field(
            self, other, lambda a, b: a * b)

    class Share(object):
        def __init__(self, v, t=None):
            # v is the local value of the share
            if type(v) is int:
                v = context.field(v)
            assert type(v) is GFElement
            self.v = v
            self.t = context.t if t is None else t

        # Publicly reconstruct a shared value
        def open(self):
            res = GFElementFuture()

            def cb(f): return res.set_result(f.result())
            opening = asyncio.ensure_future(context.open_share(self))
            # context._newopening.put_nowait(opening)
            opening.add_done_callback(cb)
            return res

        # Linear combinations of shares can be computed directly
        # TODO: add type checks for the operators
        # @typecheck(Share)
        def __add__(self, other):
            if isinstance(other, GFElement):
                return Share(self.v + other, self.t)
            elif isinstance(other, Share):
                assert self.t == other.t
                return Share(self.v + other.v, self.t)

        def __sub__(self, other):
            assert self.t == other.t, f"{self.t} {other.t}"
            return Share(self.v - other.v, self.t)
        __radd__ = __add__

        def __rsub__(self, other):
            assert self.t == other.t
            return Share(-self.v + other.v, self.t)

        def __xor__(self, other):
            if isinstance(other, GFElement):
                return Share(self.v ^ other, self.t)
            elif isinstance(other, Share):
                assert self.t == other.t
                return Share(self.v ^ other.v, self.t)

        # @typecheck(int,field)
        def __rmul__(self, other): return Share(self.v * other, self.t)

        # TODO
        def __mul__(self, other):
            assert type(other) is Share
            assert self.t == other.t
            if MixinOpName.MultiplyShare in context.mixin_ops:
                return context.mixin_ops[MixinOpName.MultiplyShare](context, self, other)
            else:
                raise NotImplementedError

        def __str__(self): return '{%d}' % (self.v)

    def _binop_share(fut, other, op):
        assert type(other) in [ShareFuture, GFElementFuture, Share, GFElement]
        res = ShareFuture()
        if isinstance(other, asyncio.Future):
            def cb(f): return res.set_result(op(fut.result(), other.result()))
            asyncio.gather(fut, other).add_done_callback(cb)
        else:
            def cb(f): return res.set_result(op(fut.result(), other))
            fut.add_done_callback(cb)
        return res

    class ShareFuture(asyncio.Future):
        def __add__(self, other): return _binop_share(
            self, other, lambda a, b: a + b)

        def __sub__(self, other): return _binop_share(
            self, other, lambda a, b: a - b)

        def __mul__(self, other): return _binop_share(
            self, other, lambda a, b: a * b)

        def open(self):
            res = GFElementFuture()

            def cb2(sh): return res.set_result(sh.result())

            def cb1(f): return self.result().open().add_done_callback(cb2)
            self.add_done_callback(cb1)
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
            if MixinOpName.MultiplyShareArray in context.mixin_ops:
                assert type(other) is ShareArray
                return context.mixin_ops[MixinOpName.MultiplyShareArray](
                    context, self, other)
            else:
                raise NotImplementedError

    return Share, ShareArray


class TaskProgramRunner(ProgramRunner):
    def __init__(self, n, t, mixin_ops={}):
        self.N, self.t, self.pid = n, t, 0
        self.mixin_ops = mixin_ops
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
                self.mixin_ops,
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

    logging.info(f"[%d] Finished {context.myid}, {x_}, {y_}, {xy_}")


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
