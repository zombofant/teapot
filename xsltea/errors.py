"""
``xsltea`` errors
#################

.. autoclass:: TemplateEvaluationError

"""

class TemplateEvaluationError(ValueError):
    """
    This error is raised by template processors whenever an error occurs during
    evalation of the template (i.e. during the call to
    :meth:`~xsltea.processors.TemplateProcessor.process``, _not_ during
    initaliazation).

    The context of this exception should be set to the original exception to
    allow for introspection and detailed tracebacks.
    """
