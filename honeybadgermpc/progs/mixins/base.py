from abc import ABC, abstractmethod
from honeybadgermpc.utils.typecheck import TypeCheck


class MixinBase(ABC):
    """Abstract base class for all Mixin objects
    These will work like drag-and-drop functors to load in some mpc applications
    """

    @abstractmethod
    def __call__(self, *args, **kwargs):
        """Subclasses of MixinBase most override this method, as this is
        the way to call the method contained by the abstract method.
        """
        return NotImplementedError

    @property
    @classmethod
    @abstractmethod
    def name(cls):
        """Subclasses of MixinBase must define the NAME value, as this is
        the way to fetch the name of the mixin
        """
        return NotImplementedError


class AsyncMixin(MixinBase):
    """Abstract base class representing a mixin with an async
    method to call
    """

    from honeybadgermpc.mpc import Mpc

    dependencies = []

    @staticmethod
    @abstractmethod
    async def _prog(self):
        return NotImplementedError

    @classmethod
    @TypeCheck()
    async def __call__(cls, context: Mpc, *args, **kwargs):
        for dependency in cls.dependencies:
            if dependency not in context.config:
                return NotImplemented

        return await cls._prog(context, *args, **kwargs)
