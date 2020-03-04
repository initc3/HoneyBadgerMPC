"""IMPORTANT ACKNOWLEDGEMENT!

The code was taken as is or based from:

* https://github.com/ethereum/py-evm/blob/master/eth/abc.py
* https://github.com/ethereum/py-evm/tree/master/eth/db/backends

If not from the above somewhere else under:

* https://github.com/ethereum/py-evm/blob/master/eth/
"""
import logging
import pickle
import warnings
from abc import ABC, abstractmethod
from contextlib import contextmanager
from pathlib import Path
from typing import ContextManager, Dict, Iterator, TYPE_CHECKING


def serialize(obj):
    return pickle.dumps(obj)


def deserialize(bytes_object):
    return pickle.loads(bytes_object)


# TODO: drop once https://github.com/cython/cython/issues/1720 is resolved
@contextmanager
def catch_and_ignore_import_warning() -> Iterator[None]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=ImportWarning)
        yield


if TYPE_CHECKING:
    with catch_and_ignore_import_warning():
        import plyvel  # noqa: F401


class ValidationError(Exception):
    """Raise when a validation error occurs."""


class DatabaseAPI(ABC):
    @abstractmethod
    def set(self, key, value):
        """Assign the ``value`` to the ``key``."""

    @abstractmethod
    def exists(self, key):
        """Return ``True`` if the ``key`` exists in the database,
        otherwise ``False``.
        """

    @abstractmethod
    def delete(self, key):
        """Delete the given ``key`` from the database."""


class BaseDB(DatabaseAPI):
    """
    This is an abstract key/value lookup with all :class:`bytes` values,
    with some convenience methods for databases. As much as possible,
    you can use a DB as if it were a :class:`dict`.
    Notable exceptions are that you cannot iterate through all values or get the length.
    (Unless a subclass explicitly enables it).
    All subclasses must implement these methods:
    __init__, __getitem__, __setitem__, __delitem__
    Subclasses may optionally implement an _exists method
    that is type-checked for key and value.
    """

    def set(self, key, value):
        self[key] = value

    def exists(self, key):
        return self.__contains__(key)

    def __contains__(self, key):
        if hasattr(self, "_exists"):
            # Classes which inherit this class would have `_exists` attr
            return self._exists(key)
        else:
            return super().__contains__(key)

    def delete(self, key):
        try:
            del self[key]
        except KeyError:
            pass

    def __iter__(self):
        raise NotImplementedError("By default, DB classes cannot be iterated.")

    def __len__(self):
        raise NotImplementedError(
            "By default, DB classes cannot return the total number of keys."
        )


class AtomicWriteBatchAPI(DatabaseAPI):
    """
    The readable/writeable object returned by an atomic database when we start building
    a batch of writes to commit.
    Reads to this database will observe writes written during batching,
    but the writes will not actually persist until this object is committed.
    """


class AtomicDatabaseAPI(DatabaseAPI):
    """
    Like ``BatchDB``, but immediately write out changes if they are
    not in an ``atomic_batch()`` context.
    """

    @abstractmethod
    def atomic_batch(self) -> ContextManager[AtomicWriteBatchAPI]:
        """
        Return a :class:`~typing.ContextManager` to write an atomic batch to the database.
        """


class BaseAtomicDB(BaseDB, AtomicDatabaseAPI):
    """
    This is an abstract key/value lookup that permits batching of updates, such that the batch of
    changes are atomically saved. They are either all saved, or none are.
    Writes to the database are immediately saved, unless they are explicitly batched
    in a context, like this:
    ::
        atomic_db = AtomicDB()
        with atomic_db.atomic_batch() as db:
            # changes are not immediately saved to the db, inside this context
            db[key] = val
            # changes are still locally visible even though they are not yet committed to the db
            assert db[key] == val
            if some_bad_condition:
                raise Exception("something went wrong, erase all the pending changes")
            db[key2] = val2
            # when exiting the context, the values are saved either key and key2 will both be saved,
            # or neither will
    """


