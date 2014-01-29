import unittest

import teapot.templating
import xsltea

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

class TestEngine(unittest.TestCase):
    def setUp(self):
        self._engine = xsltea.Engine()

    def test_add_processor(self):
        self._engine.add_namespace_processor(xsltea.ExecProcessor)
        self.assertIn(xsltea.ExecProcessor, self._engine.processors)

    def test_processor_ordering(self):
        self._engine.add_namespace_processor(Foo3)
        self._engine.add_namespace_processor(Foo1)
        self._engine.add_namespace_processor(Foo2)
        self.assertSequenceEqual(
            self._engine.processors,
            [Foo1, Foo2, Foo3])

    def test_processor_dependency(self):
        self._engine.add_namespace_processor(Bar)
        self.assertSequenceEqual(
            [Bar, Foo1],
            self._engine.processors)
        self._engine.add_namespace_processor(Foo1)
        self.assertSequenceEqual(
            [Bar, Foo1],
            self._engine.processors)
        self._engine.add_namespace_processor(Foo2)
        self.assertSequenceEqual(
            [Bar, Foo1, Foo2],
            self._engine.processors)
