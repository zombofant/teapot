import unittest

import teapot.routing

class TestRoutingMeta(unittest.TestCase):
    def test_creation_of_class_route_information(self):
        class Test(metaclass=teapot.routing.RoutableMeta):
            @teapot.routing.route("foo")
            def test(self):
                return self

        self.assertTrue(teapot.routing.isroutable(Test))
        info = teapot.routing.getrouteinfo(Test)
        self.assertEqual(len(info._instanceroutables), 1)
        self.assertEqual(len(info._routables), 0)

    def test_instanciation_of_object_information(self):
        class Test(metaclass=teapot.routing.RoutableMeta):
            @teapot.routing.route("foo")
            def test(self):
                return self

        self.assertTrue(teapot.routing.isroutable(Test))

        instance = Test()
        self.assertTrue(teapot.routing.isroutable(instance))
        info1 = teapot.routing.getrouteinfo(instance)
        self.assertNotIsInstance(info1, teapot.routing.Class)
        self.assertFalse(hasattr(info1, "_instanceroutables"))
        info2 = teapot.routing.getrouteinfo(instance)
        self.assertIs(info1, info2)

        self.assertIs(
            info1._routables[0]._callable(),
            instance)

    def test_routable_inheritance(self):
        class TestBase(metaclass=teapot.routing.RoutableMeta):
            @teapot.routing.route("foo")
            def test(self):
                return TestBase

        class TestSub(TestBase):
            @teapot.routing.route("bar")
            def test(self):
                return TestSub

        self.assertTrue(teapot.routing.isroutable(TestSub))

        info = teapot.routing.getrouteinfo(TestSub)

        self.assertEqual(len(info._instanceroutables), 2)
        self.assertEqual(len(info._routables), 0)
