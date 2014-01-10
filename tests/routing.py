import unittest

import teapot.routing
import teapot.request

class TestRoutingMeta(unittest.TestCase):
    def test_creation_of_class_route_information(self):
        class Test(metaclass=teapot.routing.RoutableMeta):
            @teapot.routing.route("foo")
            def test(self):
                return self

        self.assertTrue(teapot.routing.isroutable(Test))
        info = teapot.routing.getrouteinfo(Test)
        self.assertEqual(len(info.instanceroutables), 1)
        self.assertEqual(len(info.routables), 0)

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
            info1.routables[0].callable(),
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

        self.assertEqual(len(info.instanceroutables), 2)
        self.assertEqual(len(info.routables), 0)

class TestRouting(unittest.TestCase):
    @teapot.routing.rebase("/")
    class Test(metaclass=teapot.routing.RoutableMeta):
        @teapot.routing.route("", "index")
        def index(self):
            pass

        @teapot.routing.rebase("foo/")
        @teapot.routing.route("fnord")
        def fnord(self):
            pass

    def setUp(self):
        self._root = self.Test()

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
