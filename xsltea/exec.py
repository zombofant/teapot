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
:class:`~xsltea.processor.TemplateProcessor` subclass, put it in your
:attr:`~xsltea.processor.TemplateProcessor.REQUIRES` attribute. It can then,
just like any other processor, be accessed via the
:meth:`~xsltea.Template.get_processor`.

.. autoclass:: ScopeProcessor
   :members:

"""

import functools
import logging

from .namespaces import NamespaceMeta, xml
from .processor import TemplateProcessor
from .utils import *
from .errors import TemplateEvaluationError

logger = logging.getLogger(__name__)

class ScopeProcessor(TemplateProcessor):
    """
    The scope processor implements scoping of python values with xml
    elements. It is not very useful on its own, but it is definetly helpful for
    implementing anything using python values related to the xml tree.

    Each element has a dictionary mapping names to values (just like python
    scopes). In addition to that, there is a global scope. The
    :meth:`get_locals_dict_for_element` method allows to retrieve a dictionary
    which contains all parents locals and the locals of the element (handling
    duplicates such that more nested definitions override the outer
    definitions).

    :meth:`define_at_element` and :meth:`update_defines_for_element` can be used
    to define names at a given element (and thus, make them available at the
    element and its descendant elements).
    """

    def __init__(self, template, **kwargs):
        super().__init__(template, **kwargs)
        # a dictionary { element_id => { name => value} } which maps the
        # element_id to another dictionary containing the names defined at that
        # element.
        self._defines = {}
        self._globals = {}

    def _get_defines_for_element(self, element):
        return self._defines.get(self._template.get_element_id(element), {})

    def _update_global_scope_with_arguments(
            self,
            template_tree, hooked_element, arguments):
        # grants us access to our context instance
        scope = template_tree.get_processor(ScopeProcessor)
        scope.get_globals().update(arguments)

    def get_inherited_locals_for_element(self, element):
        """
        Retrieve the inherited locals for a given element by searching through
        the parent scopes. Returns a new dict.
        """

        logger.debug("finding inherited locals for %s",
                      self._template.get_element_id(element))
        locals_dict = {}
        for parent in reversed(list(element.iterancestors())):
            parent_dict = self._get_defines_for_element(parent)
            logger.debug("parent %s has %s",
                          self._template.get_element_id(parent),
                          parent_dict)
            locals_dict.update(parent_dict)

        logger.debug("all inherited locals: %s", locals_dict)

        return locals_dict

    def define_at_element(self, element, name, value):
        """
        Define a new *name* with the given *value* at a given *element*, making
        it available in that elements locals and in all childrens scopes.
        """

        elemdict = self._defines.setdefault(
            self._template.get_element_id(element), {})
        logger.debug("%s: set %s to %r",
                      self._template.get_element_id(element),
                      name,
                      value)
        elemdict[name] = value

    def share_scope_with(self, source_element, dest_element):
        source_dict = self._defines.setdefault(
            self._template.get_element_id(source_element), {})
        self._defines[self._template.get_element_id(dest_element)] = source_dict

    def update_defines_for_element(self, element, new_defines):
        """
        Set all the names from the *new_defines* dictionary to their associated
        values at the given *element*.
        """

        elemdict = self._defines.setdefault(
            self._template.get_element_id(element), {})
        logger.debug("%s: update with %r",
                      self._template.get_element_id(element),
                      new_defines)
        elemdict.update(new_defines)

    def get_context(self, evaluation_template):
        new_scope = ScopeProcessor(evaluation_template)
        new_scope._defines.update(self._defines)
        new_scope._globals.update(self._globals)
        return new_scope

    def get_globals(self):
        return self._globals

    def get_locals_dict_for_element(self, element):
        """
        Return a new dict combining the inherited locals of the *element* with
        its own definitions, yielding a suitable local scope for evaluation.
        """
        locals_dict = self.get_inherited_locals_for_element(element)
        locals_dict.update(self._get_defines_for_element(element))
        return locals_dict

    def preprocess(self):
        self._template.hook_element_by_id(
            self._template.tree.getroot(),
            ScopeProcessor,
            self._update_global_scope_with_arguments)

    def process(self, tree, arguments):
        pass

class ExecProcessor(TemplateProcessor):
    REQUIRES = [ScopeProcessor]

    class xmlns(metaclass=NamespaceMeta):
        xmlns = "https://xmlns.zombofant.net/xsltea/exec"

    namespaces = {"exec": str(xmlns)}

    def _eval_attribute(self, code, attrname, template_tree, element, arguments):
        scope = template_tree.get_processor(ScopeProcessor)
        globals_dict = scope.get_globals()
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

    def _eval_text(self, code, template_tree, element, arguments):
        scope = template_tree.get_processor(ScopeProcessor)
        globals_dict = scope.get_globals()
        locals_dict = scope.get_locals_dict_for_element(element)

        try:
            value = eval(code, globals_dict, locals_dict)
        except Exception as err:
            raise TemplateEvaluationError("failed to evaluate template") \
                from err

        if value is None:
            return []

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

        return []

    def preprocess(self):
        template = self._template
        scope = template.get_processor(ScopeProcessor)
        tree = self._template.tree
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

            self._template.hook_element_by_name(
                parent, ExecProcessor,
                functools.partial(
                    self._eval_attribute,
                    code,
                    attrname))

            del parent.attrib[eval_attr.attrname]

        # precompile exec:text elements
        for text_elem in tree.xpath("//exec:text",
                                    namespaces=self.namespaces):
            if len(text_elem):
                raise ValueError("{} must not have children".format(
                    self.xmlns.text))

            code = compile(text_elem.text, template.name, 'eval')

            self._template.hook_element_by_name(
                text_elem, ExecProcessor,
                functools.partial(
                    self._eval_text,
                    code))
