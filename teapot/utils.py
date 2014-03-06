"""
General-purpose utilities
=========================

This collects and provides some general-purpose utilities. Some of these may be
imported from other packages, if available. Otherwise, drop-in replacements are
provided if possible and reasonable.

Drop-in replacements are provided transparently, but may have worse performance.

"""

import abc
import collections
import collections.abc
import logging

logger = logging.getLogger(__name__)

class _sortedlist(collections.abc.MutableSet, collections.abc.Sequence):
    def __init__(self, iterable=(), key=None):
        self._iterable = list(iterable)
        self._key = key
        self._iterable.sort(key=self._key)

    def __contains__(self, other):
        return other in self._iterable

    def __getitem__(self, index):
        return self._iterable[index]

    def __iter__(self):
        return iter(self._iterable)

    def __len__(self):
        return len(self._iterable)

    def __repr__(self):
        return repr(self._iterable)

    def __str__(self):
        return str(self._iterable)

    def add(self, value):
        self._iterable.append(value)
        self._iterable.sort(key=self._key)

    def discard(self, value):
        try:
            self.remove(value)
        except ValueError as err:
            pass

    def index(self, value):
        return self._iterable.index(value)

    def remove(self, value):
        return self._iterable.remove(value)

try:
    from blist import sortedlist
except ImportError as err:
    sortedlist = _sortedlist
    logger.error("blist failed to import (%s): using fallbacks which are slooow",
                 err)

class InstrumentedList(collections.abc.MutableSequence,
                       metaclass=abc.ABCMeta):
    def __init__(self, sequence=None):
        self._storage = list()
        if sequence is not None:
            self.extend(sequence)

    @abc.abstractmethod
    def _acquire_item(self, item):
        pass

    def _acquire_items(self, sequence):
        collections.deque(map(self._acquire_item, sequence), 0)

    @abc.abstractmethod
    def _release_item(self, item):
        pass

    def _release_items(self, sequence):
        collections.deque(map(self._release_item, sequence), 0)


    def __delitem__(self, index):
        if isinstance(index, slice):
            self._release_items(self._storage[index])
        else:
            self._release_item(self._storage[index])
        try:
            del self._storage[index]
        except:
            if isinstance(index, slice):
                self._acquire_items(self._storage[index])
            else:
                self._acquire_item(self._storage[index])

    def __getitem__(self, index):
        return self._storage[index]

    def __iter__(self):
        return iter(self._storage)

    def __len__(self):
        return len(self._storage)

    def __reversed__(self):
        return iter(reversed(self._storage))

    def __setitem__(self, index, obj):
        if isinstance(index, slice):
            obj = list(obj)  # we must evaluate it here once
            self._acquire_items(obj)
        else:
            self._acquire_item(obj)

        try:
            old = self._storage[index]
            if isinstance(index, slice):
                self._release_items(old)
            else:
                self._release_item(old)
            self._storage[index] = obj
        except:
            if isinstance(index, slice):
                self._release_items(obj)
            else:
                self._release_item(obj)
            raise

    def append(self, obj):
        self._acquire_item(obj)
        try:
            self._storage.append(obj)
        except:
            self._release_item(obj)
            raise

    def insert(self, index, obj):
        self._acquire_item(obj)
        try:
            self._storage.insert(index, obj)
        except:
            self._release_item(obj)
            raise

    def reverse(self):
        self._storage.reverse()

    def pop(self, index=-1):
        obj = self._storage.pop(index)
        self._release_item(obj)
        return obj

    def __repr__(self):
        return "{!s}({!r})".format(type(self).__qualname__,
                                   self._storage)

    def __str__(self):
        return str(self._storage)
