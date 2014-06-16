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
import weakref

import lxml.etree as etree

import xsltea.errors
import xsltea.exec
import xsltea.template
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

class BranchingProcessor(TemplateProcessor):
    """
    The processor for ``tea:if`` and ``tea:switch``/``tea:case``/``tea:default``
    xml elements provides a branching implemtation for control flow elements.

    On its own, it is pretty useless. Other processors must provide attribute
    hooks matching attributes on ``tea:if`` and ``tea:case`` (see
    :attr:`xsltea.processor.attrhooks` for details) to actually provide
    conditions to check against.
    """

    xmlns = shared_ns
    namespaces = {"tea": str(xmlns)}

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.attrhooks = {}
        self.elemhooks = {
            (str(self.xmlns), "switch"): [self.handle_switch],
            (str(self.xmlns), "if"): [self.handle_if]
        }

    @classmethod
    def lookup_hooks(cls, context, elemtag, attrtag):
        elemns, elemname = xsltea.template.split_tag(elemtag)
        attrns, attrname = xsltea.template.split_tag(attrtag)
        try:
            return context.attrhooks[elemns,
                                     elemname,
                                     attrns,
                                     attrname]
        except KeyError:
            pass

        try:
            return context.attrhooks[elemns,
                                     elemname,
                                     attrns,
                                     None]
        except KeyError:
            pass

        return []

    @classmethod
    def compose_condition(cls, template, elem, context, offset):
        precode, elemcode, postcode = [], [], []
        conditions = []
        for key, value in elem.attrib.items():
            handlers = cls.lookup_hooks(context, elem.tag, key)
            for handler in handlers:
                result = handler(template, elem, key, value, context)
                if result:
                    break
            else:
                logger.warn("Unhandled attribute on {}: {}".format(
                    elem, key))
                continue

            attr_precode, attr_elemcode, attr_keycode, attr_valuecode, \
                attr_postcode = result

            if attr_keycode is not None:
                logger.warn("Attribute handler returned keycode for "
                            "conditional attribute")

            if not attr_valuecode or hasattr(attr_valuecode, "__iter__"):
                raise ValueError("Condition {} returned invalid valuecode:"
                                 " {}".format(key, attr_valuecode))

            precode.extend(attr_precode)
            elemcode.extend(attr_elemcode)
            conditions.append(attr_valuecode)
            postcode.extend(attr_postcode)

        if not conditions:
            raise ValueError("Conditional element without conditions "
                             "({}:{})".format(context.filename,
                                              elem.sourceline or 0))

        conditioncode = functools.reduce(
            lambda prev, curr: ast.BinOp(
                prev,
                ast.And(),
                curr,
                lineno=elem.sourceline or 0,
                col_offset=0),
            conditions[1:],
            conditions[0])

        return precode, elemcode, conditioncode, postcode

    @classmethod
    def create_forward(cls, body, elem, childfun_name):
        if elem.text:
            body.append(
                ast.Expr(
                    ast.Yield(
                        ast.Str(
                            elem.text,
                            lineno=elem.sourceline or 0,
                            col_offset=0),
                        lineno=elem.sourceline or 0,
                        col_offset=0),
                    lineno=elem.sourceline or 0,
                    col_offset=0)
            )

        if childfun_name:
            body.append(
                ast.Expr(
                    ast.YieldFrom(
                        ast.Call(
                            ast.Name(
                                childfun_name,
                                ast.Load(),
                                lineno=elem.sourceline or 0,
                                col_offset=0),
                            [],
                            [],
                            None,
                            None,
                            lineno=elem.sourceline or 0,
                            col_offset=0),
                        lineno=elem.sourceline or 0,
                        col_offset=0),
                    lineno=elem.sourceline or 0,
                    col_offset=0)
            )

    @classmethod
    def create_conditional(cls, template, elem, context, offset):
        precode, elemcode, conditioncode, postcode = cls.compose_condition(
            template, elem, context, offset)

        childfun_name = "children{}".format(offset)
        # prepend childfun to existing precode
        childfun_code = template.compose_childrenfun(
            elem,
            context,
            childfun_name)
        if childfun_code:
            precode[:0] = childfun_code

        body = []
        cls.create_forward(body,
                           elem,
                           childfun_name if childfun_code else "")

        if body:
            elemcode.insert(
                0,
                ast.If(
                    conditioncode,
                    body,
                    [],
                    lineno=elem.sourceline or 0,
                    col_offset=0))


        return precode, elemcode, postcode

    def handle_if(self, template, elem, context, offset):
        return self.create_conditional(template, elem, context, offset)

    def handle_switch(self, template, elem, context, offset):
        case_tag = self.xmlns.case
        default_tag = self.xmlns.default

        children = iter(elem)
        branches = []
        default = None
        for child in children:
            if default is not None:
                raise ValueError("tea:switch contains elements after tea:default")
            if child.tag != case_tag:
                if child.tag == default_tag:
                    default = child
                    continue
                raise ValueError("Unknown element in tea:switch: {}".format(
                    child.tag))

            branches.append(child)

        precode = []
        elemcode = []
        postcode = []

        branch_code = []

        for i, branch in enumerate(branches):
            cond_precode, cond_elemcode, cond_code, cond_postcode = \
                self.compose_condition(template, branch, context, offset)

            precode.extend(cond_precode)
            elemcode.extend(cond_elemcode)
            postcode[:0] = cond_postcode

            childfun_name = "children{}_{}".format(offset, i)
            branch_code.append((
                # condition code
                cond_code,
                # child
                branch,
                # childfun_name,
                childfun_name,
                # childcode
                template.compose_childrenfun(
                    branch,
                    context,
                    childfun_name)))

        if default is not None:
            childfun_name = "children{}_default".format(offset)
            branch_code.append((
                None,
                default,
                childfun_name,
                template.compose_childrenfun(
                    default,
                    context,
                    childfun_name)))

        elemcode = []
        else_branch = elemcode
        for condition_code, child, childfun_name, childfun in branch_code:
            if condition_code is not None:
                if_branch = []
                new_else_branch = []
                else_branch.append(
                    ast.If(
                        condition_code,
                        if_branch,
                        new_else_branch,
                        lineno=child.sourceline or 0,
                        col_offset=0))
                else_branch = new_else_branch
            else:
                if_branch = else_branch

            self.create_forward(
                if_branch,
                elem,
                childfun_name if childfun else "")

            precode.extend(childfun)

        return precode, elemcode, postcode



