"""
WSGI interface
##############

This module provides a class to provide an interface to a WSGI compatible
server.

.. autoclass:: Application
   :members:

"""

import logging
import urllib.parse

import teapot.request
import teapot.errors
import teapot.accept
import teapot.routing

logger = logging.getLogger(__name__)

class Application:
    """
    Instances of this class are suitable for passing them as WSGI application
    object.

    The *router* should be a :class:`~teapot.routing.Router` instance which can
    be used to resolve all requests of your application.

    If *force_slash_root* is set to :data:`True`, requests pointing to empty
    string (``b""``) will be rewritten to ``b"/"``.
    """

    def __init__(self,
                 router,
                 force_slash_root=True):
        self._router = router
        self._force_slash_root = force_slash_root

    def decode_string(self, s):
        if isinstance(s, str):
            try:
                s = s.encode("latin1")
            except UnicodeEncodeError as err:
                # already a proper unicode string
                return s

        return s.decode("utf8")

    def decode_path(self, path):
        try:
            return self.decode_string(path)
        except UnicodeDecodeError as err:
            return self.handle_path_decoding_error(path)

    def decode_query_string(self, query):
        try:
            query = self.decode_string(query)
        except UnicodeDecodeError as err:
            query = self.handle_query_decoding_error(query)

        return urllib.parse.parse_qs(query)

    def forward_response(self, response, start_response):
        """
        Forwards a :class:`~teapot.response.Response` instance (such as from a
        caught :class:`~teapot.errors.ResponseError`) to the WSGI
        interface. This does not do anything fancy and will not even take the
        clients requested encoding into account, which is why this method is
        only used in exceptional cases (i. e. if an exception happens while
        resolving the request).

        *response* must be the response object to forward and *start_response*
        must be the ``start_response`` callable WSGI handed to the application.
        """
        response.negotiate_charset(teapot.accept.CharsetPreferenceList())
        start_response(
            "{:03d} {}".format(
                response.http_response_code,
                response.http_response_message),
            list(response.get_header_tuples())
        )
        if response.body is not None:
            return [response.body]
        else:
            return []

    def handle_decoding_error(self, s):
        """
        Handler for a decoding error of any request argument *s*. By default, it
        logs the request argument and creates a ``400 Bad Request`` response.
        """
        logger.error("cannot decode %r as utf8", s)
        raise teapot.errors.make_response_error(
            400, "cannot decode {!r} as utf8".format(s))

    def handle_path_decoding_error(self, path):
        """
        Forward *path* to :meth:`handle_decoding_error`.
        """
        self.handle_decoding_error(path)

    def handle_query_decoding_error(self, query):
        """
        Forward *query* to :meth:`handle_decoding_error`.
        """
        self.handle_decoding_error(query)

    def handle_pre_start_response_error(self, error, start_response):
        """
        Handle an exception which happens before the response has started.

        *error* is the exception object, which must also be a
        :class:`~teapot.response.Response` instance and *start_response* must be
        the well known callable from the WSGI interface.
        """
        return self.forward_response(error, start_response)

    def __call__(self, environ, start_response):
        """
        Implementation of the WSGI interface specified in PEP 3333.
        """
        try:
            try:
                local_path = environ["PATH_INFO"]
                if not local_path.startswith("/") and self._force_slash_root:
                    local_path = "/"

                local_path = self.decode_path(local_path)
                query_data = self.decode_query_string(
                    environ.get("QUERY_STRING", ""))

                cookie_data = {}
                if "HTTP_COOKIE" in environ:
                    for cookie in map(
                            str.strip,
                            environ["HTTP_COOKIE"].split(";")):
                        key, value = cookie.split("=")
                        cookie_data.setdefault(key, []).append(value)

                request = teapot.request.Request.construct_from_http(
                    environ["REQUEST_METHOD"],
                    local_path,
                    environ["wsgi.url_scheme"],
                    query_data,
                    cookie_data,
                    environ["wsgi.input"],
                    environ.get("CONTENT_LENGTH"),
                    environ.get("CONTENT_TYPE"),
                    (
                        (k[5:].replace("_", "-"), v)
                        for k, v in environ.items()
                        if k.startswith("HTTP_")
                    ))

                result = iter(self._router.route_request(request))
                headers = next(result)
            except teapot.errors.ResponseError as err:
                # forward to next layer of processing
                raise
            except Exception as err:
                logger.exception(err)
                raise teapot.errors.make_response_error(
                    500, str(err))
        except teapot.errors.ResponseError as err:
            return self.handle_pre_start_response_error(
                err, start_response)

        start_response(
            "{:03d} {}".format(
                headers.http_response_code,
                headers.http_response_message),
            list(headers.get_header_tuples()))

        yield from result
