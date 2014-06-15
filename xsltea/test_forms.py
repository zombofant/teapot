import unittest

import teapot.forms

import xsltea.safe
import xsltea.forms

import lxml.etree as etree

from xsltea.namespaces import xhtml_ns

class Form(teapot.forms.Form):
    field = teapot.forms.IntField(default=10)

class TestFormProcessor(unittest.TestCase):
    xmlsrc_text_inputs = """<test xmlns="http://www.w3.org/1999/xhtml"
    xmlns:form="https://xmlns.zombofant.net/xsltea/form"
    form:form="arguments['form']">
    <input
        form:field="field"
        type="text" />
    </test>"""

    xmlsrc_box_inputs = """<test xmlns="http://www.w3.org/1999/xhtml"
    xmlns:form="https://xmlns.zombofant.net/xsltea/form"
    form:form="arguments['form']">
    <input
        form:field="field"
        type="checkbox" />
    </test>"""

    xmlsrc_radio_inputs = """<test
    xmlns="http://www.w3.org/1999/xhtml"
    xmlns:form="https://xmlns.zombofant.net/xsltea/form"
    form:form="arguments['form']">
    <input type="radio"
           form:field="field"
           value="1" />
    <input type="radio"
           form:field="field"
           value="2" />
    <input type="radio"
           form:field="field" />
</test>"""

    xmlsrc_textarea_inputs = """<test
    xmlns="http://www.w3.org/1999/xhtml"
    xmlns:form="https://xmlns.zombofant.net/xsltea/form"
    form:form="arguments['form']">
    <textarea form:field="field" rows="20" cols="100"/>
    </test>"""

    xmlsrc_if_has_error = """\
<test
    xmlns="http://www.w3.org/1999/xhtml"
    xmlns:form="https://xmlns.zombofant.net/xsltea/form"
    xmlns:exec="https://xmlns.zombofant.net/xsltea/exec"
    xmlns:tea="https://xmlns.zombofant.net/xsltea/processors">
    <exec:code>default_form = arguments["form"]</exec:code>
    <tea:if form:field-error="field">foo</tea:if>
</test>"""

    xmlsrc_for_each_error = """\
<test
    xmlns="http://www.w3.org/1999/xhtml"
    xmlns:form="https://xmlns.zombofant.net/xsltea/form">
    <form:for-each-error
        field="field"
        form="arguments['form']">foo</form:for-each-error>
</test>"""

    xmlsrc_for_field = """\
<test
    xmlns="http://www.w3.org/1999/xhtml"
    xmlns:form="https://xmlns.zombofant.net/xsltea/form">
    <label form:for="field" form:form="arguments['form']" />
</test>"""

    xmlsrc_action = """\
<test
    xmlns="http://www.w3.org/1999/xhtml"
    xmlns:form="https://xmlns.zombofant.net/xsltea/form">
    <input type="submit"
           form:form="arguments['form']"
           form:action="update" />
</test>"""


    def setUp(self):
        self._loader = xsltea.template.XMLTemplateLoader()
        self._loader.add_processor(
            xsltea.forms.FormProcessor(
                safety_level=xsltea.safe.SafetyLevel.unsafe))
        self._loader.add_processor(xsltea.exec.ExecProcessor())
        self._loader.add_processor(xsltea.safe.BranchingProcessor())

    def _load_xml(self, xmlstr):
        template = self._loader.load_template(xmlstr, "<string>")
        return template

    def _process_with_form(self, xmlstr, value=None):
        template = self._load_xml(xmlstr)
        form = Form()
        if value is not None:
            form.field = value
        tree = template.process({
            "form": form
        })
        return tree

    def test_text_inputs(self):
        tree = self._process_with_form(self.xmlsrc_text_inputs)
        input_elem = tree.getroot().find(xhtml_ns.input)
        self.assertEqual(
            "field",
            input_elem.get("name"))
        self.assertEqual(
            "10",
            input_elem.get("value"))

    def test_box_inputs(self):
        tree = self._process_with_form(
            self.xmlsrc_box_inputs,
            value=1)
        input_elem = tree.getroot().find(xhtml_ns.input)
        self.assertEqual(
            "field",
            input_elem.get("name"))
        self.assertEqual(
            "checked",
            input_elem.get("checked"))

        tree = self._process_with_form(
            self.xmlsrc_box_inputs,
            value=0)
        input_elem = tree.getroot().find(xhtml_ns.input)
        self.assertEqual(
            "field",
            input_elem.get("name"))
        self.assertIsNone(
            input_elem.get("checked"))

    def test_radio_inputs(self):
        tree = self._process_with_form(
            self.xmlsrc_radio_inputs,
            value=1)
        inputs = tree.getroot().findall(xhtml_ns.input)
        self.assertIsNotNone(
            inputs[0].get("checked"))
        self.assertEqual(
            "1",
            inputs[0].get("value"))
        self.assertIsNone(
            inputs[1].get("checked"))
        self.assertIsNone(
            inputs[2].get("checked"))

    def test_textarea_inputs(self):
        tree = self._process_with_form(
            self.xmlsrc_textarea_inputs,
            value=10)
        textarea_elem = tree.getroot().find(xhtml_ns.textarea)
        self.assertEqual(
            "field",
            textarea_elem.get("name"))
        self.assertEqual(
            "10",
            textarea_elem.text)
        self.assertEqual(
            "20",
            textarea_elem.get("rows"))
        self.assertEqual(
            "100",
            textarea_elem.get("cols"))

    def test_if_has_error(self):
        template = self._load_xml(self.xmlsrc_if_has_error)
        form = Form()
        form.errors[Form.field] = "test"
        tree = template.process({
            "form": form
        })

        self.assertEqual(
            "foo",
            tree.getroot().text)

        tree = self._process_with_form(
            self.xmlsrc_if_has_error)
        self.assertIsNone(tree.getroot().text)

    def test_for_each_error(self):
        template = self._load_xml(self.xmlsrc_for_each_error)
        form = Form()
        form.errors[Form.field] = ["test"]
        tree = template.process({
            "form": form
        })

        self.assertEqual(
            "foo",
            tree.getroot().text)

        tree = self._process_with_form(
            self.xmlsrc_if_has_error)
        self.assertIsNone(tree.getroot().text)

        template = self._load_xml(self.xmlsrc_for_each_error)
        form = Form()
        tree = template.process({
            "form": form
        })

        self.assertIsNone(tree.getroot().text)

    def test_for_field(self):
        tree = self._process_with_form(self.xmlsrc_for_field)
        self.assertEqual(
            "field",
            tree.getroot().find(xhtml_ns.label).get("for"))

    def test_action(self):
        tree = self._process_with_form(self.xmlsrc_action)
        self.assertEqual(
            "action:update",
            tree.getroot().find(xhtml_ns.input).get("name"))
