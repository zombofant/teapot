"""
``xsltea.exec`` – Python code execution from XML
################################################

The :class:`ExecProcessor` is used to execute arbitrary python code from within
templates.

.. warning::

   By arbitrary code, I mean arbitrary code. Anything from ``print("You’re dumb")``
   to ``shutil.rmtree(os.path.expanduser("~"))``. Do **never ever** run
   templates from untrusted sources with :class:`ExecProcessor`.

   An alternative, which will allow restricted execution of python code, is on
   our todo.

.. highlight:: xml

The :class:`ExecProcessor` supports the following XML syntax::

    <?xml version="1.0" ?>
    <root xmlns:exec="https://xmlns.zombofant.net/xsltea/exec"
          exec:global="import os; foo='bar'">
      <a exec:foo="'a' + 'b' * (2+3)" />
      <exec:text>23*2-4</exec:text>
      <b exec:local="fnord='baz'">
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

Except for ``exec:local`` and ``exec:global`` attributes, the supplied python
code will be compiled in ``'eval'`` mode, that is, only expressions are allowed
(no statements). ``exec:local`` and ``exec:global`` are compiled in ``'exec'``
mode, allowing you to import modules and execute other statements.

Names defined in ``exec:local`` are available in attributes on the element
itself and all of its children. Names defined in ``exec:global`` are available
everywhere, but just like in python, ``exec:local`` takes precedence.

Template parameters are put in the global scope.

.. highlight:: python

Reusable scoping
================

As described above, the :class:`ExecProcessor` supports scopes in elements. This
can be reused for other modules without pulling the whole :class:`ExecProcessor`
as an (unsafe) dependency.

To use the :class:`ScopeProcessor` in your own
:class:`~xsltea.processor.TemplateProcessor` subclass, put it in your
:attr:`~xsltea.processor.TemplateProcessor.REQUIRES` attribute. It can then,
just like any other processor, be accessed via the
:meth:`~xsltea.Template.get_processor`.

.. autoclass:: ScopeProcessor
   :members:

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
            (str(self.xmlns), None): self.handle_exec_any_attribute}
        self.elemhooks = {
            (str(self.xmlns), "code"): self.handle_exec_code,
            (str(self.xmlns), "text"): self.handle_exec_text}

    def handle_exec_any_attribute(self, template, elem, attrib, value, filename):
        valuecode = compile(value,
                            filename,
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
                              lineno=elem.sourceline,
                              col_offset=0)

        return [], [], keycode, valuecode, []

    def handle_exec_code(self, template, elem, filename, offset):
        precode = compile(elem.text,
                          filename,
                          "exec",
                          flags=ast.PyCF_ONLY_AST).body
        elemcode = template.preserve_tail_code(elem, filename)
        return precode, elemcode, []

    def handle_exec_text(self, template, elem, filename, offset):
        value = compile(elem.text,
                        filename,
                        "eval",
                        flags=ast.PyCF_ONLY_AST).body
        yielder = compile("yield str('')",
                          filename,
                          "exec",
                          flags=ast.PyCF_ONLY_AST).body[0]
        yielder.value.value.args[0] = value
        elemcode = template.preserve_tail_code(elem, filename)
        elemcode.insert(0, yielder)
        return [], elemcode, []
