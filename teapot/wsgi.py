"""
WSGI interface
##############

This module provides a class to provide an interface to a WSGI compatible
server.

.. autoclass:: Application
   :members:

"""

import logging

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
            response.get_header_tuples()
        )
        return [response.body]

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
                if not local_path and self._force_slash_root:
                    local_path = "/"

                try:
                    local_path = local_path.encode("latin1")
                    local_path = local_path.decode("utf8")
                except UnicodeEncodeError as err:
                    # in this case, the path seems to be encoded already and we
                    # ignore the error
                    pass
                except UnicodeDecodeError as err:
                    # no incoming UTF-8. we Bad Request it.
                    return self.handle_path_decoding_error(local_path)

                request = teapot.request.Request(
                    environ["REQUEST_METHOD"],
                    local_path,
                    environ["wsgi.url_scheme"],
                    {},
                    (
                        None,
                        None,
                        teapot.accept.CharsetPreferenceList()
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
            headers.get_header_tuples())

        yield from result
