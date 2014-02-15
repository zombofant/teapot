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

from .errors import TemplateEvaluationError
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
    elem = etree.Element("", attrib={})
    makeelement = elem.makeelement
    elem.text = ""
    append_children(elem, childfun())
    return elem.getroottree()""",
        "<nowhere beach>",
        "exec",
        ast.PyCF_ONLY_AST)
    _elemcode_template = compile(
        """elem = makeelement("", attrib={})
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

    @staticmethod
    def lookup_hook(hookmap, tag):
        try:
            ns, name = tag.split("}", 1)
            ns = ns[1:]
        except ValueError:
            name = tag
            ns = None

        try:
            return hookmap[(ns, name)]
        except KeyError:
            return hookmap[(ns, None)]

    @classmethod
    def from_string(cls, buf, filename, attrhooks={}, elemhooks={}):
        return cls(
            etree.fromstring(buf,
                             parser=xml_parser).getroottree(),
            filename,
            attrhooks,
            elemhooks)

    from_buffer = from_string

    def __init__(self, tree, filename, attrhooks, elemhooks):
        super().__init__()
        self._attrhooks = attrhooks
        self._elemhooks = elemhooks
        self._process = self.parse_tree(tree, filename)
        del self._attrhooks
        del self._elemhooks

    def compose_attrdict(self, elem, filename):
        precode = []
        elemcode = []
        postcode = []
        d = ast.Dict(lineno=elem.sourceline, col_offset=0)
        d.keys = []
        d.values = []
        for key, value in elem.attrib.items():
            try:
                handler = self.lookup_hook(self._attrhooks, key)
            except KeyError:
                attr_precode = []
                attr_elemcode = []
                attr_keycode = ast.Str(key,
                                       lineno=elem.sourceline,
                                       col_offset=0)
                attr_valuecode = ast.Str(value,
                                         lineno=elem.sourceline,
                                         col_offset=0)
                attr_postcode = []
            else:
                attr_precode, attr_elemcode, \
                attr_keycode, attr_valuecode, \
                attr_postcode = \
                    handler(self, elem, key, filename)

            precode.extend(attr_precode)
            elemcode.extend(attr_elemcode)
            if attr_keycode and attr_valuecode:
                d.keys.append(attr_keycode)
                d.values.append(attr_valuecode)
            postcode.extend(attr_postcode)

        return precode, elemcode, d, postcode

    def compose_childrenfun(self, elem, filename):
        children_fun = copy.deepcopy(self._children_fun_template)
        precode = []
        midcode = []
        postcode = []
        for i, child in enumerate(elem):
            child_precode, child_elemcode, child_postcode = \
                self.parse_subtree(child, filename, i)
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

    def default_subtree(self, elem, filename, offset=0):
        childfun_name = "children{}".format(offset)
        precode = self.compose_childrenfun(elem, filename)
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

        attr_precode, attr_elemcode, attrdict, attr_postcode = \
            self.compose_attrdict(elem, filename)
        self._patch_element_constructor(elemcode[0].value, elem, attrdict)

        if precode:
            elemcode[-2:-2] = attr_elemcode
        else:
            elemcode[-1:-1] = attr_elemcode
        precode.extend(attr_precode)
        postcode.extend(attr_postcode)
        return precode, elemcode, postcode

    def parse_subtree(self, elem, filename, offset=0):
        """
        Parse the given subtree. Return a tuple ``(precode, elemcode,
        postcode)`` comprising the code neccessary. to generate that element and
        its children.
        """

        try:
            handler = self.lookup_hook(self._elemhooks, elem.tag)
        except KeyError:
            return self.default_subtree(elem, filename, offset)
        else:
            return handler(self, elem, filename, offset)

    def parse_tree(self, tree, filename):
        root = tree.getroot()

        childfun_name = "children"
        precode = self.compose_childrenfun(root, filename)
        if precode:
            precode[0].name = childfun_name

        rootmod = copy.deepcopy(self._root_template)
        rootfun = rootmod.body[0]
        attr_precode, attr_elemcode, attrdict, attr_postcode = \
            self.compose_attrdict(root, filename)
        self._patch_element_constructor(rootfun.body[0].value, root, attrdict)
        if precode:
            self._patch_append_func(rootfun.body[3].value, childfun_name)
        else:
            del rootfun.body[3]

        if root.text:
            rootfun.body[2].value.s = root.text
        else:
            del rootfun.body[2]

        if precode:
            rootfun.body[-2:-2] = attr_elemcode
        else:
            rootfun.body[-1:-1] = attr_elemcode
        rootfun.body[0:0] = precode + attr_precode
        rootfun.body.extend(attr_postcode)

        code = compile(rootmod, filename, "exec")
        globals_dict = dict(globals())
        locals_dict = {}
        exec(code, globals_dict, locals_dict)
        return functools.partial(locals_dict["root"], self.append_children)

    def preserve_tail_code(self, elem, filename):
        if not elem.tail:
            return []

        body = compile("""yield ''""",
                filename,
                "exec",
                flags=ast.PyCF_ONLY_AST).body
        body[0].value.value = ast.Str(elem.tail,
                                      lineno=elem.sourceline,
                                      col_offset=0)
        return body

    def process(self, arguments):
        try:
            return self._process(arguments)
        except Exception as err:
            raise TemplateEvaluationError(
                "template evaluation failed") from err


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
        self._attrhooks = None
        self._elemhooks = None

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

    def _update_hooks(self):
        if self._attrhooks is not None and self._elemhooks is not None:
            return
        self._attrhooks = {}
        self._elemhooks = {}
        for processor in self._processors:
            self._attrhooks.update(processor().attrhooks)
            self._elemhooks.update(processor().elemhooks)

    def load_template(self, buf, name):
        """
        If more customization is required, this method can be overwritten to
        provdie a fully qualified template object (including all processors
        attached to this loader) from the buffer-compatible object in *buf*
        obtained from a source object called *name*.
        """
        self._update_hooks()
        tree = self._load_template_etree(buf, name)
        template = Template(tree, name, self._attrhooks, self._elemhooks)
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
        self._attrhooks = None
        self._elemhooks = None

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
            template = self.load_template(f.read(), name)
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
