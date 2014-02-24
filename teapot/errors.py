"""
Throwable error responses
#########################

.. autofunction:: make_response_error

.. autoclass:: ResponseError
   :members:

"""

import teapot.response
import teapot.mime

class ResponseError(teapot.response.Response, Exception):
    """
    This is a :class:`~teapot.response.Response` object which is mixed with a
    :class:`Exception` so that it can be thrown as an exception.

    The arguments are the same as the respective arguments of the
    :class:`~teapot.response.Response` class. The message of the exception is
    the status line of the HTTP response (that is, status code concatenated with
    a space and the status message).
    """
    http_response_code = 500

    def __init__(self, response_code, content_type, body, response_message=None):
        super().__init__(content_type,
                         body=body,
                         response_code=response_code,
                         response_message=response_message)
        self.args = ["{} {}".format(self.http_response_code,
                                    self.http_response_message)]


def make_response_error(response_code, plain_message, **kwargs):
    """
    Create a ``text/plain`` :class:`~teapot.response.Response` using the given
    *response_code* as status code and the given *plain_message* as plain text
    response.
    """
    return ResponseError(response_code,
                         teapot.mime.Type.text_plain,
                         plain_message,
                         **kwargs)

make_error_response = make_response_error
