from __future__ import annotations  # noqa: F407
import asyncio
from abc import ABC, abstractmethod
from honeybadgermpc.field import GFElement
from honeybadgermpc.progs.mixins.constants import MixinConstants
from honeybadgermpc.utils.typecheck import TypeCheck
from typing import Callable


class GFElementFuture(ABC, asyncio.Future):
    @property
    @classmethod
    @abstractmethod
    def context(cls):
        return NotImplementedError

    @TypeCheck(arithmetic=True)
    def __binop_field(self, other: (int, GFElement, GFElementFuture), op: Callable):
        if isinstance(other, int):
            other = self.context.field(other)

        res = GFElementFuture()

        if isinstance(other, GFElementFuture):
            asyncio.gather(self, other).add_done_callback(
                lambda _: res.set_result(op(self.result(), other.result()))
            )
        else:
            self.add_done_callback(lambda _: res.set_result(op(self.result(), other)))

        return res

    def __add__(self, other):
        return self.__binop_field(other, lambda a, b: a + b)

    __radd__ = __add__

    def __sub__(self, other):
        return self.__binop_field(other, lambda a, b: a - b)

    def __rsub__(self, other):
        return self.__binop_field(other, lambda a, b: -a + b)

    def __mul__(self, other):
        return self.__binop_field(other, lambda a, b: a * b)


class Share(ABC):
    @property
    @classmethod
    @abstractmethod
    def context(cls):
        return NotImplementedError

    def __init__(self, v, t=None):
        if type(v) is int:
            v = self.context.field(v)
        assert isinstance(v, (GFElement, GFElementFuture))

        self.v = v
        self.t = self.context.t if t is None else t

    def open(self):
        res = self.context.GFElementFuture()

        if isinstance(self.v, asyncio.Future):

            def cb1(v):
                # Future that will resolve to the opened share
                opening = self.context.open_share(self.context.Share(v.result()))
                opening.add_done_callback(lambda f: res.set_result(f.result()))

            self.v.add_done_callback(cb1)
        else:
            # Future that will resolve to the opened share
            opening = self.context.open_share(self)

            # Make res resolve to the opened value
            opening.add_done_callback(lambda f: res.set_result(f.result()))
        return res

    # Linear combinations of shares can be computed directly
    @TypeCheck(arithmetic=True)
    def __add__(self, other: (GFElement, Share)):
        if isinstance(other, GFElement):
            return self.context.Share(self.v + other, self.t)
        elif self.t != other.t:
            raise ValueError(
                f"Shares can't be added to other shares with differing t \
                    values ({self.t} {other.t})"
            )

        return self.context.Share(self.v + other.v, self.t)

    __radd__ = __add__

    def __neg__(self):
        return self.context.Share(-self.v), self.t

    @TypeCheck(arithmetic=True)
    def __sub__(self, other: (GFElement, Share)):
        if isinstance(other, GFElement):
            return self.context.Share(self.v - other, self.t)
        elif self.t != other.t:
            raise ValueError(
                f"Shares must have same t value to subtract: \
                    ({self.t} {other.t})"
            )

        return self.context.Share(self.v - other.v, self.t)

    @TypeCheck(arithmetic=True)
    def __rsub__(self, other: GFElement):
        return self.context.Share(-self.v + other, self.t)

    @TypeCheck(arithmetic=True)
    def __mul__(self, other: (int, GFElement, Share)):
        if isinstance(other, (int, GFElement)):
            return self.context.Share(self.v * other, self.t)
        elif self.t != other.t:
            raise ValueError(
                f"Shares with differing t values cannot be multiplied \
                    ({self.t} {other.t})"
            )

        res = self.context.ShareFuture()

        product = self.context.call_mixin(MixinConstants.MultiplyShare, self, other)
        product.add_done_callback(lambda p: res.set_result(p.result()))

        return res

    @TypeCheck(arithmetic=True)
    def __rmul__(self, other: (int, GFElement)):
        return self.context.Share(self.v * other, self.t)

    @TypeCheck(arithmetic=True)
    def __div__(self, other: Share):
        if self.t != other.t:
            raise ValueError(
                f"Cannot divide shares with differing t values ({self.t} {other.t})"
            )

        res = self.context.ShareFuture()

        result = self.context.call_mixin(MixinConstants.DivideShare, self, other)
        result.add_done_callback(lambda r: res.set_result(r.result()))

        return res

    __truediv__ = __floordiv__ = __div__

    @TypeCheck(arithmetic=True)
    def __eq__(self, other: Share):
        res = self.context.ShareFuture()

        eq = self.context.call_mixin(MixinConstants.ShareEquality, self, other)
        eq.add_done_callback(lambda e: res.set_result(e.result()))

        return res

    @TypeCheck(arithmetic=True)
    def __lt__(self, other: Share):
        res = self.context.ShareFuture()

        lt = self.context.call_mixin(MixinConstants.ShareLessThan, self, other)
        lt.add_done_callback(lambda r: res.set_result(r.result()))

        return res

    def __str__(self):
        return "{%d}" % (self.v)


