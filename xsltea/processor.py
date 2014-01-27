"""
Processor plugins
#################

Templates are processed using :class:`TemplateProcessor` instances. These
interpret the template contents and can be used to implement arbitrary
extensions.

.. autoclass:: TemplateProcessor
   :members:

"""

import abc

class TemplateProcessor:
    """
    This is a base for namespace processors. Each namespace processor deals with
    XML elements and attributes from a specific namespace (or set of
    namespaces).

    It takes care of preparing and executing the namespaces effects in the
    template based on the arguments passed from the function invoking the
    template.

    Upon construction, the *template* is passed to the namespace processor. It
    is expected that any processing which can be done once per template is done
    during construction of the processor.

    The final processing of the template using the parameters from the template
    invocation is done in the :meth:`process` method.
    """

    def __init__(self, template, **kwargs):
        super().__init__(**kwargs)
        self._template = template

    @abc.abstractmethod
    def process(self, arguments):
        """
        Execute the final template processing using the *arguments* dictionary
        returned by the function invoking the template.
        """