class ForeachProcessor(TemplateProcessor):
    """
    The processor for the ``tea:for-each`` xml element provides a safe for-each
    loop for templates.

    It treats the name given in ``@from`` as an iterable, from which each
    item will be bound to the expression given in ``@bind``. The expression
    must only consist of valid python names and possibly tuples. The name from
    ``@from`` will be evaluated in the scope of the ``tea:for-each``
    element.

    For each item of the iterable, the expression from ``@bind`` will be
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

    @classmethod
    def create_foreach(cls, template, elem, context, offset,
                       bind_ast, iter_ast):
        """
        Create *precode*, *elemcode* and *postcode* for a for-loop as for
        example created by tea:for-each.

        Besides the usual hook arguments, it requires AST nodes which provide
        (a) the iterable over which to iterate and (b) the tuple of names or the
        name to bind each iteration turns result to (that is, the part which
        usually is between the ``for`` and the ``in`` in python), passed as
        arguments to *iter_ast* and *bind_ast*.

        It is expected that both ASTs have already been checked for safety by
        the caller. The *bind_ast* must be in :class:`ast.Save` context.

        The loops body is created from the children of *elem*, just like with
        ``tea:for-each``.

        Returns a tuple of lists which contain the *precode*, *elemcode* and
        *postcode*.
        """
        childfun_name = "children{}".format(offset)
        precode = template.compose_childrenfun(elem, context, childfun_name)

        elemcode = compile("""\
