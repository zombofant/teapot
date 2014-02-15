"""
``xsltea.template`` – XML based templates
#########################################

.. autoclass:: Template

.. autoclass:: TemplateTree

.. autoclass:: EvaluationTree
   :members:

"""

import abc
import ast
import binascii
import copy
import functools
import logging
import random

import lxml.etree as etree

from .namespaces import \
    internal_noncopyable_ns, \
    internal_copyable_ns
from .pipeline import PathResolver
from .utils import sortedlist

xml_parser = etree.XMLParser(ns_clean=True,
                             remove_blank_text=True,
                             remove_comments=True)

logger = logging.getLogger(__name__)

class _TreeFormatter:
    """
    Private helper class to lazily format a *tree* for passing to logging
    functions.
    """

    def __init__(self, tree):
        self._tree = tree

    def __str__(self):
        return str(etree.tostring(self._tree))

class Template:
    _children_fun_template = compile(
        "def childrenX(): pass",
        "<nowhere beach>",
        "exec",
        ast.PyCF_ONLY_AST).body[0]
    _root_template = compile(
        """def root(append_children, arguments):
    vars().update(arguments)
    elem = etree.Element("", attrib={})
    elem.text = ""
    append_children(elem, childfun())
    return elem""",
        "<nowhere beach>",
        "exec",
        ast.PyCF_ONLY_AST)
    _elemcode_template = compile(
        """elem = etree.Element("", attrib={})
elem.text = ""
elem.tail = ""
append_children(elem, childfun())
yield elem""",
        "<nowhere beach>",
        "exec",
        ast.PyCF_ONLY_AST).body
    _elem_varname = "elem"

    @staticmethod
    def append_children(to_element, children_iterator):
        def text_append(s):
            if to_element.text is None:
                to_element.text = s
            else:
                to_element.text += s
        def later_text_append(s):
            nonlocal prev
            if prev.tail is None:
                prev.tail = s
            else:
                prev.tail += s
        prev = None
        for child in children_iterator:
            if isinstance(child, str):
                text_append(child)
                continue

            to_element.append(child)
            prev = child
            text_append = later_text_append

    @classmethod
    def from_string(cls, buf, filename, processors):
        return cls(
            etree.fromstring(buf,
                             parser=xml_parser).getroottree(),
            filename,
            processors)

    def __init__(self, tree, filename, processors):
        super().__init__()
        self._processors = processors
        self.rootfunc = self.parse_tree(tree, filename)

    def _compose_attrdict(self, elem, filename):
        d = ast.Dict(lineno=elem.sourceline, col_offset=0)
        d.keys = []
        d.values = []
        for key, value in elem.attrib.items():
            d.keys.append(ast.Str(key, lineno=elem.sourceline, col_offset=0))
            d.values.append(ast.Str(value, lineno=elem.sourceline, col_offset=0))
        return d

    def _compose_childrenfun(self, elem, filename):
        children_fun = copy.deepcopy(self._children_fun_template)
        precode = []
        midcode = []
        postcode = []
        for i, child in enumerate(elem):
            child_precode, child_elemcode, child_postcode = \
                self._parse_subtree(child, filename, i)
            precode.extend(child_precode)
            midcode.extend(child_elemcode)
            postcode.extend(child_postcode)

        children_fun.body[:] = precode
        children_fun.body.extend(midcode)
        children_fun.body.extend(postcode)

        if not children_fun.body:
            return []

        return [children_fun]

    def _patch_element_constructor(self, call, elem, attrdict):
        call.args[0].s = elem.tag
        call.keywords[0].value = attrdict

    def _patch_append_func(self, call, childfun_name):
        subcall = call.args[1]
        subcall.func.id = childfun_name

    def _parse_subtree(self, elem, filename, offset=0):
        """
        Parse the given subtree. Return a tuple ``(precode, elemcode,
        postcode)`` comprising the code neccessary. to generate that element and
        its children.
        """

        childfun_name = "children{}".format(offset)
        precode = self._compose_childrenfun(elem, filename)
        if precode:
            precode[0].name = childfun_name
        elemcode = copy.deepcopy(self._elemcode_template)
        postcode = []

        if not precode:
            # remove children statement
            del elemcode[3]
        else:
            self._patch_append_func(elemcode[3].value, childfun_name)

        if elem.tail:
            elemcode[2].value.s = elem.tail
        else:
            del elemcode[2]

        if elem.text:
            elemcode[1].value.s = elem.text
        else:
            del elemcode[1]

        attrdict = self._compose_attrdict(elem, filename)
        self._patch_element_constructor(elemcode[0].value, elem, attrdict)

        return precode, elemcode, postcode

    def parse_tree(self, tree, filename):
        root = tree.getroot()

        childfun_name = "children"
        precode = self._compose_childrenfun(root, filename)
        if precode:
            precode[0].name = childfun_name

        rootmod = copy.deepcopy(self._root_template)
        rootfun = rootmod.body[0]
        attrdict = self._compose_attrdict(root, filename)
        self._patch_element_constructor(rootfun.body[1].value, root, attrdict)
        if precode:
            self._patch_append_func(rootfun.body[3].value, childfun_name)
        else:
            del rootfun.body[3]

        if root.text:
            rootfun.body[2].value.s = root.text
        else:
            del rootfun.body[2]

        rootfun.body[0:0] = precode

        code = compile(rootmod, filename, "exec")
        globals_dict = dict(globals())
        locals_dict = {}
        exec(code, globals_dict, locals_dict)
        return functools.partial(locals_dict["root"], self.append_children)




