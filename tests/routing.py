import unittest

import teapot.routing
import teapot.request

@teapot.routing.rebase("/")
class SomeRoutable(metaclass=teapot.routing.RoutableMeta):
    @teapot.routing.route("", "index")
    def index(self):
        pass

    @teapot.routing.rebase("foo/")
    @teapot.routing.route("fnord")
    @classmethod
    def fnord(cls):
        pass

class TestRoutingMeta(unittest.TestCase):
    def test_creation_of_class_route_information(self):
        class Test(metaclass=teapot.routing.RoutableMeta):
            @teapot.routing.route("foo")
            def test(self):
                return self

        self.assertTrue(teapot.routing.isroutable(Test))
        info = teapot.routing.getrouteinfo(Test)
        self.assertEqual(len(info.instance_routenodes), 1)
        self.assertEqual(len(info.routenodes), 0)

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
            info1.routenodes[0].callable(),
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

        self.assertEqual(len(info.instance_routenodes), 2)
        self.assertEqual(len(info.routenodes), 0)

    def test_specialization_of_prototypes_in_getrouteinfo(self):
        class TestFoo(metaclass=teapot.routing.RoutableMeta):
            @teapot.routing.route("foo")
            @staticmethod
            def foo():
                pass

            @teapot.routing.route("bar")
            @classmethod
            def bar(cls):
                pass

            @teapot.routing.route("baz")
            def baz(cls):
                pass

        test = TestFoo()
        self.assertFalse(hasattr(
            teapot.routing.getrouteinfo(test.foo),
            "get"))
        self.assertFalse(hasattr(
            teapot.routing.getrouteinfo(test.bar),
            "get"))
        self.assertFalse(hasattr(
            teapot.routing.getrouteinfo(test.baz),
            "get"))

class TestRouting(unittest.TestCase):
    def setUp(self):
        self._root = SomeRoutable()

    def test_route_simple(self):
        request = teapot.request.Request(
            teapot.request.RequestMethod.GET,
            "/index",
            "https",
            {},
            None)
        success, data = teapot.routing.find_route(
            self._root, request)
        self.assertTrue(success)

    def test_route_multirebase(self):
        request = teapot.request.Request(
            teapot.request.RequestMethod.GET,
            "/foo/fnord",
            "https",
            {},
            None)
        success, data = teapot.routing.find_route(
            self._root, request)
        self.assertTrue(success)

    def test_route_not_found(self):
        request = teapot.request.Request(
            teapot.request.RequestMethod.GET,
            "/foo/bar",
            "https",
            {},
            None)
        success, data = teapot.routing.find_route(
            self._root, request)
        self.assertFalse(success)
        self.assertIsNone(data)

    def tearDown(self):
        del self._root

class TestUnrouting(unittest.TestCase):
    def setUp(self):
        self._root = SomeRoutable()

    def test_unrouting_unwinds_correctly_for_instancemethods(self):
        routeinfo = teapot.routing.getrouteinfo(self._root.index)
        self.assertSequenceEqual(
            list(teapot.routing.traverse_to_root(routeinfo)),
            [routeinfo,
             teapot.routing.getrouteinfo(self._root)]
        )


    def tearDown(self):
        del self._root