def _():
    for _ in _:
        yield ''
        yield from children{}()""".format(offset),
                       context.filename,
                       "exec",
                       ast.PyCF_ONLY_AST).body[0].body

        loop = elemcode[0]

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

        elemcode.extend(template.preserve_tail_code(elem, context))

        return precode, elemcode, []

    def handle_foreach(self, template, elem, context, offset):
        try:
            from_ = elem.attrib["from"]
            bind = elem.attrib["bind"]
        except KeyError as err:
            raise ValueError(
                "missing required attribute on tea:for-each: @{}".format(err))

        bind_ast = compile(bind,
                           context.filename,
                           "eval",
                           ast.PyCF_ONLY_AST).body
        self._prepare_bind_tree(bind_ast)

        iter_ast = compile(from_,
                           context.filename,
                           "eval",
                           ast.PyCF_ONLY_AST).body

        self._safety_level.check_safety(iter_ast)

        return self.create_foreach(
            template, elem, context, offset,
            bind_ast, iter_ast)

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

    The optional ``@xpath`` attribute allows to customize which parts of the
    template are included. All nodes matching the given xpath expression will be
    included in match-order at the point where the ``tea:include`` directive
    was.

    If the xpath expression requires additional namespaces, these can be set by
    passing a python dictionary expression to ``@nsmap``. The dictionary must
    be a literal expression.

    ``@src`` must be set to an identifier identifying the template to
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

    def handle_include(self, template, elem, context, offset):
        try:
            xpath = elem.get("xpath", "/*")
            source = elem.attrib["src"]
            nsmap = elem.get("nsmap", "{}")
        except KeyError as err:
            raise ValueError(
                "missing required attribute on tea:include: @{}".format(err))

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
                template.parse_subtree(element, context, offset)

            precode.extend(elem_precode)
            elemcode.extend(elem_elemcode)
            postcode.extend(elem_postcode)

        return precode, elemcode, postcode


class FunctionProcessor(TemplateProcessor):
    """
    The function processor allows to define functions inside templates. The
    definition does not generate any elements (but preserves tail text). Upon
    calling, the effect is similar to inserting the tree at the given position,
    but slightly different. The tree is only compiled once, so that recursion is
    possible without running into an infinite loop.

    Defining a function is done using a ``tea:def`` element. The ``tea:def``
    element may contain zero or more ``tea:arg`` elements, each declaring an
    argument of the function. The ``@name`` attribute is required, it defines
    the argument name. Argument names must not start with ``_`` and must be
    valid python identifiers.

    Arguments can be given a static (``mode="static"``, the default) or lazily
    evaluated (``mode="lazy"``) default value. Static default values only allow
    python literals, without any further expressions, because they are evaluated
    at parse-time. Lazily evaluated values are evaluated in the context of the
    *caller* right before calling. The evaluation is subject to the
    *safety_level* of the processor.

    Any elements and any text besides ``tea:arg`` elements are taken as body of
    the function and will be replicated upon calling.

    XML Syntax example::

        <?xml version="1.0" ?>
        …
        <tea:def xmlns:tea="https://xmlns.zombofant.net/xsltea/processors"
                 name="foo">
          <!-- declare required argument named `a` -->
          <tea:arg name="a" />
          <!-- declare argument named `b`, with default "foo" -->
          <tea:arg mode="static" name="b" value="'foo' />
          <!-- declare argument named `b`, with the default evaluated in
               the scope of the *caller* -->
          <tea:arg mode="lazy" name="b" value="arguments['some_arg']" />
          <!-- function body ... -->
        </tea:def>
        …

    To call a function, one uses an ``tea:call``. It must only contain
    ``tea:pass`` elements, which define the arguments explicitly passed to the
    function.

    Each ``tea:pass`` element requires a ``name`` attribute, which refers to the
    argument name to which the value shall be passed. The value is described by
    the elements text, which is evaluated with the *safety_level* of the
    processsor.

    For more usage examples see the tests.
    """

    xmlns = shared_ns

    staticmode = {
        "static": True,
        "lazy": False
    }

    template_libraries = weakref.WeakKeyDictionary()

    prohibited_names = {
        "utils",
        "context",
    }

    class Function:
        implicit_arguments = [
            "context",
        ]

        def __init__(self, name, arguments, safety_level, context):
            static_defaults = {}
            lazy_defaults = {}
            argnames = set()
            for argname, (static, default) in arguments:
                argnames.add(argname)
                if not default:
                    continue
                default = default[0]
                if static:
                    default = ast.literal_eval(default)
                    static_defaults[argname] = default
                else:
                    default = compile(
                        default,
                        context.filename,
                        "eval",
                        ast.PyCF_ONLY_AST).body
                    safety_level.check_safety(default)
                    lazy_defaults[argname] = default

            self.name = name
            self.arguments = frozenset(argnames)
            self.static_defaults = static_defaults
            self.lazy_defaults = lazy_defaults

            self._prototype = compile("""\
