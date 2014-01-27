import unittest

import xsltea

class TestTemplate(unittest.TestCase):
    xmlsrc = """<?xml version="1.0" ?>
<test><a /><b /><c xml:id="foobar" /></test>"""

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

    def tearDown(self):
        del self._template
