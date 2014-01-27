import copy
import unittest

import lxml.etree as etree

import xsltea
import xsltea.exec

class TestExecNamespace(unittest.TestCase):
    xmlsrc_eval_attrib = """<?xml version="1.0" ?>
<test xmlns:exec="{}" exec:test="'foo' + 'bar'"/>""".format(
        xsltea.exec.ExecNamespace.xmlns)

    xmlsrc_eval_text = """<?xml version="1.0" ?>
<test xmlns:exec="{}"><exec:text>'foo' + 'bar'</exec:text>baz</test>""".format(
        xsltea.exec.ExecNamespace.xmlns)

    xmlsrc_eval_global = """<?xml version="1.0" ?>
<test xmlns:exec="{}"
      exec:global="import binascii"><exec:text>binascii.b2a_hex(b"\\xff").decode()</exec:text></test>""".format(
        xsltea.exec.ExecNamespace.xmlns)

    xmlsrc_eval_local_ok = """<?xml version="1.0" ?>
<test xmlns:exec="{}"
      exec:local="a = 42"><exec:text>a</exec:text></test>""".format(
        xsltea.exec.ExecNamespace.xmlns)

    xmlsrc_eval_local_is_local = """<?xml version="1.0" ?>
<test xmlns:exec="{}"><a exec:local="a = 42"><exec:text>a</exec:text></a><exec:text>a</exec:text></test>""".format(
        xsltea.exec.ExecNamespace.xmlns)

    def _load_xml(self, xmlstr):
        template = xsltea.Template.from_buffer(xmlstr, "<string>")
        eval_ns = xsltea.ExecNamespace(template)
        return template, eval_ns

    def test_eval_attribute(self):
        template, exec_ns = self._load_xml(self.xmlsrc_eval_attrib)
        exec_ns.process(template.tree, {})
        self.assertEqual(template.tree.getroot().attrib["test"],
                         "foobar")

    def test_eval_text(self):
        template, exec_ns = self._load_xml(self.xmlsrc_eval_text)
        exec_ns.process(template.tree, {})
        self.assertEqual(template.tree.getroot().text,
                         "foobarbaz")

    def test_exec_global(self):
        template, exec_ns = self._load_xml(self.xmlsrc_eval_global)
        exec_ns.process(template.tree, {})
        self.assertEqual(template.tree.getroot().text,
                         "ff")

    def test_exec_local_ok(self):
        template, exec_ns = self._load_xml(self.xmlsrc_eval_local_ok)
        exec_ns.process(template.tree, {})
        self.assertEqual(template.tree.getroot().text,
                         "42")

    def test_exec_local_is_local(self):
        template, exec_ns = self._load_xml(self.xmlsrc_eval_local_is_local)
        with self.assertRaises(xsltea.TemplateEvaluationError) as ctx:
            exec_ns.process(template.tree, {})

        self.assertIsInstance(ctx.exception.__context__, NameError)

    def test_exec_with_args_and_local(self):
        template, exec_ns = self._load_xml(self.xmlsrc_eval_local_is_local)
        exec_ns.process(template.tree, {"a": 23})
        self.assertEqual(template.tree.find("a").text,
                         "42")
        self.assertEqual(template.tree.find("a").tail,
                         "23")
