"""
``xsltea`` — XML+XSLT based templating engine
#############################################

*xsltea* is a templating engine based on XML and XSL transformations. It
provides a pluggable mechanism to interpret XML documents and postprocess them,
based on templating arguments.

*xsltea* uses and requires lxml.

.. automodule:: xsltea.pipeline

.. py:currentmodule:: xsltea

.. autofunction:: make_pipeline

The following modules and classes provide extension points to xsltea.

.. automodule:: xsltea.template

.. automodule:: xsltea.processor

.. automodule:: xsltea.safe

.. automodule:: xsltea.i18n

.. automodule:: xsltea.exec

.. automodule:: xsltea.namespaces

.. automodule:: xsltea.errors

"""

try:
    import lxml.etree as etree
except ImportError as err:
    logger.error("xsltea fails to load: lxml is not available")
    raise

from .template import Template, XMLTemplateLoader
from .errors import TemplateEvaluationError
from .exec import ExecProcessor
from .forms import FormProcessor
from .safe import ForeachProcessor, IncludeProcessor, SafetyLevel, \
    FunctionProcessor, BranchingProcessor
from .pipeline import Pipeline, XHTMLPipeline, XMLPipeline, TransformLoader

def make_pipeline(
        *sources,
        loader=XMLTemplateLoader,
        output_format=XHTMLPipeline,
        **kwargs):
    """
    Create a new pipeline based on the given *output_format* pipeline. It will
    use the given *loader* class for loading templates from any of the given
    *sources* (see :class:`teapot.templating.Source`).

    Returns a new pipeline object with an associated loader.
    """

    pipeline = output_format(**kwargs)
    pipeline.loader = loader(*sources)

    return pipeline
