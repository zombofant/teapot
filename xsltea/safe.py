"""
``xsltea.safe`` – Safe processors
#################################

This module provides some processors which deal with python names and template
arguments, but are nevertheless safe, in the sense that no malicious code can be
called.

.. autoclass:: ForeachProcessor

.. autoclass:: IncludeProcessor

To specify the safety level used for template evaluation of the different
available processors, the values of the :class:`SafetyLevel` enum can be used:

.. autoclass:: SafetyLevel

"""
import abc
import ast
import collections
import functools
import logging

import lxml.etree as etree

import xsltea.errors
import xsltea.exec
from .processor import TemplateProcessor
from .namespaces import shared_ns

logger = logging.getLogger(__name__)

@functools.total_ordering
class SafetyLevel:
    """
    Enum for the safety level of template evaluation. Three different safety
    levels exist:

    .. attribute:: conservative

    .. attribute:: experimental

    .. attribute:: unsafe
    """

    safety = None

    def __lt__(self, other):
        return self.safety < other.safety

    def __le__(self, other):
        return self.safety <= other.safety

    def __eq__(self, other):
        return type(self) == type(other)

    def __ne__(self, other):
        return not (self == other)

    @abc.abstractmethod
    def _check_safety(self, ast):
        """
        Check whether the given *ast* object is safe. If it is safe,
        :data:`True` must be returned. If it is unsafe, the method must either
        return :data:`False` or raise a :class:`ValueError` explaining why it is
        not safe.

        Subclasses must implement this.

        **Do not call this directly**, but instead use :meth:`check_safety`.
        """

    def check_safety(self, ast):
        """
        Check the given *ast* for safety. Raises :class:`ValueError` if it is
        not considered safe.
        """

        if not self._check_safety(ast):
            raise ValueError("The code passed is not allowed in the current"
                             " safety restrictions ({!s})".format(self))

    def check_code_safety(self, src, mode="exec"):
        nodes = compile(src, "", mode, ast.PyCF_ONLY_AST).body
        if mode == "exec":
            for item in nodes:
                self.check_safety(item)
        else:
            self.check_safety(nodes)

    def compile_ast(self, ast, filename, mode):
        """
        Checks if the given *ast* object is safe with respect to the safety
        constraints defined by the subclass. If it is safed, it is passed
        together with the other arguments to the python :func:`compile`
        builtin.

        For a definition of *safe* with respect to the given safety-level, see
        the respective subclass’ :meth:`check_safety` implementation (or
        documentation).
        """

        if isinstance(ast, str):
            raise TypeError("First argument to compile_ast must be an ast")

        self.check_safety(ast)

        return compile(ast, filename, mode)

class _Experimental(SafetyLevel):
    """
    The experimental safety level allows the following constructs:

    * ``a`` is safe, if ``a`` does not start with an underscore
    * String, integer and float literals are safe
    * List, dict and tuple literals consisting of safe elements are
      considered safe
    * ``None`` is considered safe
    * accessing attributes is considered safe, if the attribute name
      does not start with an underscore

    Let ``a``, ``b``, ``c`` and ``d`` be safe, then:

    * ``a[b]``, ``a[b:c]``, ``a[b:c:d]`` (and any permutations) are
      considered safe
    * ``a X b`` with a binary operator ``X`` is considered safe
    * ``X a`` with an unary operator ``X`` is considered safe
    * ``a if b else c`` is considered safe
    """

    safety = -1

    def _check_safety(self, node):
        if node is None:
            return True
        elif isinstance(node, (ast.Expr)):
            return self._check_safety(node.value)
        elif isinstance(node, (ast.Name)):
            if node.id.startswith("_"):
                raise ValueError("Names starting with underscores are not"
                                 " allowed")
            return True
        elif isinstance(node, (ast.Str, ast.Num)):
            return True
        elif isinstance(node, (ast.Tuple, ast.List)):
            return all(map(self._check_safety, node.elts))
        elif isinstance(node, (ast.Dict)):
            return (all(map(self._check_safety, node.keys)) and
                    all(map(self._check_safety, node.values)))
        elif isinstance(node, (ast.Subscript)):
            return (self._check_safety(node.slice) and
                    self._check_safety(node.value))
        elif isinstance(node, (ast.Slice)):
            return (self._check_safety(node.lower) and
                    self._check_safety(node.step) and
                    self._check_safety(node.upper))
        elif isinstance(node, (ast.Index)):
            return self._check_safety(node.value)
        elif isinstance(node, (ast.BinOp)):
            return (self._check_safety(node.left) and
                    self._check_safety(node.right))
        elif isinstance(node, (ast.UnaryOp)):
            return self._check_safety(node.operand)
        elif isinstance(node, (ast.IfExp)):
            return (self._check_safety(node.body) and
                    self._check_safety(node.orelse) and
                    self._check_safety(node.test))
        else:
            raise ValueError("Must not occur in {} expressions: {}".format(
                self, node))

    def __str__(self):
        return "experimental"

