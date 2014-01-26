"""
Template engine interface
#########################

This module provides an abstract interface to use templating engines with
teapot. For each templating engine, one should subclass :class:`TemplateEngine`
to wrap the required methods.

.. autoclass:: TemplateEngine
"""

import abc

class Engine(metaclass=abc.ABCMeta):
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

    @abc.abstractmethod
    def use_template(self):
        """
        This is supposed to work as a decorator. The arguments are to be defined
        by the engine implementation, however, for consistency, the decorators
        name is defined in this class.
        """

class FileBasedEngine(Engine):
    def __init__(self, *search_path, **kwargs):
        super().__init__(**kwargs)
        self.search_path = search_path

    def open_template_file(self, name, openmode="rb", **kwargs):
        for path in self.search_path:
            try:
                f = open(os.path.join(path, name), openmode, **kwargs)
            except FileNotFoundError as err:
                continue
            except OSError as err:
                logging.warn("while looking for %s: %s", name, err)
                continue

            return f
        else:
            raise FileNotFoundError(name)
