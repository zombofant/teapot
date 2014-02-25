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
            etree.tostring(template.process({})))

class TestTemplateLoader(unittest.TestCase):
    def setUp(self):
        self._loader = xsltea.template.XMLTemplateLoader()

    def test_add_processor(self):
        proc = xsltea.ExecProcessor()
        self._loader.add_processor(proc)
        self.assertIn(proc, self._loader.processors)

    def test_add_processor_from_class(self):
        self._loader.add_processor(xsltea.exec.ExecProcessor)
        self.assertTrue(
            any(isinstance(obj, xsltea.exec.ExecProcessor)
                for obj in self._loader.processors))
