import unittest
import copy
import io

import teapot
import teapot.routing
import teapot.request

from datetime import datetime, timedelta

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

    @teapot.queryarg("foo", "bar", argtype=str)
    @teapot.route("querytest_single")
    def fooquery_single(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    @teapot.queryarg("foo", "bar", argtype=[str])
    @teapot.route("querytest_list")
    def fooquery_list(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    @teapot.queryarg("foo", None, argtype=[str], unpack_sequence=True)
    @teapot.route("querytest_unpack_list")
    def fooquery_list_unpack(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    @teapot.queryarg("foo", "bar", argtype=(str, str))
    @teapot.route("querytest_tuple")
    def fooquery_tuple(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    @teapot.queryargs()
    @teapot.route("querytest_all")
    def querytest_all(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    @teapot.queryargs("query_dict")
    @teapot.route("querytest_all_destarg")
    def querytest_all_destarg(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    @teapot.route("finaltest", order=0)
    def finaltest_1(self):
        self.args = [1]
        self.kwargs = {}

    @teapot.route("finaltestfoo", order=1)
    def finaltest_2(self):
        self.args = [2]
        self.kwargs = {}

    @teapot.route("finaltestbar", order=-1)
    def finaltest_3(self):
        self.args = [3]
        self.kwargs = {}

    @teapot.route("annotationtest")
    def annotationtest(self, request: teapot.request.Request):
        self.args = request
        self.kwargs = {}

class TestContext(unittest.TestCase):
    method = teapot.request.Method.GET
    path = "/foo/bar"
    scheme = "https"
    query_data = {}
    post_data = {}
    cookie_data = {}
    accept_info = teapot.accept.all_content_types(), \
                  teapot.accept.all_languages(), \
                  teapot.accept.all_charsets()

    def create_example_request(self):
        return teapot.request.Request(
            self.method,
            self.path,
            self.scheme,
            self.query_data,
            self.cookie_data,
            self.accept_info,
            "",
            io.BytesIO(b""),
            )

    def test_initialization_from_request(self):
        request = self.create_example_request()
        context = teapot.routing.Context.from_request(request)
        self.assertEqual(context.path, request.path)
        self.assertEqual(context.method, request.method)
        self.assertEqual(context.scheme, request.scheme)
        self.assertEqual(context.accept_language, request.accept_language)
        self.assertEqual(context.accept_content, request.accept_content)
        self.assertIs(context.original_request, request)

    def test_copy_construction(self):
        request = self.create_example_request()
        context1 = teapot.routing.Context.from_request(request)
        context1.args.append("foo")
        context1.args.append("bar")

        context2 = teapot.routing.Context.from_request(context1)
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
        context1 = teapot.routing.Context.from_request(request)
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

class Test_formatted_path(unittest.TestCase):
    def assertParses(self, format_spec, formatted, parsed, **kwargs):
        formatter = teapot.routing.formatted_path(
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
        formatter = teapot.routing.formatted_path(
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
        formatter = teapot.routing.formatted_path(
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
        request = teapot.routing.Context(**context_kwargs)
        success, data = teapot.routing.find_route(root, request)
        self.assertTrue(success)
        self.assertIsNotNone(data)

        data()

        return root.args, root.kwargs

    def setUp(self):
        self._root = SomeRoutable()

    def test_simple(self):
        request = teapot.routing.Context(
            path="/index")
        success, data = teapot.routing.find_route(
            self._root, request)
        self.assertTrue(success)

    def test_multirebase(self):
        request = teapot.routing.Context(
            path="/foo/fnord")
        success, data = teapot.routing.find_route(
            self._root, request)
        self.assertTrue(success)

    def test_not_found(self):
        request = teapot.routing.Context(
            path="/foo/bar")
        success, data = teapot.routing.find_route(
            self._root, request)
        self.assertFalse(success)
        self.assertIsNone(data)

    def test_formatted(self):
        args, kwargs = self.get_routed_args(path="/p/42")
        self.assertSequenceEqual([42], args)

    def test_query_single(self):
        args, kwargs = self.get_routed_args(
            path="/querytest_single",
            query_data={"foo": ["value"]})

        self.assertSequenceEqual(
            [],
            args)
        self.assertDictEqual(
            {"bar": "value"},
            kwargs)

    def test_query_list(self):
        values = list(map(str, range(3)))
        args, kwargs = self.get_routed_args(
            path="/querytest_list",
            query_data={"foo": values[:]})

        self.assertSequenceEqual(
            [],
            args)
        self.assertDictEqual(
            {"bar": values},
            kwargs)

    def test_query_list_unpack(self):
        values = list(map(str, range(3)))
        args, kwargs = self.get_routed_args(
            path="/querytest_unpack_list",
            query_data={"foo": values[:]})

        self.assertSequenceEqual(
            values,
            args)
        self.assertDictEqual(
            {},
            kwargs)

    def test_query_tuple(self):
        values = list(map(str, range(3)))
        args, kwargs = self.get_routed_args(
            path="/querytest_tuple",
            query_data={"foo": values[:]})

        self.assertSequenceEqual(
            [],
            args)
        self.assertDictEqual(
            {"bar": tuple(values[:2])},
            kwargs)

    def test_route_query_all(self):
        the_dict = {"foo": "bar"}
        args, kwargs = self.get_routed_args(
                path="/querytest_all",
                query_data=the_dict)

        self.assertDictEqual({}, kwargs)
        self.assertSequenceEqual([the_dict], args)

    def test_route_query_all_destarg(self):
        the_dict = {"foo": "bar"}
        args, kwargs = self.get_routed_args(
                path="/querytest_all_destarg",
                query_data=the_dict)

        self.assertDictEqual(
                {"query_dict": the_dict},
                kwargs)
        self.assertSequenceEqual(
                [],
                args)

    def test_ambigous_nonfinal_routing(self):
        args, kwargs = self.get_routed_args(
            path="/finaltest")

        self.assertSequenceEqual([1], args)
        self.assertDictEqual({}, kwargs)

    def test_request_annotation(self):
        root = SomeRoutable()
        request = teapot.request.Request(
            teapot.request.Method.GET,
            "/annotationtest",
            "http",
            {},
            {},
            (
                teapot.accept.all_content_types(),
                teapot.accept.all_languages(),
                teapot.accept.all_charsets()
            ),
            "",
            None)
        success, data = teapot.routing.find_route(root, request)
        self.assertTrue(success)
        self.assertIsNotNone(data)
        data()

        self.assertIs(request, root.args)

    def tearDown(self):
        del self._root

class TestUnrouting(unittest.TestCase):
    def setUp(self):
        self._root = SomeRoutable()

    def test_unwinds_correctly_for_instancemethods(self):
        routeinfo = teapot.getrouteinfo(self._root.index)
        self.assertSequenceEqual(
            list(teapot.routing.traverse_to_root(routeinfo)),
            [routeinfo,
             teapot.getrouteinfo(self._root)]
        )

    def test_path(self):
        self.assertEqual(
            teapot.routing.unroute(self._root.index).path,
            "/")

        self.assertEqual(
            teapot.routing.unroute(self._root.fnord).path,
            "/foo/fnord")

    def test_with_format(self):
        self.assertEqual(
            teapot.routing.unroute(
                self._root.formatted,
                42).path,
            "/p/42")

    def test_query_single(self):
        request = teapot.routing.unroute(
            self._root.fooquery_single,
            bar="value")
        self.assertDictEqual(
            request.query_data,
            {"foo": ["value"]})

        self.assertRaises(
            ValueError,
            teapot.routing.unroute,
            self._root.fooquery_single)

    def test_query_list(self):
        values = list(map(str, range(10)))
        request = teapot.routing.unroute(
            self._root.fooquery_list,
            bar=values)
        self.assertDictEqual(
            request.query_data,
            {"foo": values})

        self.assertRaises(
            ValueError,
            teapot.routing.unroute,
            self._root.fooquery_single)

    def test_query_list_unpacked(self):
        values = list(map(str, range(10)))
        request = teapot.routing.unroute(
            self._root.fooquery_list_unpack,
            *values)
        self.assertDictEqual(
            request.query_data,
            {"foo": values})

    def test_query_tuple(self):
        values = list(map(str, range(2)))
        request = teapot.routing.unroute(
            self._root.fooquery_tuple,
            bar=values)
        self.assertDictEqual(
            request.query_data,
            {"foo": values})
        self.assertRaises(
            ValueError,
            teapot.routing.unroute,
            self._root.fooquery_single)

    def test_query_all(self):
        the_dict = {"foo": "value"}
        request = teapot.routing.unroute(
                self._root.querytest_all,
                the_dict)
        self.assertDictEqual(
                request.query_data,
                the_dict)

    def test_query_destarg(self):
        the_dict = {"foo": "value"}
        request = teapot.routing.unroute(
                self._root.querytest_all_destarg,
                query_dict=the_dict)
        self.assertDictEqual(
                request.query_data,
                the_dict)

    def tearDown(self):
        del self._root


class TestRouter(unittest.TestCase):
    class Routable(metaclass=teapot.RoutableMeta):
        def __init__(self, last_modified):
            self._last_modified = last_modified

        @teapot.route("/")
        def index(self):
            response = teapot.response.Response(
                teapot.mime.Type.text_plain.with_charset("utf8"),
                last_modified=self._last_modified)

            yield response

            yield "ohai".encode(response.content_type.charset)

    def get_router(self):
        return teapot.routing.Router(
            self._root)

    def setUp(self):
        self._now = datetime.utcnow()
        self._root = self.Routable(self._now)

    def test_response(self):
        router = self.get_router()
        request = teapot.request.Request()

        result = list(router.route_request(request))
        response = result.pop(0)
        self.assertEqual(response.content_type,
                         teapot.mime.Type.text_plain.with_charset("utf8"))
        self.assertSequenceEqual(result, [b"ohai"])

    def test_304_not_modified(self):
        router = self.get_router()
        request = teapot.request.Request(
            if_modified_since=self._now)

        with self.assertRaises(teapot.errors.ResponseError) as ctx:
            list(router.route_request(request))

        self.assertEqual(ctx.exception.http_response_code, 304)

    def tearDown(self):
        del self._root
        del self._now