class ShareArray(ABC):
    @property
    @classmethod
    @abstractmethod
    def context(cls):
        return NotImplementedError

    def __init__(self, values, t=None):
        # Initialized with a list of share objects
        self.t = self.context.t if t is None else t
        values = list(values)

        for i, value in enumerate(values):
            if isinstance(value, (int, GFElement)):
                values[i] = self.context.Share(value, self.t)

            assert isinstance(values[i], Share)

        self._shares = values

    def open(self):
        # TODO: make a list of GFElementFutures?
        return self.context.open_share_array(self)

    def __len__(self):
        return len(self._shares)

    @TypeCheck(arithmetic=True)
    def __add__(self, other: (ShareArray, list)):
        if isinstance(other, list):
            other = self.context.ShareArray(other, self.t)

        assert self.t == other.t
        assert len(self) == len(other)

        result = [a + b for (a, b) in zip(self._shares, other._shares)]
        return self.context.ShareArray(result, self.t)

    @TypeCheck(arithmetic=True)
    def __sub__(self, other: (ShareArray, list)):
        if isinstance(other, list):
            other = self.context.ShareArray(other, self.t)

        assert self.t == other.t
        assert len(self) == len(other)

        result = [a - b for (a, b) in zip(self._shares, other._shares)]
        return self.context.ShareArray(result, self.t)

    @TypeCheck(arithmetic=True)
    def __mul__(self, other: ShareArray):
        return self.context.call_mixin(MixinConstants.MultiplyShareArray, self, other)

    @TypeCheck(arithmetic=True)
    def __div__(self, other: ShareArray):
        return self.context.call_mixin(MixinConstants.DivideShareArray, self, other)

    __truediv__ = __floordiv__ = __div__

    @TypeCheck()
    async def _tree_fold(self, op: Callable):
        """ Apply a provided operation in a 'tree'-like fashion--
        Instead of folding sequentially across the shares of the array which
        creates a linked-list like chain of operations as shares resolve, this
        applies them in a tree-like fashion, which involves only log(n) levels of
        application. This requires the array to be non-empty.

        example:
            A regular reduce would proceed as follows:
                sum([1,2,3,4,5]) => 1 + 2 + 3 + 4 + 5
            Instead, this will proceed as follows:
                sum([1,2,3,4,5]) => ((1+2) + (3+4)) + 5

        args:
            op (function): A binary function that takes two shares and returns a share
                or sharefuture. This is required to be commutative. For this to be
                useful, it should also be non-strict / lazy (i.e. the result arrives
                asynchronously)

        returns:
            A Share or ShareFuture representing the iterated binary operation of op on
            the shares of this array
        """
        shares = self._shares
        assert len(shares) > 0

        while len(shares) > 1:
            left, right = shares[::2], shares[1::2]
            extra = None
            if len(left) > len(right):
                extra = left[-1]
                left = left[:-1]

            results = (
                await op(self.context.ShareArray(left), self.context.ShareArray(right))
            )._shares

            if extra is not None:
                results.append(extra)

            shares = results

        return shares[0]

    async def multiplicative_product(self):
        """ Compute the product sum of values in this array such that this takes log(n)
        rounds
        """
        if len(self._shares) == 0:
            return self.context.Share(1)

        return await self._tree_fold(ShareArray.__mul__)


class ShareFuture(ABC, asyncio.Future):
    @property
    @classmethod
    @abstractmethod
    def context(cls):
        return NotImplementedError

    @TypeCheck(arithmetic=True)
    def __binop_share(
        self, other: (int, GFElement, Share, ShareFuture, GFElementFuture), op: Callable
    ):
        """Stacks the application of a function to the resolved value
        of this future with another value, which may or may not be a
        future as well.
        """

        if isinstance(other, int):
            other = self.context.field(other)

        res = self.context.ShareFuture()

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

        if isinstance(other, asyncio.Future):
            asyncio.gather(self, other).add_done_callback(cb)
        else:
            self.add_done_callback(cb)

        return res

    def open(self):
        """Returns a future that resolves to the opened
        value of this share
        """
        res = self.context.GFElementFuture()

        # Adds 2 layers of callbacks-- one to open the share when
        # it resolves, and the next to set the value of res when opening
        # resolves
        self.add_done_callback(
            lambda _: self.result()
            .open()
            .add_done_callback(lambda sh: res.set_result(sh.result()))
        )

        return res

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

    def __eq__(self, other):
        return self.__binop_share(other, lambda a, b: a == b)

    def __lt__(self, other):
        return self.__binop_share(other, lambda a, b: a < b)

    __hash__ = asyncio.Future.__hash__
