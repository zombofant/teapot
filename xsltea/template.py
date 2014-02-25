"""
``xsltea.template`` – XML based templates
#########################################

.. autoclass:: Template

.. autoclass:: TemplateLoader

.. autoclass:: XMLTemplateLoader

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
    """
    This class implements a template, based on an lxml etree. For every element
    which is not hooked using *attrhooks* or *elemhooks*, python code is
    generated which re-creates that element and its tail text.

    For all other, hook functions are called which provide the python code to
    perform the desired action. For a description of the hook dictionaries and
    their structure, please see :class:`~xsltea.processor.TemplateProcessor`.

    The user interface basically only consists of the process method:

    .. automethod:: process

    In addition to the public user interface, the template provides several
    utility functions for template processors. Throughout the documentation of
    these the terms *precode*, *elemcode* and *postcode* are used. For more
    information on these, please see the documentation of the
    :class:`~xsltea.processor.TemplateProcessor` attributes.

    .. automethod:: compose_attrdict

    .. automethod:: compose_childrenfun

    .. automethod:: default_subtree

    .. automethod:: preserve_tail_code
    """

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

    def default_attrhandler(self, elem, key, value, filename):
        precode = []
        elemcode = []
        keycode = ast.Str(key,
                          lineno=elem.sourceline or 0,
                          col_offset=0)
        valuecode = ast.Str(value,
                            lineno=elem.sourceline or 0,
                            col_offset=0)
        postcode = []
        return precode, elemcode, keycode, valuecode, postcode

    def compose_attrdict(self, elem, filename):
        """
        Create code which constructs the attributes for the given *elem*.

        Returns ``(precode, elemcode, dictcode, postcode)``. The *dictcode* is a
        :class:`ast.Dict` instance which describes the dictionary which can be
        passed to the ``attrib``-kwarg of ``makeelement``.
        """
        precode = []
        elemcode = []
        postcode = []
        d = ast.Dict(lineno=elem.sourceline or 0, col_offset=0)
        d.keys = []
        d.values = []
        for key, value in elem.attrib.items():
            try:
                handlers = self.lookup_hook(self._attrhooks, key)
            except KeyError:
                handlers = []
            for handler in handlers:
                result = handler(self, elem, key, value, filename)
                if result:
                    break
            else:
                result = self.default_attrhandler(elem, key, value, filename)
            attr_precode, attr_elemcode, \
            attr_keycode, attr_valuecode, \
            attr_postcode = result


            precode.extend(attr_precode)
            elemcode.extend(attr_elemcode)
            if attr_keycode and attr_valuecode:
                d.keys.append(attr_keycode)
                d.values.append(attr_valuecode)
            postcode.extend(attr_postcode)

        return precode, elemcode, d, postcode

    def compose_childrenfun(self, elem, filename, name):
        """
        Create *precode* declaring a function yielding all children of the given
        *elem* with the name *name*.

        Returns an array of *precode* which declares the function or which is
        empty, if the element has no children.

        Please note that this does *not* take care of the ``text`` of the
        element -- this must be handled by the element itself. ``tail`` text of
        the children is handled by the children as usual.
        """

        children_fun = compile("""\
def {}():
    pass""".format(name),
                               filename,
                               "exec",
                               ast.PyCF_ONLY_AST).body[0]
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

    def default_subtree(self, elem, filename, offset=0):
        """
        Create code for the element and its children. This is the identity
        transform which creates code reflecting the element unchanged (but
        applying all transforms to its attributes and children).

        Returns a tuple containing *precode*, *elemcode* and *postcode*.
        """

        childfun_name = "children{}".format(offset)
        precode = self.compose_childrenfun(elem, filename, childfun_name)
        elemcode = compile("""\
