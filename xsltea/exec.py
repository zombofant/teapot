from .namespaces import NamespaceMeta, xml
from .processor import NamespaceProcessor
from .utils import *
from .errors import TemplateEvaluationError

class ExecProcessor(NamespaceProcessor):
    class xmlns(metaclass=NamespaceMeta):
        xmlns = "https://xmlns.zombofant.net/xsltea/exec"

    namespaces = {"exec": str(xmlns),
                  "xml": str(xml)}

    def _get_locals_for_element(self, element):
        """
        Returns the **stored** locals for the given *element*. This raises a
        :class:`KeyError` if the element has no locals associated yet.
        """
        return self._locals_by_element[self._template.get_element_id(element)]

    def _get_processing_locals_for_element(self, element):
        try:
            locals_dict = self._get_locals_for_element(element)
        except KeyError:
            locals_dict = self._inherit_locals_for_element(element)
        return locals_dict

    def _inherit_locals_for_element(self, element):
        """
        Retrieve the inherited locals for a given element by searching through
        the parent scopes. Returns a new dict.
        """

        locals_dict = {}
        element_id = self._template.get_element_id(element)
        for parent in reversed(list(element.iterancestors())):
            parent_id = self._template.get_element_id(parent)
            try:
                parent_dict = self._get_locals_for_element(parent)
            except KeyError:
                continue

            locals_dict.update(parent_dict)

        return locals_dict

    def _set_locals_for_element(self, element, locals_dict):
        """
        Override (or set) the stored locals for the given *element* with the
        given *locals_dict*.
        """
        element_id = self._template.get_element_id(element)
        self._locals_by_element[element_id] = locals_dict

    def __init__(self, template, **kwargs):
        super().__init__(template, **kwargs)

        # store environments for specific execution contexts
        self._locals_by_element = {}
        self._precompiled_attributes = []
        self._precompiled_elements = []
        self._globals = {}

        tree = template.tree
        for global_attr in tree.xpath("//@exec:global",
                                      namespaces=self.namespaces):
            parent = global_attr.getparent()
            exec(global_attr, self._globals, self._globals)

            del parent.attrib[global_attr.attrname]

        for with_attr in tree.xpath("//@exec:local", namespaces=self.namespaces):
            parent = with_attr.getparent()
            locals_dict = self._inherit_locals_for_element(parent)
            exec(with_attr, self._globals, locals_dict)
            self._set_locals_for_element(parent, locals_dict)

            del parent.attrib[with_attr.attrname]

        # precompile the remaining attributes
        for eval_attr in tree.xpath("//@*[namespace-uri() = '{}']".format(
                self.xmlns)):
            parent = eval_attr.getparent()
            code = compile(eval_attr, template.filename, 'eval')

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

            code = compile(text_elem.text, template.filename, 'eval')
            self._precompiled_elements.append(
                (self._template.get_element_id(text_elem),
                 code))

    def process(self, tree, arguments):
        globals_dict = dict(self._globals)
        globals_dict.update(arguments)
        for element_id, attrname, code in self._precompiled_attributes:
            element = get_element_by_id(tree, element_id)

            locals_dict = self._get_processing_locals_for_element(element)

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

            locals_dict = self._get_processing_locals_for_element(element)

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
