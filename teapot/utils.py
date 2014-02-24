"""
General-purpose utilities
=========================

This collects and provides some general-purpose utilities. Some of these may be
imported from other packages, if available. Otherwise, drop-in replacements are
provided if possible and reasonable.

Drop-in replacements are provided transparently, but may have worse performance.

"""

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