elem = makeelement("", attrib={{}})
elem.text = ""
elem.tail = ""
append_children(elem, {}())
yield elem""".format(childfun_name),
                           filename,
                           "exec",
                           ast.PyCF_ONLY_AST).body
        postcode = []

        if not precode:
            # remove children statement
            del elemcode[3]

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
            handlers = self.lookup_hook(self._elemhooks, elem.tag)
        except KeyError:
            handlers = []

        for handler in handlers:
            result = handler(self, elem, filename, offset)
            if result:
                return result

        return self.default_subtree(elem, filename, offset)

    def parse_tree(self, tree, filename):
        root = tree.getroot()

        childfun_name = "children"
        precode = self.compose_childrenfun(root, filename, childfun_name)
        if precode:
            precode[0].name = childfun_name

        rootmod = compile("""\
def root(append_children, request, arguments):
    elem = etree.Element("", attrib={{}})
    makeelement = elem.makeelement
    elem.text = ""
    append_children(elem, {}())
    return elem.getroottree()""".format(childfun_name),
                          filename,
                          "exec",
                          ast.PyCF_ONLY_AST)
        rootfun = rootmod.body[0]
        attr_precode, attr_elemcode, attrdict, attr_postcode = \
            self.compose_attrdict(root, filename)
        self._patch_element_constructor(rootfun.body[0].value, root, attrdict)

        if not precode:
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
        """
        Create *elemcode* for *elem* which yields the elements ``tail`` text, if
        any is present.

        Return an *elemcode* list, which might be empty if no ``tail`` text is
        present.
        """
        if not elem.tail:
            return []

        body = compile("""yield ''""",
                filename,
                "exec",
                flags=ast.PyCF_ONLY_AST).body
        body[0].value.value = ast.Str(elem.tail,
                                      lineno=elem.sourceline or 0,
                                      col_offset=0)
        return body

    def process(self, arguments, request=None):
        """
        Evaluate the template using the given *arguments*. The contents of
        *arguments* is made available under the name *arguments* inside the
        template.

        *request* is supposed to be a teapot request object. Some processors
        might require this, but it is in general optional.

        Any exceptions thrown during template evaluation are caught and
        converted into :class:`~xsltea.errors.TemplateEvaluationError`, with the
        original exception being attached as context.
        """
        try:
            return self._process(request, arguments)
        except Exception as err:
            raise TemplateEvaluationError(
                "template evaluation failed") from err


class TemplateLoader(metaclass=abc.ABCMeta):
    """
    This is a base class to implement custom template loaders whose result is a
    tree format compatible to the default XML format.

    To subclass, several entry points are offered:

    .. automethod:: _load_template_etree

    .. automethod:: load_template
    """

    def __init__(self, *sources, **kwargs):
        super().__init__(**kwargs)
        self._sources = list(sources)
        self._cache = {}
        self._resolver = PathResolver(*sources)
        self._parser = self._resolver._parser
        self._attrhooks = None
        self._elemhooks = None
        self._processors = []

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
        attrhooks = {}
        elemhooks = {}
        for processor in self._processors:
            for selector, hooks in processor.attrhooks.items():
                attrhooks.setdefault(selector, []).extend(hooks)
            for selector, hooks in processor.elemhooks.items():
                elemhooks.setdefault(selector, []).extend(hooks)

        self._attrhooks = attrhooks
        self._elemhooks = elemhooks

    def load_template(self, buf, name):
        """
        If more customization is required, this method can be overwritten to
        provdie a fully qualified template object (including all processors
        attached to this loader) from the buffer-compatible object in *buf*
        obtained from a source object called *name*.

        This method can also be used by user code to explicitly load a template,
        leaving aside any caching.
        """
        self._update_hooks()
        tree = self._load_template_etree(buf, name)
        template = Template(tree, name, self._attrhooks, self._elemhooks)
        return template

    def add_processor(self, processor):
        """
        Add a template processor class to the list of template processors which
        shall be applied to all templates loaded using this engine.

        Drops the template cache.
        """
        # backwards compatibility
        if isinstance(processor, type) and hasattr(processor, "__call__"):
            processor = processor()
        self._processors.append(processor)

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
