import copy
import unittest

import lxml.etree as etree

import xsltea
import xsltea.exec

class TestScopeProcessor(unittest.TestCase):
    xmlsrc_nested = """<?xml version="1.0" ?>
<test><a><b /></a></test>"""

    def _load_xml(self, xmlstr):
        template = xsltea.Template.from_buffer(xmlstr, "<string>")
        template._add_namespace_processor(xsltea.exec.ScopeProcessor)
        return template, template.get_processor(xsltea.exec.ScopeProcessor)

    def test_locals(self):
        template, scope_processor = self._load_xml(self.xmlsrc_nested)
        tree = template.tree

        test = tree.getroot()
        a = test.find("a")
        b = a.find("b")

        scope_processor.define_at_element(test, "foo", "bar")
        scope_processor.define_at_element(a, "fnord", "baz")
        scope_processor.define_at_element(b, "foo", "baz")

        self.assertDictEqual(scope_processor.get_locals_dict_for_element(a),
                             {"foo": "bar", "fnord": "baz"})
        self.assertDictEqual(scope_processor.get_locals_dict_for_element(b),
                             {"foo": "baz", "fnord": "baz"})
        self.assertDictEqual(scope_processor.get_locals_dict_for_element(test),
                             {"foo": "bar"})



class TestExecProcessor(unittest.TestCase):
    xmlsrc_eval_attrib = """<?xml version="1.0" ?>
<test xmlns:exec="{}" exec:test="'foo' + 'bar'"/>""".format(
        xsltea.exec.ExecProcessor.xmlns)

    xmlsrc_eval_text = """<?xml version="1.0" ?>
<test xmlns:exec="{}"><exec:text>'foo' + 'bar'</exec:text>baz</test>""".format(
        xsltea.exec.ExecProcessor.xmlns)

    xmlsrc_eval_global = """<?xml version="1.0" ?>
<test xmlns:exec="{}"
      exec:global="import binascii"><exec:text>binascii.b2a_hex(b"\\xff").decode()</exec:text></test>""".format(
        xsltea.exec.ExecProcessor.xmlns)

    xmlsrc_eval_local_ok = """<?xml version="1.0" ?>
<test xmlns:exec="{}"
      exec:local="a = 42"><exec:text>a</exec:text></test>""".format(
        xsltea.exec.ExecProcessor.xmlns)

    xmlsrc_eval_local_is_local = """<?xml version="1.0" ?>
<test xmlns:exec="{}"><a exec:local="a = 42"><exec:text>a</exec:text></a><exec:text>a</exec:text></test>""".format(
        xsltea.exec.ExecProcessor.xmlns)

    def _load_xml(self, xmlstr):
        template = xsltea.Template.from_buffer(xmlstr, "<string>")
        template._add_namespace_processor(xsltea.exec.ScopeProcessor)
        template._add_namespace_processor(xsltea.exec.ExecProcessor)
        eval_ns = template._processors[xsltea.exec.ExecProcessor]
        return template, eval_ns

    def test_eval_attribute(self):
        template, exec_ns = self._load_xml(self.xmlsrc_eval_attrib)
        tree = template.process({}).tree
        self.assertEqual(tree.getroot().attrib["test"],
                         "foobar")

    def test_eval_text(self):
        template, exec_ns = self._load_xml(self.xmlsrc_eval_text)
        tree = template.process({}).tree
        self.assertEqual(tree.getroot().text,
                         "foobarbaz")

    def test_exec_global(self):
        template, exec_ns = self._load_xml(self.xmlsrc_eval_global)
        tree = template.process({}).tree
        self.assertEqual(tree.getroot().text,
                         "ff")

    def test_exec_local_ok(self):
        template, exec_ns = self._load_xml(self.xmlsrc_eval_local_ok)
        tree = template.process({}).tree
        self.assertEqual(tree.getroot().text,
                         "42")

    def test_exec_local_is_local(self):
        template, exec_ns = self._load_xml(self.xmlsrc_eval_local_is_local)
        with self.assertRaises(xsltea.TemplateEvaluationError) as ctx:
            tree = template.process({}).tree

        self.assertIsInstance(ctx.exception.__context__, NameError)

    def test_exec_with_args_and_local(self):
        template, exec_ns = self._load_xml(self.xmlsrc_eval_local_is_local)
        tree = template.process({"a": 23}).tree
        self.assertEqual(tree.find("a").text,
                         "42")
        self.assertEqual(tree.find("a").tail,
                         "23")
