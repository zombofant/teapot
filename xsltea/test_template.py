import unittest

import lxml.etree as etree

import teapot.request

import xsltea.exec
import xsltea.template
import xsltea.processor
import xsltea.namespaces

class StoringProcessor(xsltea.processor.TemplateProcessor):
    class xmlns(metaclass=xsltea.namespaces.NamespaceMeta):
        xmlns = "uri:local:testing"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._a = "foo"
        self._b = 1
        self._c = [1, 2, "bar"]
        self.attrhooks = {}
        self.elemhooks = {
            (str(self.xmlns), "foo"): [self.handle_elem]
        }

    def handle_elem(self, template, elem, filename, offset):
        faketree = etree.Element(xsltea.exec.ExecProcessor.xmlns.text)
        faketree.text = """str([
            template_storage[{!r}],
            template_storage[{!r}],
            template_storage[{!r}]])""".format(
                template.store(self._a),
                template.store(self._b),
                template.store(self._c))
        return template.parse_subtree(faketree, filename, offset)


class TestTemplate(unittest.TestCase):
    xmlsrc = """<?xml version="1.0" ?>
<test xmlns:exec="https://xmlns.zombofant.net/xsltea/exec">
    <a />
    <b />
    <c xml:id="foobar" exec:attr="a" />
</test>"""

    xmlsrc_identity = """<test><test2 a="b" /><test3 c="d">spam<test4>foo</test4>bar<test5 e="f">baz</test5>fnord</test3></test>"""

    xmlsrc_href = """<test xmlns:exec="https://xmlns.zombofant.net/xsltea/exec"><a><exec:text>href('/foo/bar')</exec:text></a><b><exec:text>href('foo/bar')</exec:text></b></test>"""

    xmlsrc_storage = """<test xmlns:storage="uri:local:testing"><storage:foo /></test>"""

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

    def test_href(self):
        loader = xsltea.template.XMLTemplateLoader()
        loader.add_processor(xsltea.exec.ExecProcessor())

        request = teapot.request.Request(
            scriptname="/root/")

        template = loader.load_template(self.xmlsrc_href, "<string>")
        tree = template.process({}, request=request)
        self.assertEqual(
            tree.xpath("a").pop().text,
            "/root/foo/bar")
        self.assertEqual(
            tree.xpath("b").pop().text,
            "/root/foo/bar")

    def test_storage(self):
        loader = xsltea.template.XMLTemplateLoader()
        loader.add_processor(xsltea.exec.ExecProcessor())
        loader.add_processor(StoringProcessor())
        template = loader.load_template(self.xmlsrc_storage, "<string>")
        tree = template.process({})
        l = ["foo", 1, [1, 2, "bar"]]
        self.assertEqual(
            tree.xpath("/test").pop().text,
            str(l))

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
