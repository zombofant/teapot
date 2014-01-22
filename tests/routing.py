import unittest
import copy
import io

import teapot
import teapot.routing
import teapot.request

@teapot.rebase("/")
class SomeRoutable(metaclass=teapot.routing.RoutableMeta):
    def __init__(self):
        super().__init__()
        self.args = []
        self.kwargs = {}

    @teapot.route("", "index")
    def index(self):
        pass

    @teapot.rebase("foo/")
    @teapot.route("fnord")
    @classmethod
    def fnord(cls):
        pass

    @teapot.route("p/{:2d}")
    def formatted(self, arg):
        self.args = [arg]

class TestContext(unittest.TestCase):
    method = teapot.request.Method.GET
    path = "/foo/bar"
    scheme = "https"
    query_data = {}
    accept_info = teapot.accept.all_content_types(), \
                  teapot.accept.all_languages(), \
                  teapot.accept.all_charsets()

    def create_example_request(self):
        return teapot.request.Request(
            self.method,
            self.path,
            self.scheme,
            self.query_data,
            self.accept_info,
            "",
            io.BytesIO(b""))

    def test_initialization_from_request(self):
        request = self.create_example_request()
        context = teapot.routing.Context(request)
        self.assertEqual(context.path, request.path)
        self.assertEqual(context.method, request.method)
        self.assertEqual(context.scheme, request.scheme)
        self.assertEqual(context.accept_language, request.accept_language)
        self.assertEqual(context.accept_content, request.accept_content)
        self.assertIs(context.original_request, request)

    def test_copy_construction(self):
        request = self.create_example_request()
        context1 = teapot.routing.Context(request)
        context1.args.append("foo")
        context1.args.append("bar")

        context2 = teapot.routing.Context(context1)
        self.assertEqual(context1.path, context2.path)
        self.assertEqual(context1.method, context2.method)
        self.assertEqual(context1.scheme, context2.scheme)
        self.assertEqual(context1.accept_language,
                         context2.accept_language)
        self.assertEqual(context1.accept_content,
                         context2.accept_content)
        self.assertIs(context1.original_request, request)
        self.assertIs(context2.original_request, request)
        self.assertTrue(context1.args)
        self.assertFalse(context1.kwargs)
        self.assertFalse(context2.args)
        self.assertFalse(context2.kwargs)

    def test_copy(self):
        request = self.create_example_request()
        context1 = teapot.routing.Context(request)
        context1.args.append("foo")
        context1.args.append("bar")

        context2 = copy.deepcopy(context1)
        self.assertEqual(context1.path, context2.path)
        self.assertEqual(context1.method, context2.method)
        self.assertEqual(context1.scheme, context2.scheme)
        self.assertEqual(context1.accept_language,
                         context2.accept_language)
        self.assertEqual(context1.accept_content,
                         context2.accept_content)
        self.assertIs(context1.original_request, request)
        self.assertIs(context2.original_request, request)
        self.assertEqual(context1.args, context2.args)
        self.assertFalse(context1.kwargs)
        self.assertFalse(context2.kwargs)

        self.assertIsNot(context1.args, context2.args)
        self.assertIsNot(context1.kwargs, context2.kwargs)
        self.assertIsNot(context1.query_data, context2.query_data)

class TestPathFormatter(unittest.TestCase):
    def assertParses(self, format_spec, formatted, parsed, **kwargs):
        formatter = teapot.routing.PathFormatter(
            "{:"+format_spec+"}",
            **kwargs)
        result = formatter.parse(formatted)
        self.assertTrue(result)
        numbered, keywords, remainder = result
        self.assertFalse(remainder)
        self.assertFalse(keywords)
        self.assertEqual(len(numbered), 1)
        self.assertEqual(numbered[0], parsed)

    def assertParsesNot(self, format_spec, formatted, **kwargs):
        formatter = teapot.routing.PathFormatter(
            "{:"+format_spec+"}",
            **kwargs)
        result = formatter.parse(formatted)
        self.assertFalse(result)

    def test_parse_decimal_integer(self):
        self.assertParses("d", "100", 100)
        self.assertParsesNot("2d", "1", strict=True)
        self.assertParses("2d", " 1", 1, strict=True)
        self.assertParses("2d", "12", 12, strict=True)
        self.assertParses("2d", "123", 123, strict=True)
        self.assertParses("02d", "02", 2, strict=True)
        self.assertParsesNot("02d", "2", strict=True)

    def test_parse_binary_integer(self):
        self.assertParses("b", "100", 4)
        self.assertParsesNot("b", "33")

    def test_parse_hexadecimal_integer(self):
        self.assertParses("x", "ff", 255, strict=True)
        self.assertParsesNot("x", "FF", strict=True)
        self.assertParses("X", "FF", 255, strict=True)
        self.assertParsesNot("X", "ff", strict=True)

    def test_parse_string(self):
        self.assertParses("s", "foobar", "foobar")
        self.assertParsesNot("10s", "foobar")
        self.assertParses("6s", "foobar", "foobar")

    def test_parse_float(self):
        self.assertParses("f", "10.1", 10.1)
        self.assertParses("2.1f", "1.1", 1.1)
        self.assertParses("02.1f", "10.1", 10.1, strict=True)
        self.assertParses("2.1f", "10.1", 10.1, strict=True)
        self.assertParses("2.1f", " 0.1", 0.1, strict=True)
        self.assertParsesNot("2.1f", "0.1", strict=True)

    def test_parse_multiple(self):
        formatter = teapot.routing.PathFormatter(
            "foo: {:.2f}, bar: {baz:d}")
        result = formatter.parse("foo: +3.14159, bar: 42rem")
        self.assertTrue(result)
        numbered, keywords, remainder = result
        self.assertSequenceEqual(
            numbered,
            [3.14159])
        self.assertDictEqual(
            keywords,
            {"baz": 42})
        self.assertEqual(remainder, "rem")


