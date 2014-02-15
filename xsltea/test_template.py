import unittest

import lxml.etree as etree

import xsltea.exec
import xsltea.template

class TestTemplate(unittest.TestCase):
    xmlsrc = """<?xml version="1.0" ?>
<test xmlns:exec="https://xmlns.zombofant.net/xsltea/exec">
    <a />
    <b />
    <c xml:id="foobar" exec:attr="a" />
</test>"""

    xmlsrc_identity = """<test><test2 a="b" /><test3 c="d">spam<test4>foo</test4>bar<test5 e="f">baz</test5>fnord</test3></test>"""

    def test_identity(self):
        tree = etree.fromstring(self.xmlsrc_identity,
                                parser=xsltea.template.xml_parser)
        template = xsltea.template.Template(
            tree.getroottree(),
            "<string>",
            {}, {})
        self.assertEqual(
            etree.tostring(tree),
            etree.tostring(template.rootfunc({})))

    def test_processor(self):
        template = xsltea.template.Template.from_string(self.xmlsrc, "<string>")
        template._add_processor(xsltea.exec.ScopeProcessor)
        template._add_processor(xsltea.exec.ExecProcessor)
        template.preprocess()
        tree = template.process({"a": 42}).tree
        self.assertEqual(tree.find("c").get("attr"), "42")


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
