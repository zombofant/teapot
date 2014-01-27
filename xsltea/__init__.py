"""
``xsltea`` — XML+XSLT based templating engine
#############################################

*xsltea* is a templating engine based on XML and XSL transformations. It
provides a pluggable mechanism to interpret XML documents and postprocess them,
based on templating arguments.

*xsltea* uses and requires lxml.

.. autoclass:: Engine
   :members:

.. autoclass:: Template
   :members:

.. automodule:: xsltea.processor

.. automodule:: xsltea.exec

.. automodule:: xsltea.utils

.. automodule:: xsltea.namespaces

.. automodule:: xsltea.errors

"""

import copy
import logging
import os

logger = logging.getLogger(__name__)

try:
    import lxml.etree as etree
except ImportError as err:
    logger.error("xsltea fails to load: lxml is not available")
    raise

import teapot.templating

from .namespaces import xml
from .processor import TemplateProcessor
from .exec import ExecProcessor
from .utils import *
from .errors import TemplateEvaluationError

xml_parser = etree.XMLParser(ns_clean=True,
                             remove_blank_text=True,
                             remove_comments=True)

class Template:
    """
    Wrap an lxml ``ElementTree`` *tree* as a template. The *tree* may be heavily
    modified during processing, thus, if you need the tree also for other
    purposes make sure to pass a deep copy.

    For debugging output, the *name* of the template is also used; if the
    template does not come from a file, use another distinct identifier, such as
    ``"<string>"``.

    .. attribute:: tree

       The ``ElementTree`` which belongs to the template.

    .. attribute:: name

       Name of the source from which the template was created. This can be any
       opaque identifier. It should not be relied on any semantics of this.

    """

    @classmethod
    def from_buffer(cls, buf, name, **kwargs):
        """
        Load a template from the given buffer or string *buf* (lxml will take
        care of converting a buffer to a string using the XML header).

        The *kwargs* are forwarded to the constructor.
        """
        return cls(etree.fromstring(buf, parser=xml_parser).getroottree(),
                   name)

    from_string = from_buffer

    def __init__(self, tree, name, **kwargs):
        super().__init__(**kwargs)
        self.name = name
        self.tree = tree
        self._processors = []

    def _add_namespace_processor(self, processor_cls, *args, **kwargs):
        processor = processor_cls(self, *args, **kwargs)
        self._processors.append(processor)

    def get_element_id(self, element):
        """
        Get the ``xml:id`` of the *element*. If the element does not have such
        an id, it is generated randomly and attached to the element.

        This can be used to identify elements, as ``id(element)`` is not safe
        (lxml creates and destroys python objects for elements arbitrarily)
        and there is no other reasonably safe way, as the tree might be mutated
        heavily at any time.
        """
        id = element.get(xml.id)
        if id is not None:
            return id

        id = generate_element_id(self.tree, element)
        element.set(xml.id, id)

        return id

    def process(self, arguments):
        """
        Process the template using the given dictionary of *arguments*.

        Return the result tree after all processors have been applied.
        """
        tree = copy.deepcopy(self.tree)
        for processor in self._processors:
            processor.process(tree, arguments)
        clear_element_ids(tree)
        return tree

class Engine(teapot.templating.Engine):
    """
    The xsltea templating engine. Pass an arbitrary list of
    :class:`teapot.templating.Source` to *sources*, to define the sources to be
    used for resolving template names.
    """

    def __init__(self, *sources, **kwargs):
        super().__init__(*sources, **kwargs)
        self._cache = {}
        self._processors = []

    def _add_namespace_processor(self, processor_cls, added, new_processors):
        if processor_cls in new_processors:
            return

        if processor_cls in added:
            raise ValueError("{} has recursive dependencies".format(
                processor_cls))

        added.add(processor_cls)
        if hasattr(processor_cls, "REQUIRES"):
            for requires in processor_cls.REQUIRES:
                self._add_namespace_processor(requires, added, new_processors)

        new_processors.append(processor_cls)

    def _load_template(self, buf, name):
        template = Template.from_buffer(buf, name)
        for processor in self._processors:
            template._add_namespace_processor(processor)
        return template

    def add_namespace_processor(self, processor_cls):
        """
        Add a template processor class to the list of template processors which
        shall be applied to all templates loaded using this engine.

        This also recursively loads all required processor classes; if this
        leads to a circular require, a :class:`ValueError` is raised.

        Drops the template cache.
        """
        # delegate to infinite-recursion-safe function :)
        new_processors = list(self._processors)
        self._add_namespace_processor(processor_cls, set(), new_processors)
        self._processors[:] = new_processors
        # drop cache
        self._cache.clear()

    def get_template(self, name):
        """
        Return the template identified by the given *name*. If the template has
        been loaded before, it might be retrieved from the cache. Otherwise, all
        sources are searched for templates and the first source to be able to
        provide the template will be used.

        The template is loaded and initialized with all currently registered
        template processors.
        """
        try:
            return self.cache[name]
        except KeyError:
            pass

        with self.open_template(name) as f:
            template = self._load_template(f.read())

        self.cache[name] = template
        return template

    def _result_processor(self, template_name, result):
        template = self.get_template(template_name)
        tree = template.process(result)

    @property
    def processors(self):
        """
        List of processors currently in use in the engine.
        """
        return self._processors

    def use_template(self, name):
        """
        Decorator to make a controller function use a given template.
        """
        return self.create_decorator(
            functools.partial(self._result_processor, name))
