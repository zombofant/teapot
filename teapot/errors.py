import teapot.response

class ResponseError(teapot.response.Response, Exception):
    http_response_code = 500

    def __init__(self, response_code, content_type, body, response_message=None):
        super().__init__(content_type,
                         body=body,
                         response_code=response_code,
                         response_message=response_message)


def make_response_error(response_code, plain_message, **kwargs):
    return ResponseError(response_code,
                         teapot.response.MIMEType.text_plain,
                         plain_message,
                         **kwargs)
