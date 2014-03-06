import copy
import unittest

import lxml.etree as etree

import xsltea
import xsltea.exec
import xsltea.safe
import xsltea.namespaces

class TestSafetyLevel_conservative(unittest.TestCase):
    sl = xsltea.safe.SafetyLevel.conservative

    def test_name(self):
        self.sl.check_code_safety("name")
        with self.assertRaises(ValueError):
            self.sl.check_code_safety("_name")

    def test_subscript(self):
        with self.assertRaises(ValueError):
            self.sl.check_code_safety("name['name']")

    def test_call(self):
        with self.assertRaises(ValueError):
            self.sl.check_code_safety("name(name)")

    def test_list(self):
        self.sl.check_code_safety("['1', name, 2]")

    def test_tuple(self):
        self.sl.check_code_safety("('1', name, 2)")

    def test_dict(self):
        self.sl.check_code_safety("{name: value, '1': 2}")

class TestSafetyLevel_experimental(unittest.TestCase):
    sl = xsltea.safe.SafetyLevel.experimental

    def test_name(self):
        self.sl.check_code_safety("name")
        with self.assertRaises(ValueError):
            self.sl.check_code_safety("_name")

    def test_subscript(self):
        self.sl.check_code_safety("name['name']")

    def test_binop(self):
        self.sl.check_code_safety("name + name")

    def test_unaryop(self):
        self.sl.check_code_safety("not name")

    def test_ifexpr(self):
        self.sl.check_code_safety("a if b else c")

    def test_call(self):
        with self.assertRaises(ValueError):
            self.sl.check_code_safety("name(name)")

    def test_list(self):
        self.sl.check_code_safety("['1', name, 2]")

    def test_tuple(self):
        self.sl.check_code_safety("('1', name, 2)")

    def test_dict(self):
        self.sl.check_code_safety("{name: value, '1': 2}")

class TestForeachProcessor(unittest.TestCase):
    xmlsrc_simple = """<?xml version="1.0" ?>
<test xmlns:exec="https://xmlns.zombofant.net/xsltea/exec"
      xmlns:tea="https://xmlns.zombofant.net/xsltea/processors"
    ><exec:code>foo = list(range(3))</exec:code>
<tea:for-each tea:bind="i" tea:from="foo">
    <b />
</tea:for-each></test>"""

    xmlsrc_nested = """<?xml version="1.0" ?>
<test xmlns:exec="https://xmlns.zombofant.net/xsltea/exec"
      xmlns:tea="https://xmlns.zombofant.net/xsltea/processors"
    ><exec:code>foo = list(range(3))</exec:code>
<tea:for-each tea:bind="i" tea:from="foo">
    <tea:for-each tea:bind="j" tea:from="foo">
        <b />
    </tea:for-each>
</tea:for-each></test>"""

    xmlsrc_with_text = """<?xml version="1.0" ?>
<test xmlns:exec="https://xmlns.zombofant.net/xsltea/exec"
      xmlns:tea="https://xmlns.zombofant.net/xsltea/processors"
    ><exec:code>foo = list(range(3))</exec:code>
<tea:for-each tea:bind="i" tea:from="foo">a</tea:for-each></test>"""

    xmlsrc_nested_with_text = """<?xml version="1.0" ?>
<test xmlns:exec="https://xmlns.zombofant.net/xsltea/exec"
      xmlns:tea="https://xmlns.zombofant.net/xsltea/processors"
    ><exec:code>foo = list(range(3))</exec:code>
<tea:for-each tea:bind="i" tea:from="foo">a<tea:for-each tea:bind="j" tea:from="foo">b</tea:for-each>c</tea:for-each></test>"""

    xmlsrc_with_exec_text = """<?xml version="1.0" ?>
<test xmlns:exec="https://xmlns.zombofant.net/xsltea/exec"
      xmlns:tea="https://xmlns.zombofant.net/xsltea/processors"
    ><exec:code>foo = list(range(3))</exec:code>
<tea:for-each tea:bind="i" tea:from="foo">
    <tea:for-each tea:bind="j" tea:from="foo">
        <exec:text>str(i)+str(j)</exec:text>
    </tea:for-each>
</tea:for-each></test>"""

    xmlsrc_with_exec_local = """<?xml version="1.0" ?>
<test xmlns:exec="https://xmlns.zombofant.net/xsltea/exec"
      xmlns:tea="https://xmlns.zombofant.net/xsltea/processors"
    ><exec:code>foo = list(range(3))</exec:code>
<tea:for-each tea:bind="i" tea:from="foo">
    <tea:for-each tea:bind="j" tea:from="foo">
        <foo><exec:code>k = i+j</exec:code><exec:text>k</exec:text></foo>
    </tea:for-each>
</tea:for-each></test>"""

    xmlsrc_with_unpack = """<?xml version="1.0" ?>
<test xmlns:exec="https://xmlns.zombofant.net/xsltea/exec"
      xmlns:tea="https://xmlns.zombofant.net/xsltea/processors">
    ><exec:code>foo = list(zip(range(3), range(4, 8)))</exec:code>
<tea:for-each tea:bind="i, j" tea:from="foo">
    <foo exec:attr="i+j"><exec:text>i+j</exec:text></foo>
</tea:for-each></test>"""


    def setUp(self):
        self._loader = xsltea.template.XMLTemplateLoader()
        self._loader.add_processor(xsltea.exec.ExecProcessor)
        self._loader.add_processor(xsltea.safe.ForeachProcessor)

    def _load_xml(self, xmlstr):
        template = self._loader.load_template(xmlstr, "<string>")
        return template

    def test_copy(self):
        el = etree.Element("foo")
        el.tail = "bar"
        el2 = copy.deepcopy(el)
        self.assertEqual(el.tail, el2.tail)

    def test_simple(self):
        template = self._load_xml(self.xmlsrc_simple)
        tree = template.process({})
        bs = tree.findall("b")
        self.assertEqual(len(bs), 3)
        self.assertFalse(tree.findall(
            getattr(xsltea.namespaces.shared_ns, "for-each")))

    def test_nested(self):
        template = self._load_xml(self.xmlsrc_nested)
        tree = template.process({})
        bs = tree.findall("b")
        self.assertEqual(len(bs), 9)
        self.assertFalse(tree.findall(
            getattr(xsltea.namespaces.shared_ns, "for-each")))

    def test_with_text(self):
        template = self._load_xml(self.xmlsrc_with_text)
        tree = template.process({})
        self.assertEqual(tree.getroot().text,
                         "aaa")

    def test_nested_with_text(self):
        template = self._load_xml(self.xmlsrc_nested_with_text)
        tree = template.process({})
        self.assertEqual(tree.getroot().text,
                         "abbbcabbbcabbbc")

    def test_with_exec_text(self):
        template = self._load_xml(self.xmlsrc_with_exec_text)
        tree = template.process({})
        self.assertEqual("000102101112202122",
                         tree.getroot().text)

    def test_with_exec_local(self):
        template = self._load_xml(self.xmlsrc_with_exec_local)
        tree = template.process({})
        foo_texts = [element.text for element in tree.findall("foo")]
        self.assertSequenceEqual(
            foo_texts,
            [str(i+j) for i in range(3) for j in range(3)])

    def test_with_unpack(self):
        template = self._load_xml(self.xmlsrc_with_unpack)
        tree = template.process({})
        foo_texts = [element.text for element in tree.findall("foo")]
        foo_attrs = [element.get("attr") for element in tree.findall("foo")]
        self.assertSequenceEqual(
            foo_texts,
            [str(i+j) for i, j in zip(range(3), range(4, 8))])
        self.assertSequenceEqual(
            foo_attrs,
            [str(i+j) for i, j in zip(range(3), range(4, 8))])

