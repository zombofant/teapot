import logging

import teapot.request
import teapot.errors
import teapot.accept
import teapot.routing

logger = logging.getLogger(__name__)

class Application:
    def __init__(self,
                 router,
                 force_slash_root=True):
        self._router = router
        self._force_slash_root = force_slash_root

    def forward_response(self, response, start_response):
        response.negotiate_charset(teapot.accept.CharsetPreferenceList())
        start_response(
            "{:03d} {}".format(
                response.http_response_code,
                response.http_response_message),
            [("Content-Type", str(response.content_type))]
        )
        return [response.body]

    def handle_decoding_error(self, s):
        logger.error("cannot decode %r as utf8", s)
        raise teapot.errors.make_response_error(
            400, "cannot decode {!r} as utf8".format(s))

    def handle_path_decoding_error(self, path):
        self.handle_decoding_error(path)

    def handle_pre_start_response_error(self, error, start_response):
        return self.forward_response(error, start_response)

    def __call__(self, environ, start_response):
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
