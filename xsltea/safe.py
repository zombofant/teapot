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

    def __init__(self, template, **kwargs):
        super().__init__(template, **kwargs)
        self._element_loops = {}

    def _check_ast_bind_tree(self, subtree):
        if isinstance(subtree, ast.Name):
            return
        elif isinstance(subtree, ast.Tuple):
            for el in subtree.elts:
                self._check_ast_bind_tree(el)
        else:
            raise ValueError("can only bind to a single name or nested tuples")

    def _compile_bind(self, bindstr):
        if _has_ast:
            return self._compile_bind_with_ast(bindstr)

        raise NotImplementedError("Non-AST fallback not implemented yet")

    def _compile_bind_with_ast(self, bindstr):
        # tree is a module
        tree = ast.parse(bindstr)
        if len(tree.body) != 1:
            raise ValueError("invalid syntax for tea:bind")

        expr = tree.body[0].value
        self._check_ast_bind_tree(expr)

        return self._construct_exec_binder(bindstr)

    def _compile_from(self, fromstr):
        if _has_ast:
            return self._compile_from_with_ast(fromstr)

        raise NotImplementedError("Non-AST fallback not implemented yet")

    def _compile_from_with_ast(self, fromstr):
        # tree is a module
        tree = ast.parse(fromstr)
        if len(tree.body) != 1:
            raise ValueError("invalid syntax for tea:from")

        expr = tree.body[0].value
        if not isinstance(expr, ast.Name):
            raise ValueError("tea:from only supports plain names")

        name = expr.id
        del expr
        del tree

        def _fetcher(globals_dict, locals_dict):
            try:
                return locals_dict[name]
            except KeyError:
                pass
            try:
                return globals_dict[name]
            except KeyError:
                pass
            raise NameError("name '{}' is not defined".format(name))

        return _fetcher

    def _construct_exec_binder(self, tuple_expr):
        code = compile(tuple_expr + "=item", self._template.name, "exec")
        def _exec_binder(item):
            my_globals = {"item": item}
            my_locals = dict()
            exec(code, my_globals, my_locals)
            return my_locals
        return _exec_binder

    def _foreach(self, binder, fetcher, template_tree, element, arguments):
        logger.debug("for-each at element %s with name %s",
                     template_tree.get_element_name(element),
                     template_tree.get_element_id(element))
        scope = template_tree.get_processor(xsltea.exec.ScopeProcessor)
        globals_dict = scope.get_globals()
        locals_dict = scope.get_locals_dict_for_element(element)
        logger.debug("with scope: locals: %s", locals_dict)

        iterable = fetcher(globals_dict, locals_dict)
        subtree_template = list(element)
        in_text = element.text
        post_text = element.tail

        try:
            for item in iterable:
                if in_text:
                    yield in_text
                if subtree_template:
                    these_locals = dict(locals_dict)
                    bound = binder(item)
                    these_locals.update(bound)
                    subtree = list(map(
                        template_tree.deepcopy_subtree, subtree_template))
                    iterable = iter(subtree)
                    first = next(iterable)
                    scope.update_defines_for_element(first, these_locals)
                    yield first
                    for item in iterable:
                        scope.share_scope_with(item, first)
                        yield item
            if post_text:
                yield post_text

        except ValueError as err:
            raise xsltea.errors.TemplateEvaluationError(
                "failed to bind item to names") from err

    def preprocess(self):
        scope = self._template.get_processor(xsltea.exec.ScopeProcessor)
        tree = self._template.tree
        for foreach_elem in tree.xpath("//tea:for-each",
                                       namespaces=self.namespaces):
            bind_attr = foreach_elem.get(self.xmlns.bind)
            from_attr = foreach_elem.get(getattr(self.xmlns, "from"))

            binder = self._compile_bind(bind_attr)
            fetcher = self._compile_from(from_attr)

            self._template.hook_element_by_name(
                foreach_elem,
                type(self),
                functools.partial(
                    self._foreach,
                    binder,
                    fetcher))