class TestFunctionProcessor(unittest.TestCase):
    xmlsrc_def_and_call = """\
<test xmlns:tea="https://xmlns.zombofant.net/xsltea/processors"
      xmlns:exec="https://xmlns.zombofant.net/xsltea/exec">
  <def><tea:def tea:name="test">
    <tea:arg name="a" />
    <tea:arg name="b" />foo<a><exec:text>a</exec:text></a>
    <b><exec:text>b</exec:text></b>
  </tea:def>bar</def>
  <eval><tea:call tea:name="test">
    <tea:pass name="a">1</tea:pass>
    <tea:pass name="b">2</tea:pass>
  </tea:call></eval>
</test>"""

    xmlsrc_argument_variants = """\
<test xmlns:tea="https://xmlns.zombofant.net/xsltea/processors"
      xmlns:exec="https://xmlns.zombofant.net/xsltea/exec">
  <def><tea:def tea:name="test">
    <tea:arg name="a" default="'foo'" />
    <tea:arg name="b" mode="lazy" default="arguments['passed']" />
    <a><exec:text>a</exec:text></a>
    <b><exec:text>b</exec:text></b>
  </tea:def>bar</def>
  <eval1><tea:call tea:name="test" /></eval1>
  <eval2><tea:call tea:name="test">
    <tea:pass name="a">1</tea:pass>
  </tea:call></eval2>
  <eval3><tea:call tea:name="test">
    <tea:pass name="b">1</tea:pass>
  </tea:call></eval3>
</test>"""

    def setUp(self):
        self._loader = xsltea.template.XMLTemplateLoader()
        self._loader.add_processor(xsltea.exec.ExecProcessor)
        self._loader.add_processor(xsltea.safe.FunctionProcessor(
            safety_level=xsltea.safe.SafetyLevel.experimental))

    def _load_xml(self, xmlstr):
        template = self._loader.load_template(xmlstr, "<string>")
        return template

    def test_def_and_call(self):
        template = self._load_xml(self.xmlsrc_def_and_call)
        tree = template.process({})
        defelem = tree.getroot().find("def")
        evalelem = tree.getroot().find("eval")
        self.assertEqual(0, len(defelem))
        self.assertEqual("bar", defelem.text)

        self.assertEqual(2, len(evalelem))
        self.assertEqual("foo", evalelem.text)
        self.assertEqual("1", evalelem.find("a").text)
        self.assertEqual("2", evalelem.find("b").text)

    def test_argument_variants(self):
        template = self._load_xml(self.xmlsrc_argument_variants)
        tree = template.process({
            "passed": "bar"
        })
        defelem = tree.getroot().find("def")
        self.assertEqual(0, len(defelem))

        evalelem1 = tree.getroot().find("eval1")
        evalelem2 = tree.getroot().find("eval2")
        evalelem3 = tree.getroot().find("eval3")

        self.assertEqual(2, len(evalelem1))
        self.assertEqual("foo", evalelem1.find("a").text)
        self.assertEqual("bar", evalelem1.find("b").text)

        self.assertEqual(2, len(evalelem2))
        self.assertEqual("1", evalelem2.find("a").text)
        self.assertEqual("bar", evalelem2.find("b").text)

        self.assertEqual(2, len(evalelem3))
        self.assertEqual("foo", evalelem3.find("a").text)
        self.assertEqual("1", evalelem3.find("b").text)
