import asyncio
from abc import ABC, abstractmethod
from honeybadgermpc.field import GFElement
from honeybadgermpc.progs.mixins.constants import MixinConstants
from honeybadgermpc.utils import type_check


class GFElementFuture(ABC, asyncio.Future):
    @property
    @classmethod
    @abstractmethod
    def context(cls):
        return NotImplementedError

    @type_check((int, GFElement, 'GFElementFuture'))
    def __binop_field(self, other, op):
        assert callable(op)

        if isinstance(other, int):
            other = self.context.field(other)

        res = GFElementFuture()

        if isinstance(other, GFElementFuture):
            asyncio.gather(self, other).add_done_callback(
                lambda _: res.set_result(op(self.result(), other.result())))
        else:
            self.add_done_callback(
                lambda _: res.set_result(op(self.result(), other)))

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
                opening = asyncio.ensure_future(
                    self.context.open_share(self.context.Share(v.result())))
                opening.add_done_callback(lambda f: res.set_result(f.result()))

            self.v.add_done_callback(cb1)
        else:
            # Wraps the open_share coroutine in a Task
            opening = asyncio.ensure_future(self.context.open_share(self))

            # Make res resolve to the opened value
            opening.add_done_callback(lambda f: res.set_result(f.result()))

        return res

    # Linear combinations of shares can be computed directly
    def __add__(self, other):
        if isinstance(other, GFElement):
            return self.context.Share(self.v + other, self.t)
        elif not isinstance(other, Share):
            return NotImplemented
        elif self.t != other.t:
            raise ValueError(
                f"Shares can't be added to other shares with differing t \
                    values ({self.t} {other.t})")

        return self.context.Share(self.v + other.v, self.t)

    __radd__ = __add__

    def __neg__(self):
        return self.context.Share(-self.v), self.t

    def __sub__(self, other):
        if isinstance(other, GFElement):
            return self.context.Share(self.v - other, self.t)
        elif not isinstance(other, Share):
            return NotImplemented
        elif self.t != other.t:
            raise ValueError(
                f"Shares must have same t value to subtract: \
                    ({self.t} {other.t})")

        return self.context.Share(self.v - other.v, self.t)

    def __rsub__(self, other):
        if isinstance(other, GFElement):
            return self.context.Share(-self.v + other, self.t)

        return NotImplemented

    def __mul__(self, other):
        if isinstance(other, (int, GFElement)):
            return self.context.Share(self.v * other, self.t)
        elif not isinstance(other, Share):
            return NotImplemented
        elif self.t != other.t:
            raise ValueError(
                f"Shares with differing t values cannot be multiplied \
                    ({self.t} {other.t})")

        res = self.context.ShareFuture()

        product = self.context.call_mixin(MixinConstants.MultiplyShare, self, other)
        product.add_done_callback(lambda p: res.set_result(p.result()))

        return res

    def __rmul__(self, other):
        if isinstance(other, (int, GFElement)):
            return self.context.Share(self.v * other, self.t)

        return NotImplemented

    def __div__(self, other):
        if not isinstance(other, Share):
            return NotImplemented
        elif self.t != other.t:
            raise ValueError(
                f"Cannot divide shares with differing t values ({self.t} {other.t})")

        res = self.context.ShareFuture()

        result = self.context.call_mixin(MixinConstants.DivideShare, self, other)
        result.add_done_callback(lambda r: res.set_result(r.result()))

        return res

    __truediv__ = __floordiv__ = __div__

    def __eq__(self, other):
        if not isinstance(other, self.context.Share):
            return NotImplemented

        res = self.context.ShareFuture()

        eq = self.context.call_mixin(MixinConstants.ShareEquality, self, other)
        eq.add_done_callback(lambda e: res.set_result(e.result()))

        return res

    def __str__(self):
        return '{%d}' % (self.v)


class ShareArray(ABC):
    @property
    @classmethod
    @abstractmethod
    def context(cls):
        return NotImplementedError

    def __init__(self, values, t=None):
        # Initialized with a list of share objects
        self.t = self.context.t if t is None else t

        for i, value in enumerate(values):
            if isinstance(value, (int, GFElement)):
                values[i] = self.context.Share(value, self.t)

            assert isinstance(values[i], Share)

        self._shares = values

    def open(self, use_powers_of_omega=True):
        # TODO: make a list of GFElementFutures?
        # res = GFElementFuture()
        res = asyncio.Future()

        opening = asyncio.create_task(
            self.context.open_share_array(self, use_powers_of_omega))
        opening.add_done_callback(lambda f: res.set_result(f.result()))

        return res

    def __len__(self):
        return len(self._shares)

    def __add__(self, other):
        if isinstance(other, list):
            other = self.context.ShareArray(other, self.t)
        elif not isinstance(other, self.context.ShareArray):
            return NotImplemented

        assert self.t == other.t
        assert len(self) == len(other)

        result = [a+b for (a, b) in zip(self._shares, other._shares)]
        return self.context.ShareArray(result, self.t)

    def __sub__(self, other):
        if isinstance(other, list):
            other = self.context.ShareArray(other, self.t)
        elif not isinstance(other, self.context.ShareArray):
            return NotImplemented

        assert self.t == other.t
        assert len(self) == len(other)

        result = [a-b for (a, b) in zip(self._shares, other._shares)]
        return self.context.ShareArray(result, self.t)

    def __mul__(self, other):
        return self.context.call_mixin(MixinConstants.MultiplyShareArray, self, other)

    def __div__(self, other):
        return self.context.call_mixin(MixinConstants.DivideShareArray, self, other)

    __truediv__ = __floordiv__ = __div__


class ShareFuture(ABC, asyncio.Future):
    @property
    @classmethod
    @abstractmethod
    def context(cls):
        return NotImplementedError

    @type_check((int,
                 GFElement,
                 'self.context.Share',
                 'self.context.ShareFuture',
                 'self.context.GFElementFuture'))
    def __binop_share(self, other, op):
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

        if isinstance(other, (ShareFuture, GFElementFuture)):
            asyncio.gather(self, other).add_done_callback(cb)
        elif isinstance(other, (Share, GFElement)):
            self.add_done_callback(cb)
        else:
            return NotImplementedError

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
            lambda _: self.result().open().add_done_callback(
                lambda sh: res.set_result(sh.result())))

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
