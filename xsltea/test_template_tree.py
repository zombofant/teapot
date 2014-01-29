import unittest

import xsltea

import lxml.etree as etree

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
        self._tree = xsltea.TemplateTree(etree.fromstring(self.xmlstr))

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
