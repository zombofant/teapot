"""
Template engine interface
#########################

This module provides an abstract interface to use templating engines with
teapot. For each templating engine, one should subclass :class:`TemplateEngine`
to wrap the required methods.

.. autoclass:: Engine
   :members:

Template sources
================

.. autoclass:: Source
   :members:

.. autoclass:: FileSystemSource
   :members:

"""

import abc
import logging
import os

logger = logging.getLogger(__name__)

class Engine(metaclass=abc.ABCMeta):
    def __init__(self, *sources, **kwargs):
        super().__init__(**kwargs)
        self._sources = sources

    @staticmethod
    def create_decorator(result_processor):
        """
        Create a decorator, which, when applied to a *callable*, produces
        a function which will first call the *callable* and then pass the result
        to the given *result_processor*. The result of that call is returned.
        """
        def decorator(callable):
            def templated_callable(*args, **kwargs):
                return result_processor(callable(*args, **kwargs))
            templated_callable.__name__ = callable.__name__
            return templated_callable
        return decorator

    def open_template(self, name, **kwargs):
        """
        Iterate over all sources passed at construction time and try to open the
        given template *name*. The *kwargs* are passed to the
        :meth:`~Source.open_template` method of the source.

        Returns a file-like providing read access to the given template or
        raises a :class:`FileNotFoundError`.
        """
        for source in self._sources:
            try:
                return source.open(name, **kwargs)
            except FileNotFoundError as err:
                continue
            except OSError as err:
                logger.warn("while searching for template %s: %s",
                            name, err)
                continue
        else:
            raise FileNotFoundError(name)

    @abc.abstractmethod
    def use_template(self):
        """
        This is supposed to work as a decorator. The arguments are to be defined
        by the engine implementation, however, for consistency, the decorators
        name is defined in this class.
        """

class Source:
    @abc.abstractmethod
    def open(self, name, binary=True, encoding=None):
        """
        Open the template with the given *name* and return a file-like object
        providing read access to the template.

        Subclasses must support an optional keyword-argument called `binary`. If
        it is supplied and evaluates to :data:`True`, the returned file-like
        must be opened in binary mode. If it is supplied and evaluates to
        :data:`False`, the returned file-like must be opened in text mode. The
        default is up to the subclass.

        For text-mode opening, the optional keyword argument *encoding* may be
        used if it is present and the default of the source is binary.

        If the template cannot be found, :class:`FileNotFoundError` should be
        raised. If the template cannot be opened for any other reason, an
        appropriate subclass of :class:`OSError` should be raised.

        Must be implemented by subclasses.
        """

class FileSystemSource(Source):
    def __init__(self, search_path, **kwargs):
        super().__init__(**kwargs)
        self._search_path = search_path

    def open(self, name, binary=True, encoding=None):
        """
        Look for a file with the given *name* in the search path supplied upon
        constructing.

        :func:`open` the file with ``"rb"``, if *binary* is :data:`True`, and
        with ``"r"`` and the given *encoding* otherwise.

        Return the opened file.
        """
        return open(os.path.join(self._search_path, name),
                    "rb" if binary else "r",
                    encoding=encoding)
