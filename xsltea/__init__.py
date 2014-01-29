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

import binascii
import copy
import logging
import os
import random

logger = logging.getLogger(__name__)

try:
    import lxml.etree as etree
except ImportError as err:
    logger.error("xsltea fails to load: lxml is not available")
    raise

import teapot.templating

from .namespaces import xml, internal_ns
from .processor import TemplateProcessor
from .exec import ExecProcessor
from .utils import *
from .errors import TemplateEvaluationError

xml_parser = etree.XMLParser(ns_clean=True,
                             remove_blank_text=True,
                             remove_comments=True)

class TemplateTree:
    namespaces = {"internal": str(internal_ns)}

    _element_id_rng = random.Random()
    _element_id_rng.seed()

    xpath_selector_non_barred = "not(ancestor::*[@internal:barrier])"

    def __init__(self, tree):
        self.tree = tree

    def __deepcopy__(self, copydict):
        return TemplateTree(copy.deepcopy(self.tree, copydict))

    def _get_elements_by_attribute(self, base, attrname, elemid):
        return base.xpath(
            "descendant::*[@internal:{} = '{}']".format(
                attrname, elemid),
            namespaces=self.namespaces)

    def _get_unique_element_attribute(self, attrname):
        while True:
            randbytes = self._element_id_rng.getrandbits(128).to_bytes(
                16, 'little')
            elemid = attrname+binascii.b2a_hex(randbytes).decode()
            if not self._get_elements_by_attribute(self.tree, attrname, elemid):
                return elemid

    def deepcopy_subtree(self, subtree):
        """
        Copy the given element *subtree* and all of its children using
        :func:`copy.deepcopy`. In addition to mere copying, ``internal:id``
        attributes are removed so that it is safe to re-insert these elements
        into this tree.
        """
        copied = copy.deepcopy(subtree)
        for id_attr in copied.xpath("descendant::@internal:id",
                                    namespaces=self.namespaces):
            del id_attr.getparent().attrib[id_attr.attrname]
        return copied

    def get_element_by_id(self, id):
        """
        Return the element carrying the given *id* or raise :class:`KeyError` if
        the element does not exist.
        """
        try:
            return self.tree.xpath("//*[@internal:id = '"+id+"']",
                                   namespaces=self.namespaces).pop()
        except IndexError:
            raise KeyError(id) from None

    def get_elements_by_name(self, name, root=None):
        """
        Get all elements which have an ``@internal:name`` attribute matching
        *name*. Return a possibly empty list of matching elements.

        If *root* is given, only search in the children of that element.
        """
        return self._get_elements_by_attribute(
            (root if root is not None else self.tree),
            "name", name)

    def get_element_id(self, element):
        """
        Get the ``internal:id`` of the *element*. The same rules as for
        :meth:`get_element_name` apply, except that the `id` is not copied when
        the element is within a subtree copied using :meth:`deepcopy_subtree`.
        """
        id = element.get(internal_ns.id)
        if id is not None:
            return id

        id = self._get_unique_element_attribute("id")
        element.set(internal_ns.id, id)

        return id

    def get_element_name(self, element):
        """
        Get the ``internal:name`` of the *element*. If the element does not have
        such a name, it is generated randomly and attached to the element.

        This can be used to identify elements, as ``id(element)`` is not safe
        (lxml creates and destroys python objects for elements arbitrarily)
        and there is no other reasonably safe way, as the tree might be mutated
        heavily at any time.

        Note that multiple elements may share the same name, if they have been
        duplicated. Also, elements may just vanish during processing. Your code
        must be able to cope with both cases.
        """
        name = element.get(internal_ns.name)
        if name is not None:
            return name

        name = self._get_unique_element_attribute("name")
        element.set(internal_ns.name, name)

        return name

    def set_element_barrier(self, element, barrier=True):
        if barrier:
            element.set(internal_ns.barrier, "")
        else:
            try:
                del element.attrib[internal_ns.barrier]
            except KeyError:
                pass

class Template(TemplateTree):
    """
    Wrap an lxml ``ElementTree`` *tree* as a template. The *tree* may be heavily
    modified during processing, thus, if you need the tree also for other
    purposes make sure to pass a deep copy.

    For debugging output, the *name* of the template is also used; if the
    template does not come from a file, use another distinct identifier, such as
    ``"<string>"``.

    .. attribute:: tree

       The ``TemplateTree`` which belongs to the template.

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
        super().__init__(tree, **kwargs)
        self.name = name
        self._processors_ordered = []
        self._processors = {}

    def _add_namespace_processor(self, processor_cls, *args, **kwargs):
        if processor_cls in self._processors:
            raise ValueError("{} already loaded in template {}".format(
                processor_cls, self))
        processor = processor_cls(self, *args, **kwargs)
        self._processors_ordered.append(processor)
        self._processors[processor_cls] = processor

    def get_processor(self, processor_cls):
        """
        Return the processor instance of the given processor class associated
        with this Template. If the processor has not been added to the template
        (via the :class:`Engine`), :class:`KeyError` is raised.
        """
        return self._processors[processor_cls]

    def process(self, arguments):
        """
        Process the template using the given dictionary of *arguments*.

        Return the result tree after all processors have been applied.
        """
        tree = TemplateTree(copy.deepcopy(self.tree))
        for processor in self._processors_ordered:
            processor.process(tree, arguments)
        # clear_element_ids(tree)
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
        if processor_cls in self._processors:
            return

        # delegate to infinite-recursion-safe function :)
        for required in processor_cls.REQUIRES:
            self.add_namespace_processor(required)

        new_index = None
        if processor_cls.BEFORE:
            # we can ignore AFTER here, because we, by default, insert at the
            # end.
            new_index = len(self._processors)
            for i, other_cls in enumerate(self._processors):
                if other_cls in processor_cls.BEFORE:
                    new_index = min(i, new_index)
                    break

        if new_index is not None:
            self._processors.insert(new_index, processor_cls)
        else:
            # no ordering restrictions found
            self._processors.append(processor_cls)

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
