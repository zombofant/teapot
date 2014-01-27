import unittest

import xsltea
import xsltea.exec

class TestTemplate(unittest.TestCase):
    xmlsrc = """<?xml version="1.0" ?>
<test xmlns:exec="https://xmlns.zombofant.net/xsltea/exec">
    <a />
    <b />
    <c xml:id="foobar" exec:attr="a" />
</test>"""

    def setUp(self):
        self._template = xsltea.Template.from_string(self.xmlsrc, "<string>")

    def test_element_id_generation(self):
        id1 = self._template.get_element_id(
            self._template.tree.find("a"))
        id2 = self._template.get_element_id(
            self._template.tree.find("b"))
        self.assertNotEqual(id1, id2)

    def test_element_id_takeover(self):
        idc = self._template.get_element_id(
            self._template.tree.find("c"))
        self.assertEqual(idc, "foobar")

    def test_element_id_reuse(self):
        id1 = self._template.get_element_id(
            self._template.tree.find("a"))
        id2 = self._template.get_element_id(
            self._template.tree.find("a"))
        self.assertEqual(id1, id2)

    def test_processor(self):
        self._template._add_namespace_processor(
            xsltea.exec.ScopeProcessor)
        self._template._add_namespace_processor(
            xsltea.exec.ExecProcessor)
        tree = self._template.process({"a": 42})
        self.assertEqual(tree.find("c").get("attr"), "42")
        self.assertFalse(tree.xpath("//@xml:id"))

    def tearDown(self):
        del self._template
