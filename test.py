import teapot
import teapot.mime
import teapot.wsgi
import teapot.response

@teapot.rebase("/")
class Test(metaclass=teapot.routing.RoutableMeta):
    def __init__(self, a, b):
        self._a = a
        self._b = b

    @teapot.route("", "index")
    def index(self):
        response = teapot.response.Response(
            teapot.mime.Type.text_plain,
            body="{}".format(self._a))

        return response

    @teapot.route("foo")
    def foo(self):
        response = teapot.response.Response(
            teapot.mime.Type.text_plain.with_charset("utf8"))

        yield response

        yield "{}".format(self._b).encode(
            response.content_type.charset)

test = Test(10, 20)

import wsgiref.simple_server

httpd = wsgiref.simple_server.make_server(
    '', 8000,
    teapot.wsgi.Application(
        teapot.routing.Router(test)))

httpd.serve_forever()