SafetyLevel.experimental = _Experimental()
del _Experimental

class _Conservative(SafetyLevel):
    """
    The conservative safety level allows literals, names and list/dict/tuple
    compounds consisting of these.
    """

    safety = 0

    def _check_safety(self, node):
        if isinstance(node, ast.Name):
            if node.id.startswith("_"):
                raise ValueError("Names starting with underscores are not allowed"
                                 " in conservative mode")
            return True
        elif isinstance(node, (ast.Str, ast.Num)):
            return True
        elif isinstance(node, (ast.Tuple, ast.List)):
            return all(map(self._check_safety, node.elts))
        elif isinstance(node, (ast.Dict)):
            return (all(map(self._check_safety, node.keys)) and
                    all(map(self._check_safety, node.values)))
        elif isinstance(node, (ast.Expr)):
            return self._check_safety(node.value)
        else:
            raise ValueError("Must not occur in {} expressions: {}".format(
                self, node))

    def __str__(self):
        return "conservative"

SafetyLevel.conservative = _Conservative()
del _Conservative

class _Unsafe(SafetyLevel):
    """
    This is **unsafe**. No checks are performed. Imports and everything are
    allowed.
    """

    safety = -100

    def _check_safety(self, node):
        return True

    def __str__(self):
        return "unsafe"

SafetyLevel.unsafe = _Unsafe()
del _Unsafe

