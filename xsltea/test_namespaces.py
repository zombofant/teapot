import unittest

import xsltea.namespaces

class SomeNamespace(metaclass=xsltea.namespaces.NamespaceMeta):
    xmlns = "foo"

class TestNamespaceMeta(unittest.TestCase):
    def test_name_creation(self):
        self.assertEqual(SomeNamespace.bar, "{foo}bar")

    def test_element_creation(self):
        elem = SomeNamespace("bar")
        self.assertEqual(elem.tag, SomeNamespace.bar)
