"""
WSGI interface
##############

This module provides a class to provide an interface to a WSGI compatible
server.

.. autoclass:: Application
   :members:

"""

import itertools
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

    def forward_response(self, start_response, environ, response):
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
        return self._generate_response(
            start_response,
            environ,
            response,
            iter([] if response.body is None else [response.body]))

    def handle_decoding_error(self, s):
        """
        Handler for a decoding error of any request argument *s*. By default, it
        logs the request argument and creates a ``400 Bad Request`` response.
        """
        logger.error("cannot decode %r as utf8", s)
        raise teapot.errors.make_response_error(
            400, "cannot decode {!r} as utf8".format(s))

    def handle_exception(self, exc):
        logger.exception(exc)
        raise teapot.errors.make_response_error(
            500, teapot.response.lookup_response_message(500))

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

    def handle_pre_start_response_error(self, start_response, environ, error):
        """
        Handle an exception which happens before the response has started.

        *error* is the exception object, which must also be a
        :class:`~teapot.response.Response` instance and *start_response* must be
        the well known callable from the WSGI interface.
        """
        return self.forward_response(start_response, environ, error)

    def _start_response(self, start_response, response_obj):
        start_response(
            "{:03d} {}".format(
                response_obj.http_response_code,
                response_obj.http_response_message),
            list(response_obj.get_header_tuples())
        )

    @staticmethod
    def _file_wrapper(filelike, block_size=8192):
        with filelike as f:
            data = f.read(block_size)
            while data:
                yield data
                data = f.read(block_size)

    def _generate_response(self, start_response, environ,
                           response_obj, result_iter):
        self._start_response(start_response, response_obj)
        try:
            first_object = next(result_iter)
        except StopIteration:
            logger.debug("empty sequence response")
            return []

        if hasattr(first_object, "read"):
            try:
                file_wrapper = environ["wsgi.file_wrapper"]
            except KeyError:
                logger.info("non-wrapped file, reading whole file chunkedly")
                return self._file_wrapper(first_object)
            else:
                logger.debug("wrapped file")
                return file_wrapper(first_object)
        else:
            logger.debug("normal, iterable response")
            return itertools.chain((first_object,), result_iter)

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

                request = teapot.request.Request.construct_from_http(
                    environ["REQUEST_METHOD"],
                    local_path,
                    environ["wsgi.url_scheme"],
                    query_data,
                    environ["wsgi.input"],
                    environ.get("CONTENT_LENGTH"),
                    environ.get("CONTENT_TYPE"),
                    (
                        (k[5:].replace("_", "-"), v)
                        for k, v in environ.items()
                        if k.startswith("HTTP_")
                    ),
                    environ.get("SCRIPT_NAME"),
                    environ.get("SERVER_PORT"))

                result = iter(self._router.route_request(request))
                headers = next(result)
            except teapot.errors.ResponseError as err:
                # forward to next layer of processing
                raise
            except Exception as err:
                return self.handle_exception(err)
        except teapot.errors.ResponseError as err:
            return self.handle_pre_start_response_error(
                start_response, environ, err)

        return self._generate_response(
            start_response,
            environ,
            headers,
            result)
