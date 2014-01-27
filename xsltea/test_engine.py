import unittest

import teapot.templating
import xsltea

class FnordProcessor(xsltea.NamespaceProcessor):
    pass

class FakeProcessor(xsltea.NamespaceProcessor):
    REQUIRES = [xsltea.ExecProcessor, FnordProcessor]

FnordProcessor.REQUIRES = [FakeProcessor]

class TestEngine(unittest.TestCase):
    def setUp(self):
        self._engine = xsltea.Engine()

    def test_recursion_detection_for_processors(self):
        prev_list = list(self._engine.processors)

        with self.assertRaises(ValueError):
            self._engine.add_namespace_processor(FakeProcessor)
        self.assertSequenceEqual(
            prev_list, self._engine.processors,
            "Processor list was modified, despite error")

        with self.assertRaises(ValueError):
            self._engine.add_namespace_processor(FnordProcessor)
        self.assertSequenceEqual(
            prev_list, self._engine.processors,
            "Processor list was modified, despite error")

    def test_add_processor(self):
        self._engine.add_namespace_processor(xsltea.ExecProcessor)
        self.assertIn(xsltea.ExecProcessor, self._engine.processors)
