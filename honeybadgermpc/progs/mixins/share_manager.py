from __future__ import annotations  # noqa: F407

import asyncio
import logging

from abc import ABC, abstractmethod
from collections import defaultdict

from honeybadgermpc.field import GFElement
from honeybadgermpc.utils.typecheck import TypeCheck
from honeybadgermpc.polynomial import EvalPoint
from honeybadgermpc.robust_reconstruction import robust_reconstruct
from honeybadgermpc.batch_reconstruction import batch_reconstruct
from honeybadgermpc.exceptions import HoneyBadgerMPCError
from honeybadgermpc.config import ConfigVars
from .dataflow import Share, ShareFuture, ShareArray


class ShareManager(ABC):
    """ Manages the opening of shares.
    """
    @abstractmethod
    def open_share(self, share: (Share, ShareFuture)) -> asyncio.Future:
        """ Given a secret-shared value share, open the value to reveal its plaintext
        value.

        args:
            share (Share): Secret shared value to be opened

        outputs:
            Future that resolves to the plaintext GFElement value of the share
        """
        pass

    @abstractmethod
    def open_share_array(self, share_array: ShareArray) -> asyncio.Future:
        """ Given a list of secret-shared values share_array, open the values to reveal
        their plaintext values.

        args:
            share_array (ShareArray): List of secret shared values to be opened

        outputs:
            Future that resolves to an array of GFElements.
        """
        pass

    @abstractmethod
    async def force_opening(self) -> bool:
        """ Force flush any in-progress reconstructions

        Return True if successful
        """
        pass

    @abstractmethod
    async def _loop_once(self):
        """ Blocking operation to poll for an incoming share, and perform associated
        bookkeeping.

        Return True to indicate if looping should be continued
        """
        pass

    async def receive_loop(self, iterations=-1):
        """ Blocking background task which continually polls for incoming shares, and
        perform associated bookkeeping.

        Run this in a background task to enable share opening.

        args:
            iterations (int): Number of iterations to run the receive loop.
                Note: if -1, run indefinitely

        outputs:
            Return the number of iterations of the receive loop performed.
        """
        always_run = iterations == -1
        count = 0
        while always_run or count < iterations:
            await self._loop_once()
            count += 1

        return count


