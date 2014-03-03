"""
``xsltea.exec`` – Python code execution from XML
################################################

The :class:`ExecProcessor` is used to execute arbitrary python code from within
templates.

.. warning::

   By arbitrary code, I mean arbitrary code. Anything from ``print("You’re dumb")``
   to ``shutil.rmtree(os.path.expanduser("~"))``. Do **never ever** run
   templates from untrusted sources with :class:`ExecProcessor`.

.. highlight:: xml

The :class:`ExecProcessor` supports the following XML syntax::

    <?xml version="1.0" ?>
    <root xmlns:exec="https://xmlns.zombofant.net/xsltea/exec"
     ><exec:code>import os; foo='bar'</exec:code>
      <a exec:foo="'a' + 'b' * (2+3)" />
      <exec:text>23*2-4</exec:text>
      <b><exec:code>fnord='baz'</exec:code>
        <exec:text>fnord + foo + str(os)</exec:text>
      </b>
    </root>

The above XML will transform to the below XML when processed::

    <?xml version="1.0" ?>
    <root xmlns:exec="https://xmlns.zombofant.net/xsltea/exec">
      <a foo="abbbbb" />
      42
      <b>
        bazbar&lt;module 'os' from '/usr/lib64/python3.3/os.py'&gt;
      </b>
    </root>

The code for attributes and for ``exec:text`` is compiled in ``'eval'`` mode,
that is, only expressions are allowed (no statements). ``exec:code`` is compiled
in ``'exec'`` mode, allowing you to import modules and execute other statements.

Technically, the children of each element are grouped together into a function
scope, nested into the outer function scope. ``nonlocal`` and ``global`` will
work as expected under these circumstances and local scoping takes place.

Template arguments are available in a dictionary called ``arguments`` (see
:meth:`~xsltea.template.Template.process`).

.. highlight:: python

"""

import ast
import functools
import logging

from .namespaces import NamespaceMeta, xml
from .processor import TemplateProcessor
from .utils import *
from .errors import TemplateEvaluationError

logger = logging.getLogger(__name__)

class ExecProcessor(TemplateProcessor):
    REQUIRES = []

    class xmlns(metaclass=NamespaceMeta):
        xmlns = "https://xmlns.zombofant.net/xsltea/exec"

    namespaces = {"exec": str(xmlns)}

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.attrhooks = {
            (str(self.xmlns), None): [self.handle_exec_any_attribute]}
        self.elemhooks = {
            (str(self.xmlns), "code"): [self.handle_exec_code],
            (str(self.xmlns), "if"): [self.handle_exec_if],
            (str(self.xmlns), "text"): [self.handle_exec_text]}

    def handle_exec_any_attribute(self, template, elem, attrib, value, context):
        valuecode = compile(value,
                            context.filename,
                            "eval",
                            flags=ast.PyCF_ONLY_AST).body

        if isinstance(valuecode, ast.Tuple):
            # namespace is given
            if len(valuecode.elts) != 2:
                raise ValueError("unsupported amount of elements in attribute"
                                 " value tuple: {}".format(len(valuecode.elts)))

            keycode = valuecode.elts[1]
            valuecode = valuecode.elts[0]
        else:
            # strip namespace
            keycode = ast.Str(attrib.split("}", 1)[1],
                              lineno=elem.sourceline or 0,
                              col_offset=0)

        elemcode = compile("""\
attrval = ''
if attrval is not None:
    elem.set('', str(attrval))""",
                           context.filename,
                           "exec",
                           ast.PyCF_ONLY_AST).body

        elemcode[0].value = valuecode
        elemcode[1].body[0].value.args[0] = keycode

        return [], elemcode, None, None, []

    def handle_exec_code(self, template, elem, context, offset):
        precode = compile(elem.text,
                          context.filename,
                          "exec",
                          flags=ast.PyCF_ONLY_AST).body
        elemcode = template.preserve_tail_code(elem, context)
        return precode, elemcode, []

    def handle_exec_text(self, template, elem, context, offset):
        value = compile(elem.text,
                        context.filename,
                        "eval",
                        flags=ast.PyCF_ONLY_AST).body
        yielder = compile("yield str('')",
                          context.filename,
                          "exec",
                          flags=ast.PyCF_ONLY_AST).body[0]
        yielder.value.value.args[0] = value
        elemcode = template.preserve_tail_code(elem, context)
        elemcode.insert(0, yielder)
        return [], elemcode, []

    @classmethod
    def create_if(cls, template, elem, context, offset,
                  condition_ast):
        childfun_name = "children{}".format(offset)
        precode = template.compose_childrenfun(elem, context, childfun_name)

        elemcode = compile("""\
if _:
    yield ''
    yield from children{}()""".format(offset),
                           context.filename,
                           "exec",
                           ast.PyCF_ONLY_AST).body

        elemcode[0].test = condition_ast

        if not precode:
            del elemcode[0].body[1]

        if elem.text:
            elemcode[0].body[0].value.value = ast.Str(
                elem.text,
                lineno=elem.sourceline or 0,
                col_offset=0)
        else:
            del elemcode[0].body[0]

        if not elemcode[0].body:
            del elemcode[0]

        return precode, elemcode, []


    def handle_exec_if(self, template, elem, context, offset):
        attrib = elem.attrib
        try:
            condition_code = attrib["condition"]
        except KeyError:
            raise ValueError("exec:if requires @condition")
        condition_code = compile(condition_code,
                                 context.filename,
                                 "eval",
                                 ast.PyCF_ONLY_AST).body
        return self.create_if(template, elem, context, offset,
                              condition_code)
