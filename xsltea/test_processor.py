import unittest

import xsltea.processor

class TestProcessorMeta(unittest.TestCase):
    def test_AFTER_circle_detection(self):
        class Foo(metaclass=xsltea.processor.ProcessorMeta):
            pass

        with self.assertRaises(ValueError):
            class Bar(metaclass=xsltea.processor.ProcessorMeta):
                BEFORE = [Foo]
                AFTER = [Foo]

    def test_write_protection(self):
        class Foo(metaclass=xsltea.processor.ProcessorMeta):
            pass

        with self.assertRaises(AttributeError):
            Foo.REQUIRES = []
        with self.assertRaises(AttributeError):
            Foo.AFTER = []
        with self.assertRaises(AttributeError):
            Foo.BEFORE = []

        s = Foo.AFTER
        with self.assertRaises(AttributeError):
            s.add(Foo)

    def test_relationship_attribtues(self):
        class Foo1(metaclass=xsltea.processor.ProcessorMeta):
            pass

        class Foo7(metaclass=xsltea.processor.ProcessorMeta):
            pass

        class Foo6(metaclass=xsltea.processor.ProcessorMeta):
            BEFORE = [Foo7]

        class Foo5(metaclass=xsltea.processor.ProcessorMeta):
            BEFORE = [Foo6]

        class Foo4(metaclass=xsltea.processor.ProcessorMeta):
            BEFORE = [Foo5]

        class Foo3(metaclass=xsltea.processor.ProcessorMeta):
            BEFORE = [Foo4]

        class Foo2(metaclass=xsltea.processor.ProcessorMeta):
            AFTER = [Foo1]
            BEFORE = [Foo3]

        self.assertSetEqual(set([]), Foo1.AFTER)
        self.assertSetEqual(set([Foo2, Foo3, Foo4, Foo5, Foo6, Foo7]), Foo1.BEFORE)

        self.assertSetEqual(set([Foo1]), Foo2.AFTER)
        self.assertSetEqual(set([Foo3, Foo4, Foo5, Foo6, Foo7]), Foo2.BEFORE)

        self.assertSetEqual(set([Foo1, Foo2]), Foo3.AFTER)
        self.assertSetEqual(set([Foo4, Foo5, Foo6, Foo7]), Foo3.BEFORE)

        self.assertSetEqual(set([Foo1, Foo2, Foo3]), Foo4.AFTER)
        self.assertSetEqual(set([Foo5, Foo6, Foo7]), Foo4.BEFORE)

        self.assertSetEqual(set([Foo1, Foo2, Foo3, Foo4]), Foo5.AFTER)
        self.assertSetEqual(set([Foo6, Foo7]), Foo5.BEFORE)

        self.assertSetEqual(set([Foo1, Foo2, Foo3, Foo4, Foo5]), Foo6.AFTER)
        self.assertSetEqual(set([Foo7]), Foo6.BEFORE)

        self.assertSetEqual(set([Foo1, Foo2, Foo3, Foo4, Foo5, Foo6]), Foo7.AFTER)
        self.assertSetEqual(set([]), Foo7.BEFORE)
