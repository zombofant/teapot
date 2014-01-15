import codecs
import copy
import logging
import itertools

import teapot.accept

logger = logging.getLogger(__name__)

class MIMEType:
    def __init__(self, type_, subtype,
                 charset=None,
                 custom_parameters={}):
        self.__type = type_
        self.__subtype = subtype
        self.__parameters = dict(custom_parameters)
        charset = charset or custom_parameters.get("charset", None)
        if charset is not None:
            codec = codecs.lookup(charset)
            charset = codec.name

        if charset is None:
            try:
                del self.__parameters["charset"]
            except KeyError:
                pass
        else:
            self.__parameters["charset"] = charset

    def __copy__(self):
        return MIMEType(self.__type, self.__subtype,
                        custom_parameters=copy.copy(self.__parameters))

    def with_charset(self, charset):
        return MIMEType(self.__type, self.__subtype,
                        charset=charset,
                        custom_parameters=copy.copy(self.__parameters))

    @property
    def charset(self):
        return self.__parameters.get("charset", None)

    def get_custom_parameter(self, key):
        return self.__parameters[key]

    def __str__(self):
        base = "{}/{}".format(self.__type, self.__subtype)
        if self.__parameters:
            base += "; " + "; ".join(
                "{!s}={!s}".format(k, v)
                for k, v in self.__parameters.items())
        return base

    def __repr__(self):
        return "{}({}, {}, parameters={})".format(
            self.__qualname__,
            self.__type,
            self.__subtype,
            repr(self.__parameters))

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

    def __init__(self, content_type, body=None):
        self.content_type = copy.copy(content_type)
        self.body = body

        if self.content_type.charset is not None \
           and isinstance(body, str):
            logger.info("Response constructed with fixed-charset"
                        " content type. Browsers might not like"
                        "this.")
            self.body = self.body.encode(self.content_type.charset)

    def negotiate_charset(self, preference_list, strict=False):
        if not isinstance(self.body, str):
            # we do not change anything for already encoded blobs
            return

        candidates = (pref.value
                       for pref
                       in preference_list.get_sorted_by_preference())
        candidates = list(itertools.islice(candidates, 4))
        if "utf-8" not in candidates and not strict:
            candidates.append("utf-8")

        for i, candidate in enumerate(candidates):
            try:
                self.body = self.body.encode(candidate)
            except UnicodeEncodeError:
                if i == len(candidates)-1:
                    raise
            else:
                break

        self.content_type = self.content_type.with_charset(candidate)