class TestRoutingMeta(unittest.TestCase):
    def test_creation_of_class_route_information(self):
        class Test(metaclass=teapot.RoutableMeta):
            @teapot.route("foo")
            def test(self):
                return self

        self.assertTrue(teapot.isroutable(Test))
        info = teapot.getrouteinfo(Test)
        self.assertEqual(len(info.instance_routenodes), 1)
        self.assertEqual(len(info.routenodes), 0)

    def test_instanciation_of_object_information(self):
        class Test(metaclass=teapot.RoutableMeta):
            @teapot.route("foo")
            def test(self):
                return self

        self.assertTrue(teapot.isroutable(Test))

        instance = Test()
        self.assertTrue(teapot.isroutable(instance))
        info1 = teapot.getrouteinfo(instance)
        self.assertNotIsInstance(info1, teapot.routing.Class)
        self.assertFalse(hasattr(info1, "_instanceroutables"))
        info2 = teapot.getrouteinfo(instance)
        self.assertIs(info1, info2)

        self.assertIs(
            info1.routenodes[0].callable(),
            instance)

    def test_routable_inheritance(self):
        class TestBase(metaclass=teapot.RoutableMeta):
            @teapot.route("foo")
            def test(self):
                return TestBase

        class TestSub(TestBase):
            @teapot.route("bar")
            def test(self):
                return TestSub

        self.assertTrue(teapot.isroutable(TestSub))

        info = teapot.getrouteinfo(TestSub)

        self.assertEqual(len(info.instance_routenodes), 2)
        self.assertEqual(len(info.routenodes), 0)

    def test_specialization_of_prototypes_in_getrouteinfo(self):
        class TestFoo(metaclass=teapot.RoutableMeta):
            @teapot.route("foo")
            @staticmethod
            def foo():
                pass

            @teapot.route("bar")
            @classmethod
            def bar(cls):
                pass

            @teapot.route("baz")
            def baz(cls):
                pass

        test = TestFoo()
        self.assertFalse(hasattr(
            teapot.getrouteinfo(test.foo),
            "get"))
        self.assertFalse(hasattr(
            teapot.getrouteinfo(test.bar),
            "get"))
        self.assertFalse(hasattr(
            teapot.getrouteinfo(test.baz),
            "get"))

    def test_constructor_routability(self):
        class Foo:
            pass

        self.assertRaises(
            TypeError,
            teapot.route("/index"),
            Foo)

        foo_class = teapot.route("/index", make_constructor_routable=True)(Foo)
        self.assertIs(foo_class, Foo)
        self.assertTrue(teapot.isroutable(Foo))

class TestRouting(unittest.TestCase):
    def get_routed_args(self, **context_kwargs):
        root = SomeRoutable()
        request = teapot.routing.Context(None, **context_kwargs)
        success, data = teapot.routing.find_route(root, request)
        self.assertTrue(success)
        self.assertIsNotNone(data)

        data()

        return root.args, root.kwargs

    def setUp(self):
        self._root = SomeRoutable()

    def test_route_simple(self):
        request = teapot.routing.Context(
            None,
            path="/index")
        success, data = teapot.routing.find_route(
            self._root, request)
        self.assertTrue(success)

    def test_route_multirebase(self):
        request = teapot.routing.Context(
            None,
            path="/foo/fnord")
        success, data = teapot.routing.find_route(
            self._root, request)
        self.assertTrue(success)

    def test_route_not_found(self):
        request = teapot.routing.Context(
            None,
            path="/foo/bar")
        success, data = teapot.routing.find_route(
            self._root, request)
        self.assertFalse(success)
        self.assertIsNone(data)

    def test_route_formatted(self):
        args, kwargs = self.get_routed_args(path="/p/42")
        self.assertSequenceEqual([42], args)

    def tearDown(self):
        del self._root

class TestUnrouting(unittest.TestCase):
    def setUp(self):
        self._root = SomeRoutable()

    def test_unrouting_unwinds_correctly_for_instancemethods(self):
        routeinfo = teapot.getrouteinfo(self._root.index)
        self.assertSequenceEqual(
            list(teapot.routing.traverse_to_root(routeinfo)),
            [routeinfo,
             teapot.getrouteinfo(self._root)]
        )

    def test_unrouting_of_path(self):
        self.assertEqual(
            teapot.routing.unroute(self._root.index).path,
            "/")

        self.assertEqual(
            teapot.routing.unroute(self._root.fnord).path,
            "/foo/fnord")

    def test_unrouting_with_format(self):
        self.assertEqual(
            teapot.routing.unroute(
                self._root.formatted,
                42).path,
            "/p/42")

    def tearDown(self):
        del self._root