def func(utils, context, {}):
    pass""".format(
        ", ".join(self.arguments)),
                              context.filename,
                              "exec",
                              ast.PyCF_ONLY_AST)

        def finalize_body(self, template, body, context):
            def_ast = self._prototype
            def_ast.body[0].body[:] = body

            globals_dict = dict(globals())
            locals_dict = {}

            def_code = compile(def_ast, context.filename, "exec")
            exec(def_code, globals_dict, locals_dict)
            self._func = functools.partial(
                locals_dict["func"],
                template.utils)


        def compose_call(self, template, argumentmap, context, sourceline):
            arguments = {}
            arguments.update({
                k: compile(
                    repr(v),
                    context.filename,
                    "eval",
                    ast.PyCF_ONLY_AST).body
                for k, v in self.static_defaults.items()})
            arguments.update(self.lazy_defaults)
            arguments.update(argumentmap)

            missing_arguments = self.arguments - set(arguments.keys())
            if missing_arguments:
                raise ValueError(
                    "Missing arguments to {}: {}".format(
                        self.name,
                        ", ".join(missing_arguments)))

            argscode = ast.Dict([], [], lineno=sourceline, col_offset=0)
            for name, value_ast in arguments.items():
                argscode.keys.append(ast.Str(
                    name,
                    lineno=sourceline,
                    col_offset=0))
                argscode.values.append(value_ast)

            # yield from self(**arguments)
            return [ast.Expr(
                ast.YieldFrom(
                    ast.Call(
                        template.ast_get_stored(
                            template.store(self),
                            sourceline),
                        [
                            ast.Name(
                                argname,
                                ast.Load(),
                                lineno=sourceline,
                                col_offset=0)
                            for argname in self.implicit_arguments
                        ],
                        [],
                        None,
                        argscode,
                        lineno=sourceline,
                        col_offset=0),
                    lineno=sourceline,
                    col_offset=0),
                lineno=sourceline,
                col_offset=0)]

        def __call__(self, *args, **kwargs):
            return self._func(*args, **kwargs)

    def __init__(self,
                 safety_level=SafetyLevel.conservative,
                 override_loader=None,
                 **kwargs):
        super().__init__(**kwargs)
        self._safety_level = safety_level
        self._override_loader = override_loader
        self.attrhooks = {}
        self.elemhooks = {
            (str(self.xmlns), "def"): [self.handle_def],
            (str(self.xmlns), "call"): [self.handle_call],
            (str(self.xmlns), "arg"): [
                functools.partial(
                    self.handle_use_outside_def_or_call,
                    "tea:def")
            ],
            (str(self.xmlns), "pass"): [
                functools.partial(
                    self.handle_use_outside_def_or_call,
                    "tea:call")
            ],
        }

    def handle_use_outside_def_or_call(self, legitimate,
                                       template, elem, context, offset):
        raise ValueError("tea:{} was used outside {}".format(
            elem.tag.split("}", 1)[1],
            legitimate))

    def swallow_elem(self, template, elem, context, offset):
        return [], template.preserve_tail_code(elem, context), []

    def _check_no_children(self, elem, name):
        if len(elem):
            raise ValueError("No children allowed for {}".format(
                name))

    def handle_def(self, template, elem, context, offset):
        try:
            name = elem.attrib["name"]
        except KeyError as err:
            raise ValueError("Missing required attribute on tea:def:"
                             " @{}".format(str(err).split("}")[1]))

        library = self.template_libraries.setdefault(template, {})

        arguments = {}
        for argumentelem in elem.findall(self.xmlns.arg):
            self._check_no_children(argumentelem, "tea:arg")
            if argumentelem.text or len(argumentelem):
                raise ValueError("tea:arg must be empty")

            attrib = dict(argumentelem.attrib)

            try:
                argname = attrib.pop("name")
            except KeyError as err:
                raise ValueError("Missing required attribute on tea:arg: "
                                 "@{}".format(str(err)))

            if argname in arguments:
                raise ValueError("Duplicate tea:arg element for argument"
                                 " {}".format(argname))

            if argname in self.prohibited_names:
                raise ValueError("Argument name not allowed: {}".format(
                    argname))

            if not argname.isidentifier() or argname.startswith("_"):
                raise ValueError("{} is not a valid argument name".format(
                    argname))

            try:
                static = self.staticmode[attrib.pop("mode", "static")]
            except KeyError as err:
                raise ValueError("Invalid value for tea:arg/@mode: {}".format(
                    err))
            try:
                default = attrib.pop("default")
            except KeyError as err:
                arguments[argname] = (static, ())
            else:
                arguments[argname] = (static, (default,))

            if attrib:
                raise ValueError("Unsupported attributes on tea:arg: {}".format(
                    ", ".join(attrib.keys())))

        func = self.Function(
            name,
            arguments.items(),
            self._safety_level,
            context)
        library[name] = func

        try:

            context.elemhooks[(str(self.xmlns), "arg")].insert(
                0,
                self.swallow_elem)
            try:
                body = template.build_childrenfun_body(elem, context)
            finally:
                context.elemhooks[(str(self.xmlns), "arg")].pop(0)
        except:
            del library[name]
            raise

        func.finalize_body(template, body, context)

        return [], template.preserve_tail_code(elem, context), []

    def handle_call(self, template, elem, context, offset):
        try:
            name = elem.attrib["name"]
            source = elem.get("src")
        except KeyError as err:
            raise ValueError("Missing required attribute on tea:call:"
                             " @tea:{}".format(str(err).split("}")[1]))

        if source is not None:
            loader = self._override_loader
            if loader is None:
                if not hasattr(template, "loader"):
                    raise ValueError("Cannot call function from other template:"
                                     " no loader specified for current template"
                                     " and no override present")
                loader = template.loader
            source_template = loader.get_template(source)
        else:
            source_template = template

        library = self.template_libraries.setdefault(source_template, {})

        try:
            func = library[name]
        except KeyError as err:
            if source is not None:
                raise ValueError("Function {} is not defined in {}".format(
                    str(err), source))
            else:
                raise ValueError("Function {} is not defined in this"
                                 " template".format(str(err)))

        arguments = {}
        for child in elem:
            if child.tag and child.tag != getattr(self.xmlns, "pass"):
                raise ValueError("Unexpected child {} to"
                                 " tea:call".format(elem.tag))
            if not child.tag:
                continue

            try:
                name = child.attrib["name"]
            except KeyError as err:
                raise ValueError(
                    "Missing required attribute on tea:pass: @{}".format(
                        str(err)))

            if name in self.prohibited_names:
                raise ValueError("Argument name not allowed: {}".format(
                    argname))

            if not child.text:
                raise ValueError("Text of tea:pass must be non-empty and a valid"
                                 " expression")

            value_ast = compile(child.text,
                                context.filename,
                                "eval",
                                ast.PyCF_ONLY_AST).body
            self._safety_level.check_safety(value_ast)
            arguments[name] = value_ast

        elemcode = func.compose_call(template,
                                     arguments,
                                     context,
                                     elem.sourceline or 0)
        elemcode.extend(template.preserve_tail_code(elem, context))

        return [], elemcode, []

class GlobalsProcessor(TemplateProcessor):
    """
    """

    def __init__(self,
                 safety_level=SafetyLevel.conservative,
                 override_loader=None,
                 **kwargs):
        super().__init__(**kwargs)
        self.attrhooks = {}
        self.elemhooks = {}
        self.names = {}

    def global_precode(self, template):
        for name, value in self.names.items():
            key = template.store(value)
            yield ast.Assign(
                [
                    ast.Name(
                        name,
                        ast.Store(),
                        lineno=0,
                        col_offset=0)
                ],
                template.ast_get_stored(key, 0),
                lineno=0,
                col_offset=0)
