import codecs
import copy
import logging
import itertools

import teapot.accept
import teapot.timeutils

logger = logging.getLogger(__name__)

def lookup_response_message(response_code, default="Unknown Status"):
    """
    Look up the status code message as defined in RFC 2616 using the given
    *response_code*. If the *response_code* is unknown, the given *default* is
    used.
    """
    return {
        100: "Continue",
        101: "Switching Protocols",
        200: "OK",
        201: "Created",
        202: "Accepted",
        203: "Non-Authoritative Information",
        204: "No Content",
        205: "Reset Content",
        206: "Partial Content",
        300: "Multiple Choices",
        301: "Moved Permanently",
        302: "Found",
        303: "See Other",
        304: "Not Modified",
        305: "Use Proxy",
        306: "(Unused)",
        307: "Temporary Redirect",
        400: "Bad Request",
        401: "Unauthorized",
        402: "Payment Required",
        403: "Forbidden",
        404: "Not Found",
        405: "Method Not Allowed",
        406: "Not Acceptable",
        407: "Proxy Authentication Required",
        408: "Request Timeout",
        409: "Conflict",
        410: "Gone",
        411: "Length Required",
        412: "Precondition Failed",
        413: "Request Entity Too Large",
        414: "Request-URI Too Long",
        415: "Unsupported Media Type",
        416: "Requested Range Not Satisfiable",
        417: "Expectation Failed",
        500: "Internal Server Error",
        501: "Not Implemented",
        502: "Bad Gateway",
        503: "Service Unavailable",
        504: "Gateway Timeout",
        505: "HTTP Version Not Supported",
    }.get(response_code, default)

class Response:
    charset_preferences = [
        # prefer UTF-8, then go through the other unicode encodings in
        # ascending order of size. prefer little-endian over big-endian
        # encodings
        teapot.accept.CharsetPreference("utf-8", 1.0),
        teapot.accept.CharsetPreference("utf-16le", 0.95),
        teapot.accept.CharsetPreference("utf-16be", 0.9),
        teapot.accept.CharsetPreference("utf-32le", 0.75),
        teapot.accept.CharsetPreference("utf-32be", 0.7),
        teapot.accept.CharsetPreference("latin1", 0.6)
    ]

    def __init__(self,
                 content_type,
                 body=None,
                 response_code=200,
                 response_message=None,
                 last_modified=None):
        super().__init__()
        self.http_response_code = response_code
        self.http_response_message = response_message or \
                                     lookup_response_message(response_code)
        self.content_type = copy.copy(content_type)
        self.body = body
        self.last_modified = last_modified

        if self.content_type and \
           self.content_type.charset is not None \
           and isinstance(body, str):
            logger.info("Response constructed with fixed-charset"
                        " content type. Browsers might not like"
                        "this.")
            self.body = self.body.encode(self.content_type.charset)

    def get_header_tuples(self):
        if self.content_type:
            yield ("Content-Type", str(self.content_type))
        if self.last_modified:
            yield ("Last-Modified",
                   teapot.timeutils.format_http_date(self.last_modified))


    def negotiate_charset(self, preference_list, strict=False):
        if not isinstance(self.body, str):
            # we do not change anything for already encoded blobs or iterables
            # or anything like that
            return

        candidates = (pref.value
                       for pref
                       in preference_list.get_sorted_by_preference())
        candidates = list(itertools.islice(candidates, 4))
        if "utf-8" not in candidates and not strict:
            candidates.append("utf-8")

        for i, candidate in enumerate(candidates):
            if candidate == "*":
                candidate = "utf8"
            try:
                self.body = self.body.encode(candidate)
            except UnicodeEncodeError:
                if i == len(candidates)-1:
                    raise
            else:
                break

        self.content_type = self.content_type.with_charset(candidate)
