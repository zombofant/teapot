"""
Python code execution from XML
##############################

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
:class:`~xsltea.processor.Processor` subclass, put it in your
:attr:`~xsltea.processor.Processor.REQUIRES` attribute.

.. autoclass:: ScopeProcessor

"""

import logging

from .namespaces import NamespaceMeta, xml
from .processor import TemplateProcessor
from .utils import *
from .errors import TemplateEvaluationError

class ScopeProcessor(TemplateProcessor):
    def __init__(self, template, **kwargs):
        super().__init__(template, **kwargs)
        # a dictionary { element_id => { name => value} } which maps the
        # element_id to another dictionary containing the names defined at that
        # element.
        self._defines = {}
        self._globals = {}

    def _get_defines_for_element(self, element):
        return self._defines.get(self._template.get_element_id(element), {})

    def get_inherited_locals_for_element(self, element):
        """
        Retrieve the inherited locals for a given element by searching through
        the parent scopes. Returns a new dict.
        """

        logging.debug("finding inherited locals for %s",
                      self._template.get_element_id(element))
        locals_dict = {}
        for parent in reversed(list(element.iterancestors())):
            parent_dict = self._get_defines_for_element(parent)
            logging.debug("parent %s has %s",
                          self._template.get_element_id(parent),
                          parent_dict)
            locals_dict.update(parent_dict)

        logging.debug("all inherited locals: %s", locals_dict)

        return locals_dict

    def define_at_element(self, element, name, value):
        elemdict = self._defines.setdefault(
            self._template.get_element_id(element), {})
        logging.debug("%s: set %s to %r",
                      self._template.get_element_id(element),
                      name,
                      value)
        elemdict[name] = value

    def update_defines_for_element(self, element, new_defines):
        elemdict = self._defines.setdefault(
            self._template.get_element_id(element), {})
        logging.debug("%s: update with %r",
                      self._template.get_element_id(element),
                      new_defines)
        elemdict.update(new_defines)

    def get_globals(self):
        return self._globals

    def get_locals_dict_for_element(self, element):
        locals_dict = self.get_inherited_locals_for_element(element)
        locals_dict.update(self._get_defines_for_element(element))
        return locals_dict

    def process(self, tree, arguments):
        pass

ScopeProcessor.logger = logging.getLogger(ScopeProcessor.__qualname__)

class ExecProcessor(TemplateProcessor):
    REQUIRES = [ScopeProcessor]

    class xmlns(metaclass=NamespaceMeta):
        xmlns = "https://xmlns.zombofant.net/xsltea/exec"

    namespaces = {"exec": str(xmlns),
                  "xml": str(xml)}

    def __init__(self, template, **kwargs):
        super().__init__(template, **kwargs)

        # store environments for specific execution contexts
        self._precompiled_attributes = []
        self._precompiled_elements = []

        tree = template.tree
        scope = template.get_processor(ScopeProcessor)
        globals_dict = scope.get_globals()

        for global_attr in tree.xpath("//@exec:global",
                                      namespaces=self.namespaces):
            parent = global_attr.getparent()
            exec(global_attr, globals_dict, globals_dict)

            del parent.attrib[global_attr.attrname]

        for with_attr in tree.xpath("//@exec:local", namespaces=self.namespaces):
            parent = with_attr.getparent()
            locals_dict = {}
            this_globals_dict = dict(globals_dict)
            this_globals_dict.update(
                scope.get_inherited_locals_for_element(parent))
            exec(with_attr, this_globals_dict, locals_dict)
            scope.update_defines_for_element(parent, locals_dict)

            del parent.attrib[with_attr.attrname]

        # precompile the remaining attributes
        for eval_attr in tree.xpath("//@*[namespace-uri() = '{}']".format(
                self.xmlns)):
            parent = eval_attr.getparent()
            code = compile(eval_attr, template.name, 'eval')

            attrname = eval_attr.attrname.split("}", 1).pop()

            self._precompiled_attributes.append(
                (self._template.get_element_id(parent),
                 attrname,
                 code))

            del parent.attrib[eval_attr.attrname]

        # precompile exec:text elements
        for text_elem in tree.xpath("//exec:text",
                                    namespaces=self.namespaces):
            if len(text_elem):
                raise ValueError("{} must not have children".format(
                    self.xmlns.text))

            code = compile(text_elem.text, template.name, 'eval')
            self._precompiled_elements.append(
                (self._template.get_element_id(text_elem),
                 code))

    def process(self, tree, arguments):
        scope = self._template.get_processor(ScopeProcessor)
        globals_dict = dict(scope.get_globals())
        globals_dict.update(arguments)
        for element_id, attrname, code in self._precompiled_attributes:
            element = get_element_by_id(tree, element_id)

            locals_dict = scope.get_locals_dict_for_element(element)

            try:
                value = eval(code, globals_dict, locals_dict)
            except Exception as err:
                raise TemplateEvaluationError("failed to evaluate template") \
                    from err

            if value is not None:
                if not isinstance(value, str) and hasattr(value, "__iter__"):
                    value, ns = value
                    attrname = "{" + ns + "}" + attrname
                element.set(attrname, str(value))

        for element_id, code in self._precompiled_elements:
            element = get_element_by_id(tree, element_id)

            locals_dict = scope.get_locals_dict_for_element(element)

            try:
                value = eval(code, globals_dict, locals_dict)
            except Exception as err:
                raise TemplateEvaluationError("failed to evaluate template") \
                    from err

            if value is None:
                element.getparent().remove(element)
                continue
            value = str(value)
            if element.tail is not None:
                value += element.tail

            parent = element.getparent()

            prev = element.getprevious()
            if prev is None:
                if parent.text is None:
                    parent.text = value
                else:
                    parent.text += value
            else:
                if prev.tail is None:
                    prev.tail = value
                else:
                    prev.tail += value

            parent.remove(element)