class TemplateLoader(metaclass=abc.ABCMeta):
    """
    This is a base class to implement custom template loaders whose result is a
    tree format compatible to the default XML format.

    To subclass, several entry points are offered:

    .. automethod:: _load_template_etree

    .. automethod:: _load_template
    """

    def __init__(self, *sources, **kwargs):
        super().__init__(**kwargs)
        self._sources = list(sources)
        self._cache = {}
        self._processors = []
        self._resolver = PathResolver(*sources)
        self._parser = self._resolver._parser

    def _add_processor(self, processor_cls, added, new_processors):
        if processor_cls in new_processors:
            return

        if processor_cls in added:
            raise ValueError("{} has recursive dependencies".format(
                processor_cls))

        added.add(processor_cls)
        for requires in processor_cls.REQUIRES:
                self._add_processor(requires, added, new_processors)

        new_processors.append(processor_cls)

    @abc.abstractmethod
    def _load_template_etree(self, buf, name):
        """
        This can be overwritten to provide an element tree object which
        represents the template contained in the buffer-compatible object *buf*
        obtained from a file (or other source) called *name*.
        """

    def _load_template(self, buf, name):
        """
        If more customization is required, this method can be overwritten to
        provdie a fully qualified template object (including all processors
        attached to this loader) from the buffer-compatible object in *buf*
        obtained from a source object called *name*.
        """
        tree = self._load_template_etree(buf, name)
        template = Template(tree, name)
        for processor in self._processors:
            template._add_processor(processor)
        template.preprocess()
        return template

    def add_processor(self, processor_cls):
        """
        Add a template processor class to the list of template processors which
        shall be applied to all templates loaded using this engine.

        This also recursively loads all required processor classes; if this
        leads to a circular require, a :class:`ValueError` is raised.

        Inserting a processor with :attr:`xsltea.processor.ProcessorMeta.BEFORE`
        restrictions is in the worst case (no restrictions apply) linear in
        amount of currently added processors.

        Drops the template cache.
        """
        if processor_cls in self._processors:
            return

        # delegate to infinite-recursion-safe function :)
        for required in processor_cls.REQUIRES:
            self.add_processor(required)

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

    @property
    def processors(self):
        return self._processors

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
            return self._cache[name]
        except KeyError:
            pass

        for source in self._sources:
            try:
                f = source.open(name)
                break
            except FileNotFoundError:
                pass
            except OSError as err:
                logging.warn(
                    "while searching for template %s: %s",
                    ame, err)
        else:
            raise FileNotFoundError(name)

        try:
            template = self._load_template(f.read(), name)
        finally:
            f.close()

        self._cache[name] = template
        return template

class XMLTemplateLoader(TemplateLoader):
    """
    This is the default template loader for xsltea. It implements
    loading templates from XML and can be subclassed to process any other format
    which can either be converted into the default XML format.
    """

    def _load_template_etree(self, buf, name):
        tree = etree.fromstring(
            buf,
            parser=xml_parser).getroottree()
        return tree
