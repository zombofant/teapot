import copy
import unittest

import lxml.etree as etree

import xsltea
import xsltea.exec
import xsltea.safe
import xsltea.template
import xsltea.namespaces

class TestExecProcessor(unittest.TestCase):
    xmlsrc_eval_attrib = """<?xml version="1.0" ?>
<test xmlns:exec="{}" exec:test="'foo' + 'bar'"/>""".format(
        xsltea.exec.ExecProcessor.xmlns)

    xmlsrc_eval_attrib_nonstr = """<?xml version="1.0" ?>
<test xmlns:exec="{}" exec:test="42"/>""".format(
        xsltea.exec.ExecProcessor.xmlns)

    xmlsrc_eval_attrib_with_ns = """<?xml version="1.0" ?>
<test xmlns:exec="{}" exec:test="'foo' + 'bar', '{{urn:test}}test'"/>""".format(
        xsltea.exec.ExecProcessor.xmlns)

    xmlsrc_eval_attrib_drop = """<?xml version="1.0" ?>
<test xmlns:exec="{}" exec:test="None"/>""".format(
        xsltea.exec.ExecProcessor.xmlns)

    xmlsrc_eval_text = """<?xml version="1.0" ?>
<test xmlns:exec="{}"><exec:text>'foo' + 'bar'</exec:text>baz</test>""".format(
        xsltea.exec.ExecProcessor.xmlns)

    xmlsrc_eval_global = """<?xml version="1.0" ?>
<test xmlns:exec="{}"><exec:code>import binascii</exec:code><exec:text>binascii.b2a_hex(b"\\xff").decode()</exec:text></test>""".format(
        xsltea.exec.ExecProcessor.xmlns)

    xmlsrc_eval_local_ok = """<?xml version="1.0" ?>
<test xmlns:exec="{}"><exec:code>a = 42</exec:code><exec:text>a</exec:text></test>""".format(
        xsltea.exec.ExecProcessor.xmlns)

    xmlsrc_eval_local_is_local = """<?xml version="1.0" ?>
<test xmlns:exec="{}"><a><exec:code>a = 42</exec:code><exec:text>a</exec:text></a><exec:text>a</exec:text></test>""".format(
        xsltea.exec.ExecProcessor.xmlns)

    xmlsrc_eval_args = """<?xml version="1.0" ?>
<test xmlns:exec="{}"><a><exec:code>a = 42</exec:code><exec:text>a</exec:text></a><exec:text>arguments["a"]</exec:text></test>""".format(
        xsltea.exec.ExecProcessor.xmlns)

    xmlsrc_exec_if = """<?xml version="1.0" ?>
<test xmlns:exec="{}" xmlns:tea="{}"><a><tea:if exec:eval="arguments['a']"><exec:text>42</exec:text></tea:if><tea:if exec:eval="not arguments['a']"><exec:text>23</exec:text></tea:if></a></test>""".format(
        xsltea.exec.ExecProcessor.xmlns,
        xsltea.namespaces.shared_ns)

    xmlsrc_exec_if_without_children = """<?xml version="1.0" ?>
<test xmlns:exec="{}" xmlns:tea="{}"><a><tea:if exec:eval="arguments['a']"><exec:code>foo = arguments['a']</exec:code></tea:if></a></test>""".format(
        xsltea.exec.ExecProcessor.xmlns,
        xsltea.namespaces.shared_ns)

    xmlsrc_exec_switch = """<?xml version="1.0" ?>
<test xmlns:exec="{}" xmlns:tea="{}"><a><tea:switch><tea:case exec:eval="arguments['a']"><exec:text>42</exec:text></tea:case><tea:default><exec:text>23</exec:text></tea:default></tea:switch></a></test>""".format(
        xsltea.exec.ExecProcessor.xmlns,
        xsltea.namespaces.shared_ns)

    def setUp(self):
        self._loader = xsltea.template.XMLTemplateLoader()
        self._loader.add_processor(xsltea.exec.ExecProcessor)
        self._loader.add_processor(xsltea.safe.BranchingProcessor)

    def _load_xml(self, xmlstr):
        template = self._loader.load_template(xmlstr, "<string>")
        return template

    def test_eval_attribute(self):
        template = self._load_xml(self.xmlsrc_eval_attrib)
        tree = template.process({})
        self.assertEqual(tree.getroot().attrib["test"],
                         "foobar")

    def test_eval_attribute_nonstr(self):
        template = self._load_xml(self.xmlsrc_eval_attrib_nonstr)
        tree = template.process({})
        self.assertEqual(tree.getroot().attrib["test"],
                         "42")

    def test_eval_attribute_with_ns(self):
        template = self._load_xml(self.xmlsrc_eval_attrib_with_ns)
        tree = template.process({})
        self.assertEqual(tree.getroot().attrib["{urn:test}test"],
                         "foobar")

    def test_eval_attribute_drop(self):
        template = self._load_xml(self.xmlsrc_eval_attrib_drop)
        tree = template.process({})
        self.assertFalse(tree.getroot().attrib)

    def test_eval_text(self):
        template = self._load_xml(self.xmlsrc_eval_text)
        tree = template.process({})
        self.assertEqual(tree.getroot().text,
                         "foobarbaz")

    def test_exec_global(self):
        template = self._load_xml(self.xmlsrc_eval_global)
        tree = template.process({})
        self.assertEqual(tree.getroot().text,
                         "ff")

    def test_exec_local_ok(self):
        template = self._load_xml(self.xmlsrc_eval_local_ok)
        tree = template.process({})
        self.assertEqual(tree.getroot().text,
                         "42")

    def test_exec_local_is_local(self):
        template = self._load_xml(self.xmlsrc_eval_local_is_local)
        with self.assertRaises(xsltea.TemplateEvaluationError) as ctx:
            tree = template.process({})
            print(etree.tostring(tree))

        self.assertIsInstance(ctx.exception.__context__, NameError)

    def test_exec_with_args_and_local(self):
        template = self._load_xml(self.xmlsrc_eval_args)
        tree = template.process({"a": 23})
        self.assertEqual(tree.find("a").text,
                         "42")
        self.assertEqual(tree.find("a").tail,
                         "23")

    def test_exec_if(self):
        template = self._load_xml(self.xmlsrc_exec_if)
        tree = template.process({"a": True})
        self.assertEqual(tree.find("a").text, "42")
        tree = template.process({"a": False})
        self.assertEqual(tree.find("a").text, "23")

    def test_exec_if_without_children(self):
        template = self._load_xml(self.xmlsrc_exec_if_without_children)
        tree = template.process({"a": True})
        self.assertEqual(0, len(tree.find("a")))

    def test_exec_switch(self):
        template = self._load_xml(self.xmlsrc_exec_switch)
        tree = template.process({"a": True})
        self.assertEqual(tree.find("a").text, "42")
        tree = template.process({"a": False})
        self.assertEqual(tree.find("a").text, "23")
