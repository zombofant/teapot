import unittest

import teapot.forms

import xsltea.safe
import xsltea.forms

import lxml.etree as etree

from xsltea.namespaces import xhtml_ns

class Form(teapot.forms.Form):
    @teapot.forms.field
    def field(self, value):
        return int(value)

    @field.default
    def field(self):
        return 10

class TestFormProcessor(unittest.TestCase):
    xmlsrc_text_inputs = """<input
    xmlns="http://www.w3.org/1999/xhtml"
    xmlns:form="https://xmlns.zombofant.net/xsltea/form"
    form:field="field"
    form:form="arguments['form']"
    type="text" />"""

    xmlsrc_box_inputs = """<input
    xmlns="http://www.w3.org/1999/xhtml"
    xmlns:form="https://xmlns.zombofant.net/xsltea/form"
    form:field="field"
    form:form="arguments['form']"
    type="checkbox" />"""

    xmlsrc_textarea_inputs = """<textarea
    xmlns="http://www.w3.org/1999/xhtml"
    xmlns:form="https://xmlns.zombofant.net/xsltea/form"
    form:field="field"
    form:form="arguments['form']" />"""


    def setUp(self):
        self._loader = xsltea.template.XMLTemplateLoader()
        self._loader.add_processor(xsltea.forms.FormProcessor(
            safety_level=xsltea.safe.SafetyLevel.unsafe))

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
        self.assertEqual(
            "field",
            tree.getroot().get("name"))
        self.assertEqual(
            "10",
            tree.getroot().get("value"))

    def test_box_inputs(self):
        tree = self._process_with_form(
            self.xmlsrc_box_inputs,
            value=1)
        self.assertEqual(
            "field",
            tree.getroot().get("name"))
        self.assertEqual(
            "checked",
            tree.getroot().get("checked"))

        tree = self._process_with_form(
            self.xmlsrc_box_inputs,
            value=0)
        self.assertEqual(
            "field",
            tree.getroot().get("name"))
        self.assertIsNone(
            tree.getroot().get("checked"))

    def test_textarea_inputs(self):
        tree = self._process_with_form(
            self.xmlsrc_textarea_inputs,
            value=10)
        self.assertEqual(
            "field",
            tree.getroot().get("name"))
        self.assertEqual(
            "10",
            tree.getroot().text)