class SingleShareManager(ShareManager):
    # TODO: take in reconstruction config directly instead of induced_faults
    # TODO: simply take in context metadata instead of context.
    def __init__(self, context: 'Mpc', induce_faults: bool = False):  # noqa: F821
        self._share_id = 0
        self._context = context
        self._induce_faults = induce_faults

        self.n = context.N
        self.t = context.t
        self.field = context.field

        # Store opened shares until ready to reconstruct
        # playerid => { [shareid => Future share] }
        self._share_buffers = tuple(defaultdict(asyncio.Future) for _ in range(self.n))

        # Batch reconstruction is handled slightly differently,
        # We'll create a separate queue for received values
        # { shareid => Queue() }
        self._share_array_buffers = defaultdict(asyncio.Queue)

    def _get_share_id(self) -> int:
        """ Utility function to fetch monotonically increasing integer values.
        This is useful for assigning ids to shares.

        TODO: use defaultdict to give out an id based on share's context's myid.
        """
        share_id = self._share_id
        self._share_id += 1
        return share_id

    @TypeCheck()
    def open_share(self, share: (Share, ShareFuture)) -> asyncio.Future:
        """ Given secret-shared value share, open the value by
        broadcasting our local share, and then receive the likewise
        broadcasted local shares from other nodes, and finally reconstruct
        the secret shared value.

        args:
            share (Share): Secret shared value to open

        outputs:
            Future that resolves to the GFElement value of the share.
        """
        result = asyncio.Future()
        n, t = self.n, self.t
        degree = t if share.t is None else share.t
        share_id = self._get_share_id()

        # Broadcast share
        for dest in range(n):
            value_to_share = share.v

            # Send random data if meant to induce faults
            if self._induce_faults:
                logging.debug("[FAULT][RobustReconstruct] Sending random share.")
                value_to_share = self._context.field.random()

            # 'S' is for single shares
            self._context.send(dest, ('S', share_id, value_to_share))

        # Set up the buffer of received shares
        share_buffer = [self._share_buffers[i][share_id] for i in range(n)]

        point = EvalPoint(self.field, n, use_omega_powers=False)

        # Create polynomial that reconstructs the shared value by evaluating at 0
        reconstruction = asyncio.create_task(robust_reconstruct(
            share_buffer, self.field, n, t, point, degree))

        def _callback(res):
            p, errors = res.result()
            if p is None:
                logging.error(
                    f"Robust reconstruction for share (id: {share_id}) "
                    f"failed with errors: {errors}!")
                result.set_exception(HoneyBadgerMPCError(
                    f"Failed to open share with id {share_id}!"))
            else:
                result.set_result(p(self.field(0)))

        reconstruction.add_done_callback(_callback)

        return result

    @TypeCheck()
    def open_share_array(self, share_array: ShareArray) -> asyncio.Future:
        """ Given array of secret shares, opens them in a batch
        and returns their plaintext values.

        args:
            sharearray (ShareArray): shares to open

        outputs:
            Future, which will resolve to an array of GFElements
        """
        result = asyncio.Future()
        n, t = self.n, self.t
        degree = t if share_array.t is None else share_array.t
        share_id = self._get_share_id()

        _recv = self._share_array_buffers[share_id].get

        def _send(dest, msg):
            (tag, share) = msg
            self._context.send(dest, (tag, share_id, share))

        def _callback(res):
            elements = res.result()
            if elements is None:
                logging.error(
                    f"Batch reconstruction for share_array (id: {share_id}) failed!")
                result.set_exception(HoneyBadgerMPCError("Batch reconstruction failed!"))
            else:
                result.set_result(elements)

        reconstructed = asyncio.create_task(batch_reconstruct(
            [s.v for s in share_array._shares],
            self.field.modulus,
            t,
            n,
            self._context.myid,
            _send,
            _recv,
            config=self._context.config.get(ConfigVars.Reconstruction),
            debug=True,
            degree=degree))

        reconstructed.add_done_callback(_callback)

        return result

    async def _loop_once(self):
        """ Background task to continually receive incoming shares, and
        put the received share in the appropriate buffer. In the case
        of a single share this puts it into self._share_buffers, otherwise,
        it gets enqueued in the appropriate self._share_array_buffers.
        """
        (j, (tag, share_id, share)) = await self._context.recv()

        if tag == 'S':
            assert isinstance(share, GFElement), f"Reconstructed shares must be " \
                f"GFElements, received: {share} of type {type(share)}"

            assert share_id not in self._share_array_buffers, f"Received single "\
                f"share with id {share_id}, but that id is in use for batch " \
                f"reconstruction"

            buf = self._share_buffers[j]
            if buf[share_id].done():
                logging.error(
                    f"Redundant single share received: {j} {(tag, share_id)}")
                raise AssertionError(f"Received redundant single share: {share_id}")

            buf[share_id].set_result(share)
        elif tag in ('R1', 'R2'):
            assert isinstance(share, list), f"Batch-reconstructed shares must be " \
                f"in a list"

            assert all([isinstance(s, (int, GFElement)) for s in share]), f"Batch-" \
                f"reconstructed shares must be a list of GFElements or ints, " \
                f"received {share}."

            assert share_id not in self._share_buffers[j], "Received batch shares " \
                f"with id {share_id}, but that id is in use for single " \
                f"reconstruction"

            self._share_array_buffers[share_id].put_nowait((j, (tag, share)))

        return True

    def force_opening(self) -> bool:
        return True


class BatchedShareManager(ShareManager):
    def __init__(self, contexts: list, induce_faults: bool = False):
        self._contexts = contexts
        self._induce_faults = induce_faults

        self._share_buffers = [defaultdict(asyncio.Future) for _ in range()]

    def add_context(self, context):
        self._contexts.append(context)

    @TypeCheck()
    def open_share(self, share: (Share, ShareFuture)) -> asyncio.Future:
        return asyncio.Future()

    @TypeCheck()
    def open_share_array(self, share_array: ShareArray) -> asyncio.Future:
        return asyncio.Future()

    async def _loop_once(self):
        pass

    def force_opening(self) -> bool:
        return True
