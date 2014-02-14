"""
``xsltea`` — XML+XSLT based templating engine
#############################################

*xsltea* is a templating engine based on XML and XSL transformations. It
provides a pluggable mechanism to interpret XML documents and postprocess them,
based on templating arguments.

*xsltea* uses and requires lxml.

The engine is used as an anchor for ``xsltea`` in your application. Each engine
has its own set of options, no global variables are used. The engine also
provides the decorator to use to decorate your controller methods for using the
templating engine.

.. autoclass:: Engine
   :members:

The following classes deal with templates and the lxml ElementTrees used in
these:

.. autoclass:: Template

The following modules and classes provide extension points to xsltea.

.. autoclass:: TemplateTree

.. autoclass:: EvaluationTree
   :members:

.. automodule:: xsltea.processor

.. automodule:: xsltea.safe

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
from .transform import Pipeline, XHTMLPipeline, XMLPipeline, TransformLoader

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
