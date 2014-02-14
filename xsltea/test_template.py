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


class Foo1(xsltea.processor.TemplateProcessor):
    pass

class Foo3(xsltea.processor.TemplateProcessor):
    pass

class Foo2(xsltea.processor.TemplateProcessor):
    AFTER = [Foo1]
    BEFORE = [Foo3]

class Bar(xsltea.processor.TemplateProcessor):
    REQUIRES = [Foo1]
    BEFORE = [Foo2, Foo1]

class TestTemplateLoader(unittest.TestCase):
    def setUp(self):
        self._loader = xsltea.template.XMLTemplateLoader()

    def test_add_processor(self):
        self._loader.add_processor(xsltea.ExecProcessor)
        self.assertIn(xsltea.ExecProcessor, self._loader.processors)

    def test_processor_ordering(self):
        self._loader.add_processor(Foo3)
        self._loader.add_processor(Foo1)
        self._loader.add_processor(Foo2)
        self.assertSequenceEqual(
            self._loader.processors,
            [Foo1, Foo2, Foo3])

    def test_processor_dependency(self):
        self._loader.add_processor(Bar)
        self.assertSequenceEqual(
            [Bar, Foo1],
            self._loader.processors)
        self._loader.add_processor(Foo1)
        self.assertSequenceEqual(
            [Bar, Foo1],
            self._loader.processors)
        self._loader.add_processor(Foo2)
        self.assertSequenceEqual(
            [Bar, Foo1, Foo2],
            self._loader.processors)
