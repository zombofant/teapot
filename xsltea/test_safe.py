import copy
import unittest

import lxml.etree as etree

import xsltea
import xsltea.exec
import xsltea.safe
import xsltea.namespaces

class TestForeachProcessor(unittest.TestCase):
    xmlsrc_simple = """<?xml version="1.0" ?>
<test xmlns:exec="https://xmlns.zombofant.net/xsltea/exec"
      xmlns:tea="https://xmlns.zombofant.net/xsltea/processors"
      exec:global="foo = list(range(3))">
<tea:for-each tea:bind="i" tea:from="foo">
    <b />
</tea:for-each></test>"""

    xmlsrc_nested = """<?xml version="1.0" ?>
<test xmlns:exec="https://xmlns.zombofant.net/xsltea/exec"
      xmlns:tea="https://xmlns.zombofant.net/xsltea/processors"
      exec:global="foo = list(range(3))">
<tea:for-each tea:bind="i" tea:from="foo">
    <tea:for-each tea:bind="j" tea:from="foo">
        <b />
    </tea:for-each>
</tea:for-each></test>"""

    xmlsrc_with_text = """<?xml version="1.0" ?>
<test xmlns:exec="https://xmlns.zombofant.net/xsltea/exec"
      xmlns:tea="https://xmlns.zombofant.net/xsltea/processors"
      exec:global="foo = list(range(3))">
<tea:for-each tea:bind="i" tea:from="foo">a</tea:for-each></test>"""

    xmlsrc_nested_with_text = """<?xml version="1.0" ?>
<test xmlns:exec="https://xmlns.zombofant.net/xsltea/exec"
      xmlns:tea="https://xmlns.zombofant.net/xsltea/processors"
      exec:global="foo = list(range(3))">
<tea:for-each tea:bind="i" tea:from="foo">a<tea:for-each tea:bind="j" tea:from="foo">b</tea:for-each>c</tea:for-each></test>"""

    xmlsrc_with_exec_text = """<?xml version="1.0" ?>
<test xmlns:exec="https://xmlns.zombofant.net/xsltea/exec"
      xmlns:tea="https://xmlns.zombofant.net/xsltea/processors"
      exec:global="foo = list(range(3))">
<tea:for-each tea:bind="i" tea:from="foo">
    <tea:for-each tea:bind="j" tea:from="foo">
        <exec:text>str(i)+str(j)</exec:text>
    </tea:for-each>
</tea:for-each></test>"""

    xmlsrc_with_exec_local = """<?xml version="1.0" ?>
<test xmlns:exec="https://xmlns.zombofant.net/xsltea/exec"
      xmlns:tea="https://xmlns.zombofant.net/xsltea/processors"
      exec:global="foo = list(range(3))">
<tea:for-each tea:bind="i" tea:from="foo">
    <tea:for-each tea:bind="j" tea:from="foo">
        <foo exec:local="k = i+j"><exec:text>k</exec:text></foo>
    </tea:for-each>
</tea:for-each></test>"""

    def _load_xml(self, xmlstr):
        template = xsltea.Template.from_buffer(xmlstr, "<string>")
        template._add_processor(xsltea.exec.ScopeProcessor)
        template._add_processor(xsltea.exec.ExecProcessor)
        template._add_processor(xsltea.safe.ForeachProcessor)
        template.preprocess()
        return template, template.get_processor(xsltea.safe.ForeachProcessor)

    def test_copy(self):
        el = etree.Element("foo")
        el.tail = "bar"
        el2 = copy.deepcopy(el)
        self.assertEqual(el.tail, el2.tail)

    def test_simple(self):
        template, foreach_ns = self._load_xml(self.xmlsrc_simple)
        tree = template.process({})
        bs = tree.tree.findall("b")
        self.assertEqual(len(bs), 3)
        self.assertFalse(tree.tree.findall(
            getattr(xsltea.namespaces.shared_ns, "for-each")))

    def test_nested(self):
        template, foreach_ns = self._load_xml(self.xmlsrc_nested)
        tree = template.process({})
        bs = tree.tree.findall("b")
        self.assertEqual(len(bs), 9)
        self.assertFalse(tree.tree.findall(
            getattr(xsltea.namespaces.shared_ns, "for-each")))

    def test_with_text(self):
        template, foreach_ns = self._load_xml(self.xmlsrc_with_text)
        tree = template.process({})
        self.assertEqual(tree.tree.getroot().text,
                         "aaa")

    def test_nested_with_text(self):
        template, foreach_ns = self._load_xml(self.xmlsrc_nested_with_text)
        tree = template.process({})
        self.assertEqual(tree.tree.getroot().text,
                         "abbbcabbbcabbbc")

    def test_with_exec_text(self):
        template, foreach_ns = self._load_xml(self.xmlsrc_with_exec_text)
        tree = template.process({})
        self.assertEqual("000102101112202122",
                         tree.tree.getroot().text)

    def test_with_exec_local(self):
        template, foreach_ns = self._load_xml(self.xmlsrc_with_exec_local)
        tree = template.process({})
        foo_texts = [element.text for element in tree.tree.findall("foo")]
        self.assertSequenceEqual(
            foo_texts,
            [str(i+j) for i in range(3) for j in range(3)])