class ForeachProcessor(TemplateProcessor):
    """
    The processor for the ``tea:for-each`` xml element provides a safe for-each
    loop for templates.

    It treats the name given in ``@tea:from`` as an iterable, from which each
    item will be bound to the expression given in ``@tea:bind``. The expression
    must only consist of valid python names and possibly tuples. The name from
    ``@tea:from`` will be evaluated in the scope of the ``tea:for-each``
    element.

    For each item of the iterable, the expression from ``@tea:bind`` will be
    evaluated as if it was on the right side of an assignment, assigning the
    item from the iterable. A deep copy of all elements in the ``tea:for-each``
    element is created and the names obtained from the above evaluation are put
    in their local scopes, so that their values can be used further.

    The elements are returned and inserted at the place where the
    ``tea:for-each`` element was.

    The :class:`ForeachProcessor` requires the
    :class:`~xsltea.exec.ScopeProcessor` and is executed after the
    :class:`~xsltea.exec.ExecProcessor` (if it is loaded).
    """

    REQUIRES = []
    AFTER = [xsltea.exec.ExecProcessor]

    xmlns = shared_ns
    namespaces = {"tea": str(xmlns)}

    def __init__(self, safety_level=SafetyLevel.conservative, **kwargs):
        super().__init__(**kwargs)
        self._safety_level = safety_level
        self.attrhooks = {}
        self.elemhooks = {
            (str(self.xmlns), "for-each"): [self.handle_foreach]}

    def handle_foreach(self, template, elem, filename, offset):
        try:
            from_ = elem.attrib[getattr(self.xmlns, "from")]
            bind = elem.attrib[self.xmlns.bind]
        except KeyError as err:
            raise ValueError(
                "missing required attribute on tea:for-each: @tea:{}".format(
                    str(err).split("}", 1)[1]))

        childfun_name = "children{}".format(offset)
        precode = template.compose_childrenfun(elem, filename, childfun_name)

        elemcode = compile("""\
def _():
    for _ in _:
        yield ''
        yield from children{}()""".format(offset),
                       filename,
                       "exec",
                       ast.PyCF_ONLY_AST).body[0].body

        loop = elemcode[0]

        bind_ast = compile(bind,
                           filename,
                           "eval",
                           ast.PyCF_ONLY_AST).body
        self._prepare_bind_tree(bind_ast)

        iter_ast = compile(from_,
                           filename,
                           "eval",
                           ast.PyCF_ONLY_AST).body

        self._safety_level.check_safety(iter_ast)

        loop.iter = iter_ast
        loop.target = bind_ast

        loopbody = loop.body

        if not precode:
            del loopbody[1]

        if elem.text:
            loopbody[0].value.value = ast.Str(elem.text,
                                              lineno=elem.sourceline,
                                              col_offset=0)
        else:
            del loopbody[0]

        if not loopbody:
            del elemcode[0]

        elemcode.extend(template.preserve_tail_code(elem, filename))

        return precode, elemcode, []

    def _prepare_bind_tree(self, subtree):
        if isinstance(subtree, ast.Name):
            subtree.ctx = ast.Store()
            return
        elif isinstance(subtree, ast.Tuple):
            subtree.ctx = ast.Store()
            for el in subtree.elts:
                self._prepare_bind_tree(el)
        else:
            raise ValueError("can only bind to a single name or nested tuples")


class IncludeProcessor(TemplateProcessor):
    """
    The ``tea:include`` element processor provides safe inclusion of other
    templates. The other template will be loaded as element tree and inserted as
    if it was part of the current template.

    The optional ``tea:xpath`` attribute allows to customize which parts of the
    template are included. All nodes matching the given xpath expression will be
    included in match-order at the point where the ``tea:include`` directive
    was.

    If the xpath expression requires additional namespaces, these can be set by
    passing a python dictionary expression to ``tea:nsmap``. The dictionary must
    be a literal expression.

    ``tea:source`` must be set to an identifier identifying the template to
    insert; the semantics of the identifier depend on the configured template
    loader, usually it is a file name.
    """

    xmlns = shared_ns

    def __init__(self, override_loader=None, **kwargs):
        super().__init__(**kwargs)
        self._override_loader = None

        self.attrhooks = {}
        self.elemhooks = {
            (str(self.xmlns), "include"): [self.handle_include]
        }

    def handle_include(self, template, elem, filename, offset):
        try:
            xpath = elem.get(self.xmlns.xpath, "/*")
            source = elem.attrib[self.xmlns.source]
            nsmap = elem.get(self.xmlns.nsmap, "{}")
        except KeyError as err:
            raise ValueError(
                "missing required attribute on tea:include: @tea:{}".format(
                    str(err).split("}", 1)[1]))

        loader = self._override_loader
        if loader is None:
            if not hasattr(template, "loader"):
                raise ValueError("Cannot include other template: no loader"
                                 " specified for current template and no override"
                                 " present")
            loader = template.loader

        tree = loader.get_template(source).tree
        elements = tree.xpath(xpath,
                              namespaces=ast.literal_eval(nsmap))

        offset = offset * 1000

        precode, elemcode, postcode = [], [], []
        for element in elements:
            elem_precode, elem_elemcode, elem_postcode = \
                template.parse_subtree(element, filename, offset)

            precode.extend(elem_precode)
            elemcode.extend(elem_elemcode)
            postcode.extend(elem_postcode)

        return precode, elemcode, postcode
