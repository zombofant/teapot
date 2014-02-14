import unittest

import lxml.etree as etree

import xsltea.exec
import xsltea.template

class TestTemplateTree(unittest.TestCase):
    xmlstr = """<?xml version="1.0" ?>
<test>
    <a />
    <b>
      <d />
    </b>
    <c xml:id="foobar"  />
    <d />
</test>"""

    def setUp(self):
        self._tree = xsltea.template.TemplateTree(etree.fromstring(self.xmlstr))

    def test_element_id_generation(self):
        id1 = self._tree.get_element_id(
            self._tree.tree.find("a"))
        id2 = self._tree.get_element_id(
            self._tree.tree.find("b"))
        self.assertNotEqual(id1, id2)

    def test_element_id_takeover(self):
        idc = self._tree.get_element_id(
            self._tree.tree.find("c"))
        self.assertNotEqual(idc, "foobar")

    def test_element_id_reuse(self):
        id1 = self._tree.get_element_id(
            self._tree.tree.find("a"))
        id2 = self._tree.get_element_id(
            self._tree.tree.find("a"))
        self.assertEqual(id1, id2)

    def tearDown(self):
        del self._tree
class TestTemplate(unittest.TestCase):
    xmlsrc = """<?xml version="1.0" ?>
<test xmlns:exec="https://xmlns.zombofant.net/xsltea/exec">
    <a />
    <b />
    <c xml:id="foobar" exec:attr="a" />
</test>"""

    def setUp(self):
        self._template = xsltea.template.Template.from_string(self.xmlsrc, "<string>")

    def test_processor(self):
        self._template._add_processor(xsltea.exec.ScopeProcessor)
        self._template._add_processor(xsltea.exec.ExecProcessor)
        self._template.preprocess()
        tree = self._template.process({"a": 42}).tree
        self.assertEqual(tree.find("c").get("attr"), "42")

    def tearDown(self):
        del self._template
