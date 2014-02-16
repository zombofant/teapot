"""
``xsltea.safe`` – Safe processors
#################################

This module provides some processors which deal with python names and template
arguments, but are nevertheless safe, in the sense that no malicious code can be
called.

.. autoclass:: ForeachProcessor

"""
try:
    import ast
    _has_ast = True
except ImportError:
    import keyword
    _has_ast = False

import functools
import logging

import lxml.etree as etree

import xsltea.errors
import xsltea.exec
from .processor import TemplateProcessor
from .namespaces import shared_ns

logger = logging.getLogger(__name__)

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

    def __init__(self, allow_unsafe=False, **kwargs):
        super().__init__(**kwargs)
        self._allow_unsafe = allow_unsafe
        self.attrhooks = {}
        self.elemhooks = {
            (str(self.xmlns), "for-each"): self.handle_foreach}

    def handle_foreach(self, template, elem, filename, offset):
        try:
            from_ = elem.attrib[getattr(self.xmlns, "from")]
            bind = elem.attrib[self.xmlns.bind]
        except KeyError as err:
            raise ValueError(
                "missing required attribute on tea:for-each: @tea:{}".format(
                    str(err).split("}", 1)[1]))

        childfun_name = "children{}".format(offset)
        precode = template.compose_childrenfun(elem, filename)
        if precode:
            precode[0].name = childfun_name

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

        if not self._allow_unsafe:
            if not isinstance(iter_ast, ast.Name):
                raise ValueError("in safe mode, only one plain Name is allowed "
                                 "in @tea:from")

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
