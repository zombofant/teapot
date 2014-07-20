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
import itertools
import logging
import random
import types

import teapot
import teapot.routing

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

class ReplaceAstNames(ast.NodeTransformer):
    def __init__(self, nodemap):
        self._nodemap = nodemap

    def visit_Name(self, node):
        try:
            replacement = self._nodemap[node.id]
        except KeyError:
            return node

        if isinstance(replacement, str):
            replacement = \
                ast.Str(replacement,
                        lineno=node.lineno,
                        col_offset=node.col_offset)
        return replacement

def replace_ast_names(node, nodemap):
    return ReplaceAstNames(nodemap).visit(node)

def split_tag(tag):
    """
    Split an ElementTree *tag* into its namespace and localname part, and return
    them as tuple of ``(ns, localname)``.
    """
    try:
        ns, name = tag.split("}", 1)
        ns = ns[1:]
    except ValueError:
        name = tag
        ns = None

    return ns, name

class _TreeFormatter:
    """
    Private helper class to lazily format a *tree* for passing to logging
    functions.
    """

    def __init__(self, tree):
        self._tree = tree

    def __str__(self):
        return str(etree.tostring(self._tree))

class Context:
    """
    The context object is passed around to the template processing functions, to
    have a forward-compatible storage of global evaluation parameters.

    The different attributes are available for modification by the processing
    functions if neccessary.

    .. attribute:: filename

       This is the file name of the template file currently being processed.

    .. attribute:: attrhooks

       A dictionary of attribute hooks, as described in :class:`Template` and
       :class:`~xsltea.processor.TemplateProcessor`.

    .. attribute:: elemhooks

       A dictionary of element hooks, as described in :class:`Template` and
       :class:`~xsltea.processor.TemplateProcessor`.

    """

    filename = None
    attrhooks = None
    elemhooks = None

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
    def href(request, url, *args, **kwargs):
        if teapot.isroutable(url):
            return teapot.routing.unroute_to_url(request, url, *args, **kwargs)

        if args or kwargs:
            raise TypeError("href only takes additional arguments if first "
                            "argument is routable.")

        if url.startswith("/"):
            url = url[1:]
        if request.scriptname:
            return request.scriptname + url
        else:
            return "/" + url

    @staticmethod
    def lookup_hook(hookmap, tag):
        ns, name = split_tag(tag)

        try:
            return hookmap[(ns, name)]
        except KeyError:
            return hookmap[(ns, None)]

    @staticmethod
    def lookup_attrhook(hookmap, elemtag, attrtag):
        attrns, attrname = split_tag(attrtag)
        elemns, elemname = split_tag(elemtag)

        try:
            return hookmap[(elemns, elemname, attrns, attrname)]
        except KeyError:
            pass

        try:
            return hookmap[(elemns, elemname, attrns, None)]
        except KeyError:
            pass

        try:
            return hookmap[(elemns, None, attrns, attrname)]
        except KeyError:
            pass

        try:
            return hookmap[(elemns, None, attrns, None)]
        except KeyError:
            pass

        try:
            return hookmap[(None, None, attrns, attrname)]
        except KeyError:
            pass

        try:
            return hookmap[(None, None, attrns, None)]
        except KeyError:
            pass

        try:
            return hookmap[(attrns, attrname)]
        except KeyError:
            pass

        return hookmap[(attrns, None)]

    @classmethod
    def from_string(cls, buf, filename, attrhooks={}, elemhooks={}):
        return cls(
            etree.fromstring(buf,
                             parser=xml_parser).getroottree(),
            filename,
            attrhooks,
            elemhooks)

    from_buffer = from_string

    def __init__(self, tree, filename, attrhooks, elemhooks,
                 globalhooks=[],
                 loader=None,
                 global_precode=[],
                 global_postcode=[]):
        super().__init__()

        self.storage = {}
        self._reverse_storage = {}
        self.loader = loader
        context = Context()
        context.filename = filename
        context.attrhooks = copy.deepcopy(attrhooks)
        context.elemhooks = copy.deepcopy(elemhooks)
        context.globalhooks = copy.copy(globalhooks)
        self._process = self.parse_tree(
            tree, context,
            global_precode,
            global_postcode)
        self.tree = tree
        del self._reverse_storage

    def default_attrhandler(self, elem, key, value, context):
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

    def compose_attrdict(self, elem, context):
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
                handlers = self.lookup_attrhook(context.attrhooks, elem.tag, key)
            except KeyError:
                handlers = []
            for handler in handlers:
                result = handler(self, elem, key, value, context)
                if result:
                    break
            else:
                result = self.default_attrhandler(elem, key, value, context)
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

    def build_childrenfun_body(self, elem, context):
        """
        Create and return a list of ast nodes which resemble the body of the
        children function (see :meth:`compose_childrenfun`) for the given *elem*.
        """
        precode = []
        midcode = []
        postcode = []
        for i, child in enumerate(elem):
            child_precode, child_elemcode, child_postcode = \
                self.parse_subtree(child, context, i)
            precode.extend(child_precode)
            midcode.extend(child_elemcode)
            postcode.extend(child_postcode)

        body = precode
        body.extend(midcode)
        body.extend(postcode)

        body.append(ast.Return(
            ast.List(
                [],
                ast.Load(),
                lineno=elem.sourceline or 0,
                col_offset=0),
            lineno=elem.sourceline or 0,
            col_offset=0))

        return body

    def compose_childrenfun(self, elem, context, name):
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
                               context.filename,
                               "exec",
                               ast.PyCF_ONLY_AST).body[0]
        children_fun.body[:] = self.build_childrenfun_body(
            elem, context)

        if not children_fun.body:
            return []

        return [children_fun]

    def default_subtree(self, elem, context, offset=0):
        """
        Create code for the element and its children. This is the identity
        transform which creates code reflecting the element unchanged (but
        applying all transforms to its attributes and children).

        Returns a tuple containing *precode*, *elemcode* and *postcode*.
        """

        childfun_name = "children{}".format(offset)
        precode = self.compose_childrenfun(elem, context, childfun_name)
        attr_precode, attr_elemcode, attrdict, attr_postcode = \
            self.compose_attrdict(elem, context)

        elemcode = self.ast_makeelement_and_setup(
            elem.tag,
            elem.sourceline or 0,
            attrdict=attrdict,
            text=elem.text,
            tail=elem.tail,
            elemcode=attr_elemcode,
            childfun=childfun_name if precode else None)
        elemcode.append(
            self.ast_yield("elem", elem.sourceline or 0))

        precode.extend(attr_precode)
        postcode = attr_postcode
        return precode, elemcode, postcode

    def parse_subtree(self, elem, context, offset=0):
        """
        Parse the given subtree. Return a tuple ``(precode, elemcode,
        postcode)`` comprising the code neccessary. to generate that element and
        its children.
        """

        try:
            handlers = self.lookup_hook(context.elemhooks, elem.tag)
        except KeyError:
            handlers = []

        for handler in handlers:
            result = handler(self, elem, context, offset)
            if result:
                return result

        return self.default_subtree(elem, context, offset)

    def parse_tree(self, tree, context, global_precode, global_postcode):
        self.utils = types.SimpleNamespace()

        root = tree.getroot()

        global_precode = list(itertools.chain(
            *(precode_func(self) for precode_func in global_precode)))
        global_postcode = list(itertools.chain(
            *(postcode_func(self) for postcode_func in global_postcode)))

        for hook in context.globalhooks:
            precode, postcode = hook(self, root, context)
            global_precode.extend(precode)
            global_postcode[0:0] = postcode

        childfun_name = "children"
        childfun = self.compose_childrenfun(root, context, childfun_name)
        attr_precode, attr_elemcode, attrdict, attr_postcode = \
            self.compose_attrdict(root, context)

        rootfun_body = []
        rootfun = ast.FunctionDef(
            "root",
            ast.arguments(
                [
                    ast.arg("utils", None),
                    ast.arg("context", None),
                    ast.arg("arguments", None)
                ],
                None,
                None,
                [],
                None,
                None,
                [],
                []),
            rootfun_body,
            [],
            None,
            lineno=0,
            col_offset=0)

        rootfun_body[:0] = global_precode + attr_precode + childfun

        rootfun_body.extend([
            ast.Assign(
                [
                    ast.Name(
                        "elem",
                        ast.Store(),
                        lineno=0,
                        col_offset=0),
                ],
                ast.Call(
                    ast.Attribute(
                        ast.Name(
                            "etree",
                            ast.Load(),
                            lineno=0,
                            col_offset=0),
                        "Element",
                        ast.Load(),
                        lineno=0,
                        col_offset=0),
                    [
                        ast.Str(
                            root.tag,
                            lineno=0,
                            col_offset=0),
                        attrdict
                    ],
                    [],
                    None,
                    None,
                    lineno=0,
                    col_offset=0),
                lineno=0,
                col_offset=0),
            ast.Assign(
                [
                    self.ast_get_from_object("makeelement", "context",
                                             0,
                                             ast.Store())
                ],
                ast.Attribute(
                    ast.Name(
                        "elem",
                        ast.Load(),
                        lineno=0,
                        col_offset=0),
                    "makeelement",
                    ast.Load(),
                    lineno=0,
                    col_offset=0),
                lineno=0,
                col_offset=0)
        ])

        if root.text:
            rootfun_body.append(
                self.ast_set_text(
                    "elem",
                    root.text,
                    root.sourceline or 0))

        rootfun_body.extend(attr_elemcode)

        if childfun:
            rootfun_body.append(
                self.ast_append_children(
                    "elem",
                    childfun_name,
                    root.sourceline or 0))

        rootfun_body.extend(attr_postcode)
        rootfun_body.extend(global_postcode)

        rootfun_body.append(
            ast.Return(
                ast.Call(
                    ast.Attribute(
                        ast.Name(
                            "elem",
                            ast.Load(),
                            lineno=0,
                            col_offset=0),
                        "getroottree",
                        ast.Load(),
                        lineno=0,
                        col_offset=0),
                    [], [],
                    None, None,
                    lineno=0,
                    col_offset=0),
                lineno=0,
                col_offset=0))


        rootmod = ast.Module([rootfun])
        # print(ast.dump(rootmod))

        code = compile(rootmod, context.filename, "exec")
        globals_dict = dict(globals())
        locals_dict = {}
        exec(code, globals_dict, locals_dict)

        self.utils.append_children = self.append_children
        self.utils.storage = self.storage

        return functools.partial(locals_dict["root"],
                                 self.utils)

    def preserve_tail_code(self, elem, context):
        """
        Create *elemcode* for *elem* which yields the elements ``tail`` text, if
        any is present.

        Return an *elemcode* list, which might be empty if no ``tail`` text is
        present.
        """
        if not elem.tail:
            return []

        body = compile("""yield ''""",
                context.filename,
                "exec",
                flags=ast.PyCF_ONLY_AST).body
        body[0].value.value = ast.Str(elem.tail,
                                      lineno=elem.sourceline or 0,
                                      col_offset=0)
        return body

    def compose_context(self, arguments, request=None):
        context = types.SimpleNamespace()
        context.request = request
        context.href = functools.partial(self.href, request)
        return context

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
            context = self.compose_context(arguments, request=request)
            return self._process(context, arguments)
        except Exception as err:
            raise TemplateEvaluationError(
                "template evaluation failed") from err

    def store(self, obj):
        try:
            hash(obj)
        except (TypeError, ValueError):
            obj_key = (False, id(obj))
        else:
            obj_key = (True, obj)

        try:
            return self._reverse_storage[obj_key]
        except KeyError:
            pass

        while True:
            identifier = binascii.b2a_hex(
                random.getrandbits(8*12).to_bytes(12, "little")).decode()
            if identifier not in self.storage:
                break

        self._reverse_storage[obj_key] = identifier
        self.storage[identifier] = obj

        return identifier

    # other utilities

    def compilation_error(self, msg, context, sourceline):
        return ValueError(
            "{} (in {}:{})".format(
                msg,
                context.filename,
                sourceline or 0))

    # AST code generation helpers, which may need Template state in the future

    def ast_append_children(self, elem, childfun, sourceline):
        """
        Return an AST statement which appends the children provided by
        *childfun* to the element referred to by *elem*.

        The AST is tagged to belong to the given *sourceline*.

        If any of *elem* or *childfun* is a string, it is converted to an
        :class:`ast.Name` with load semantics.
        """

        elem = self.ast_or_name(elem, sourceline)
        childfun = self.ast_or_name(childfun, sourceline)

        return ast.Expr(
            ast.Call(
                self.ast_get_util("append_children", sourceline),
                [
                    elem,
                    ast.Call(
                        childfun,
                        [], [],
                        None, None,
                        lineno=sourceline,
                        col_offset=0)
                ],
                [],
                None,
                None,
                lineno=sourceline,
                col_offset=0),
            lineno=sourceline,
            col_offset=0)

    def ast_store_and_call(self, callable,
                           args=[],
                           keywords={},
                           starargs=None, kwargs=None,
                           *,
                           sourceline=0):
        """
        Store a given *callable* in the template and call it with the provided
        arguments.

        *args* must be a list of AST nodes or strings (may be mixed). Strings
        are converted to names implicitly (using :meth:`ast_or_name`).

        *keywords* must either be a list of :class:`ast.keyword` instances or a
        dictionary. If it is a dictionary, it is converted to a list tof
        :class:`ast.keyword` instances, by taking the keys (which must be
        strings) as keyword keys and the values as names or AST nodes (using
        :meth:`ast_or_name`).

        If *starargs* is not :data:`None`, it must either be an AST node
        pointing to a sequence, which will be passed as starargs to the
        function, or a list of AST nodes or strings (may be mixed; strings are
        converted to AST nodes via :meth:`ast_or_name`).

        If *kwargs* is not :data:`None`, it must either be an AST node pointing
        to a dictionary to be passed as kwargs to the function, or a dictionary,
        which will be converted to an :class:`ast.Dict`. Plain string keys are
        converted to :class:`ast.Str`, plain string values are converted to
        :class:`ast.Name`.

        Return the :class:`ast.Expr` object which wraps the call.
        """

        for i, arg in enumerate(args):
            args[i] = self.ast_or_name(arg, sourceline)

        if hasattr(keywords, "items"):
            keywords = [
                ast.keyword(key, self.ast_or_name(value, sourceline))
                for key, value in keywords.items()
            ]

        if starargs is not None and hasattr(starargs, "__iter__"):
            starargs = ast.List(
                [
                    self.ast_or_name(arg, sourceline)
                    for arg in starargs
                ],
                lineno=sourceline,
                col_offset=0)

        if (    kwargs is not None and
                hasattr(kwargs, "items")):

            kwargs_keys = []
            kwargs_values = []

            for key, value in kwargs.items():
                kwargs_keys.append(self.ast_or_str(key, sourceline))
                kwargs_values.append(self.ast_or_name(value, sourceline))

            kwargs = ast.Dict(
                kwargs_keys,
                kwargs_values,
                lineno=sourceline,
                col_offset=0)

        return ast.Expr(
            ast.Call(
                self.ast_get_stored(
                    self.store(callable),
                    sourceline),
                args,
                keywords,
                starargs,
                kwargs,
                lineno=sourceline,
                col_offset=0),
            lineno=sourceline,
            col_offset=0)


    def ast_get_elem_attr(self, key, sourceline, varname="elem", default=None):
        """
        Return an AST expression which evaluates to the value of the XML
        attribute *key* on the element referred to by *varname*.

        The AST is tagged to belong to the given *sourceline*.

        If *varname* is a string, it is converted to an :class:`ast.Name` with
        load semantics. If any of *key* and *default* is a string, it is wrapped
        in an :class:`ast.Str`.
        """

        args = [
            self.ast_or_str(key, sourceline),
        ]

        if default is not None:
            default = self.ast_or_str(default, sourceline)
            args.append(default)

        return ast.Call(
            self.ast_get_from_object(
                "get",
                self.ast_or_name(varname, sourceline),
                sourceline),
            args,
            [],
            None,
            None,
            lineno=sourceline,
            col_offset=0)

    def ast_get_from_object(self, attrname, objname, sourceline, ctx=None):
        """
        Return an AST expression which evaluates to the value of the attribute
        *attrname* on the object referred to by *objname*, which can be used in
        the given *ctx* (defaulting to a :class:`ast.Load` context).

        The AST is tagged to belong to the given *sourceline*.

        If *objname* is a string, it is converted to an :class:`ast.Name` with
        load semantics.
        """

        ctx = ctx or ast.Load()
        return ast.Attribute(
            self.ast_or_name(objname, sourceline),
            attrname,
            ctx,
            lineno=sourceline,
            col_offset=0)

    def ast_get_href(self, sourceline):
        """
        Return an AST expression which evaluates to the :meth:`href` method,
        partially specialized using the current request (so that it takes only
        one argument, the object to be converted into an URL).

        The AST is tagged to belong to the given *sourceline*.
        """

        return self.ast_get_from_object("href", "context", sourceline)

    def ast_get_util(self, utilname, sourceline, ctx=None):
        """
        Return an AST expression providing access to the attribute *utilname* on
        the `utils` object in the given *ctx* (defaulting to a :class:`ast.Load`
        context).

        The AST is tagged to belong to the given *sourceline*.
        """

        return self.ast_get_from_object(utilname, "utils", sourceline, ctx=ctx)

    def ast_get_request(self, sourceline):
        """
        Return an AST expression evaluating to the current request. It can be
        used in :class:`ast.Load` contexts.

        The AST is tagged to belong to the given *sourceline*.
        """
        return self.ast_get_from_object("request", "context", sourceline)

    def ast_get_stored(self, key, sourceline, ctx=None):
        """
        Return an AST expression which evaluates to the stored object with the
        given *key* (as returned by :meth:`store`). The object can be used in
        the context given by *ctx* (defaults to :class:`ast.Load`).

        The AST is tagged to belong to the given *sourceline*.
        """

        return ast.Subscript(
            self.ast_get_from_object(
                "storage",
                "utils",
                sourceline),
            ast.Index(
                ast.Str(
                    key,
                    lineno=sourceline,
                    col_offset=0),
                lineno=sourceline,
                col_offset=0),
            ctx or ast.Load(),
            lineno=sourceline,
            col_offset=0)

    def ast_href(self, from_, sourceline):
        """
        Return an AST expression which calls the ``href`` utility on the given
        input, *from_*.

        The AST is tagged to belong to the given *sourceline*.

        If *from_* is a string, it is wrapped into an :class:`ast.Str`.
        """

        return ast.Call(
            self.ast_get_href(sourceline),
            [
                self.ast_or_str(from_, sourceline)
            ],
            [],
            None,
            None,
            lineno=sourceline,
            col_offset=0)

    def ast_makeelement(self, tag, sourceline, attrdict=None, nsdict=None):
        """
        Return an AST expression which evaluates to a newly created
        :class:`lxml.etree.Element`. The element will have the given *tag*, and
        if given attributes from *attrdict* and it will be using the namespace
        map provided in *nsdict*. For details see the documentation of the
        ``makeelement`` function from :mod:`lxml.etree`.

        The dictionaries **must** be :class:`ast.Dict` objects, or
        :data:`None`.

        The AST is tagged to belong to the given *sourceline*.

        If *tag* is a string, it is wrapped into an :class:`ast.Str`.
        """

        tag = self.ast_or_str(tag, sourceline)

        args = [
            tag
        ]
        if attrdict is not None:
            args.append(attrdict)
        if nsdict is not None:
            if attrdict is None:
                args.append(
                    ast.Dict([], [],
                             lineno=sourceline,
                             col_offset=0))
            args.append(nsdict)

        return ast.Call(
            self.ast_get_from_object("makeelement", "context", sourceline),
            args,
            [],
            None,
            None,
            lineno=sourceline,
            col_offset=0)

    def ast_makeelement_and_setup(
            self, tag, sourceline,
            attrdict=None,
            nsdict=None,
            text=None,
            tail=None,
            elemcode=None,
            childfun=None,
            varname="elem"):
        """
        Return a list of AST statements which create an element and set it up in
        a sophisticated manner. Element creation happens through
        :meth:`ast_makeelement`, thus the documentation of *tag*, *attrdict* and
        *nsdict* from there applies.

        After construction, the elements ``text`` attribute is set to *text*, if
        *text* is not :data:`None`. The same holds for the ``tail`` attribute,
        using *tail* respectively.

        If *elemcode* is not :data:`None`, it is inserted after text and tail
        have been set up, but before the child function is called, if any.

        If *childfun* is not :data:`None`, a statement to append the children to
        the element using the given *childfun* is created using
        :meth:`ast_append_children`, so the documentation from there regarding
        *childfun* applies.

        The AST is tagged to belong to the given *sourceline*.

        If any of *text* or *tail* is a string, it is wrapped in an
        :class:`ast.Str`.
        """

        code = [
            ast.Assign(
                [
                    ast.Name(
                        varname,
                        ast.Store(),
                        lineno=sourceline,
                        col_offset=0),
                ],
                self.ast_makeelement(tag, sourceline,
                                     attrdict=attrdict,
                                     nsdict=nsdict),
                lineno=sourceline,
                col_offset=0)
        ]

        if text is not None:
            code.append(self.ast_set_text(varname, text, sourceline))

        if tail is not None:
            code.append(self.ast_set_tail(varname, tail, sourceline))

        if elemcode is not None:
            code.extend(elemcode)

        if childfun is not None:
            code.append(
                self.ast_append_children(
                    varname,
                    childfun,
                    sourceline))

        return code

    def ast_or_name(self, value, sourceline, ctx=None):
        """
        Return an :class:`ast.Name` pointing to the name in *value* if *value*
        is a string and return *value* otherwise.

        If a :class:`ast.Name` instance is created, it will be attributed to the
        given *sourceline* and be using the context *ctx*, which defaults to a
        :class:`ast.Load` context.
        """

        ctx = ctx or ast.Load()
        if isinstance(value, str):
            value = ast.Name(
                value,
                ctx,
                lineno=sourceline,
                col_offset=0)

        return value

    def ast_or_str(self, value, sourceline):
        """
        Return an :class:`ast.Str` containing the string in *value* if *value*
        is a string and return *value*x otherwise.

        If a :class:`ast.Str` instance is created, it will be attributed to the
        given *sourceline*.
        """

        if isinstance(value, str):
            value = ast.Str(
                value,
                lineno=sourceline,
                col_offset=0)

        return value

    def ast_set_attr(self, obj, attrname, value, sourceline):
        """
        Return an AST statement setting the attribute with *attrname* on the
        given *obj* to the given *value*.

        The AST is tagged to belong to the given *sourceline*.

        If *obj* is a string, it will be converted to a :class:`ast.Name`.
        """

        return ast.Assign(
            [
                ast.Attribute(
                    self.ast_or_name(obj, sourceline),
                    attrname,
                    ast.Store(),
                    lineno=sourceline,
                    col_offset=0)
            ],
            value,
            lineno=sourceline,
            col_offset=0)

    def ast_set_elem_attr(self, key, value, sourceline, varname="elem"):
        """
        Return an AST statement setting the XML attribute *key* to the given
        *value* on the XML element stored in the variable called *varname*.

        The AST is tagged to belong to the given *sourceline*.

        If *varname* is a string, it will be converted to an
        :class:`ast.Name`. If any of *key* or *value* is a string, it will be
        converted to :class:`ast.Str`.
        """

        return ast.Expr(
            ast.Call(
                self.ast_get_from_object(
                    "set",
                    self.ast_or_name(varname, sourceline),
                    sourceline),
                [
                    self.ast_or_str(key, sourceline),
                    self.ast_or_str(value, sourceline)
                ],
                [],
                None,
                None,
                lineno=sourceline,
                col_offset=0),
            lineno=sourceline,
            col_offset=0)

    def ast_set_tail(self, varname, value, sourceline):
        """
        Return an AST statement setting the XML tail of the element in *varname*
        to the given *value*.

        The AST is tagged to belong to the given *sourceline*.

        If *varname* is a string, it will be converted to an
        :class:`ast.Name`. If *value* is a string, it will be converted to
        :class:`ast.Str`.
        """

        return self.ast_set_attr(
            self.ast_or_name(varname, sourceline),
            "tail",
            self.ast_or_str(value, sourceline),
            sourceline)

    def ast_set_text(self, varname, value, sourceline):
        """
        Return an AST statement setting the XML text of the element in *varname*
        to the given *value*.

        The AST is tagged to belong to the given *sourceline*.

        If *varname* is a string, it will be converted to an
        :class:`ast.Name`. If *value* is a string, it will be converted to
        :class:`ast.Str`.
        """

        return self.ast_set_attr(
            self.ast_or_name(varname, sourceline),
            "text",
            self.ast_or_str(value, sourceline),
            sourceline)

    def ast_yield(self, varname, sourceline):
        """
        Return an AST statement yielding the object referred to by *varname*.

        The AST is tagged to belong to the given *sourceline*.

        If *varname* is a string, it will be converted to an :class:`ast.Name`.
        """

        varname = self.ast_or_name(varname, sourceline)
        return ast.Expr(
            ast.Yield(
                varname,
                lineno=sourceline,
                col_offset=0),
            lineno=sourceline,
            col_offset=0)


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
        self._global_postcode = None
        self._global_precode = None
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
        globalhooks = []
        global_precode = []
        global_postcode = []
        for processor in self._processors:
            for selector, hooks in processor.attrhooks.items():
                attrhooks.setdefault(selector, []).extend(hooks)
            for selector, hooks in processor.elemhooks.items():
                elemhooks.setdefault(selector, []).extend(hooks)
            globalhooks.extend(processor.globalhooks)
            global_precode.append(processor.global_precode)
            global_postcode.append(processor.global_postcode)

        global_postcode.reverse()

        self._attrhooks = attrhooks
        self._elemhooks = elemhooks
        self._globalhooks = globalhooks
        self._global_precode = global_precode
        self._global_postcode = global_postcode

    def load_template(self, buf, name):
        """
        If more customization is required, this method can be overwritten to
        provide a fully qualified template object (including all processors
        attached to this loader) from the buffer-compatible object in *buf*
        obtained from a source object called *name*.

        This method can also be used by user code to explicitly load a template,
        leaving aside any caching.
        """
        self._update_hooks()
        tree = self._load_template_etree(buf, name)
        template = Template(tree,
                            name,
                            self._attrhooks,
                            self._elemhooks,
                            globalhooks=self._globalhooks,
                            loader=self,
                            global_precode=self._global_precode,
                            global_postcode=self._global_postcode)
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