class MemoryDB(BaseDB):
    kv_store: Dict[bytes, bytes] = None

    def __init__(self, kv_store: Dict[bytes, bytes] = None) -> None:
        if kv_store is None:
            self.kv_store = {}
        else:
            self.kv_store = kv_store

    def __getitem__(self, key: bytes) -> bytes:
        return self.kv_store[key]

    def __setitem__(self, key: bytes, value: bytes) -> None:
        self.kv_store[key] = value

    def _exists(self, key: bytes) -> bool:
        return key in self.kv_store

    def __delitem__(self, key: bytes) -> None:
        del self.kv_store[key]

    def __iter__(self) -> Iterator[bytes]:
        return iter(self.kv_store)

    def __len__(self) -> int:
        return len(self.kv_store)

    def __repr__(self) -> str:
        return f"MemoryDB({self.kv_store!r})"


class LevelDB(BaseAtomicDB):
    logger = logging.getLogger("apps.db.LevelDB")

    # Creates db as a class variable to avoid level db lock error
    def __init__(self, db_path: Path = None, max_open_files: int = None) -> None:
        if not db_path:
            raise TypeError("Please specifiy a valid path for your database.")
        try:
            with catch_and_ignore_import_warning():
                import plyvel  # noqa: F811
        except ImportError:
            raise ImportError(
                "LevelDB requires the plyvel library which is not available for import."
            )
        self.db_path = db_path
        self.db = plyvel.DB(
            str(db_path),
            create_if_missing=True,
            error_if_exists=False,
            max_open_files=max_open_files,
        )

    def __getitem__(self, key: bytes) -> bytes:
        v = self.db.get(key)
        if v is None:
            raise KeyError(key)
        return v

    def __setitem__(self, key: bytes, value: bytes) -> None:
        self.db.put(key, value)

    def _exists(self, key: bytes) -> bool:
        return self.db.get(key) is not None

    def __delitem__(self, key: bytes) -> None:
        if self.db.get(key) is None:
            raise KeyError(key)
        self.db.delete(key)

    @contextmanager
    def atomic_batch(self) -> Iterator[AtomicWriteBatchAPI]:
        # with self.db.write_batch(transaction=True) as atomic_batch:
        #    readable_batch = LevelDBWriteBatch(self, atomic_batch)
        #    try:
        #        yield readable_batch
        #    finally:
        #        readable_batch.decommission()
        raise NotImplementedError


# class LevelDBWriteBatch(BaseDB, AtomicWriteBatchAPI):
#    """
#    A native leveldb write batch does not permit reads on the in-progress data.
#    This class fills that gap, by tracking the in-progress diff, and adding
#    a read interface.
#    """
#
#    logger = logging.getLogger("eth.db.backends.LevelDBWriteBatch")
#
#    def __init__(
#        self, original_read_db: DatabaseAPI, write_batch: "plyvel.WriteBatch"
#    ) -> None:
#        self._original_read_db = original_read_db
#        self._write_batch = write_batch
#        # keep track of the temporary changes made
#        self._track_diff = DBDiffTracker()
#
#    def __getitem__(self, key: bytes) -> bytes:
#        if self._track_diff is None:
#            raise ValidationError("Cannot get data from a write batch, out of context")
#
#        try:
#            changed_value = self._track_diff[key]
#        except DiffMissingError as missing:
#            if missing.is_deleted:
#                raise KeyError(key)
#            else:
#                return self._original_read_db[key]
#        else:
#            return changed_value
#
#    def __setitem__(self, key: bytes, value: bytes) -> None:
#        if self._track_diff is None:
#            raise ValidationError("Cannot set data from a write batch, out of context")
#
#        self._write_batch.put(key, value)
#        self._track_diff[key] = value
#
#    def _exists(self, key: bytes) -> bool:
#        if self._track_diff is None:
#            raise ValidationError(
#                "Cannot test data existance from a write batch, out of context"
#            )
#
#        try:
#            self._track_diff[key]
#        except DiffMissingError as missing:
#            if missing.is_deleted:
#                return False
#            else:
#                return key in self._original_read_db
#        else:
#            return True
#
#    def __delitem__(self, key: bytes) -> None:
#        if self._track_diff is None:
#            raise ValidationError(
#                "Cannot delete data from a write batch, out of context"
#            )
#
#        self._write_batch.delete(key)
#        del self._track_diff[key]
#
#    def decommission(self) -> None:
#        """
#        Prevent any further actions to be taken on this write batch, called after leaving context
#        """
#        self._track_diff = None
