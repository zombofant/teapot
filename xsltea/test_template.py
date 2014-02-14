import unittest

import xsltea
import xsltea.exec

class TestTemplate(unittest.TestCase):
    xmlsrc = """<?xml version="1.0" ?>
<test xmlns:exec="https://xmlns.zombofant.net/xsltea/exec">
    <a />
    <b />
    <c xml:id="foobar" exec:attr="a" />
</test>"""

    def setUp(self):
        self._template = xsltea.Template.from_string(self.xmlsrc, "<string>")

    def test_processor(self):
        self._template._add_processor(xsltea.exec.ScopeProcessor)
        self._template._add_processor(xsltea.exec.ExecProcessor)
        self._template.preprocess()
        tree = self._template.process({"a": 42}).tree
        self.assertEqual(tree.find("c").get("attr"), "42")

    def tearDown(self):
        del self._template
