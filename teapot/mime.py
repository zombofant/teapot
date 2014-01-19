import copy
import codecs

class Type:
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
        return Type(self.__type, self.__subtype,
                    custom_parameters=copy.copy(self.__parameters))

    def with_charset(self, charset):
        return Type(self.__type, self.__subtype,
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

Type.text_plain = Type("text", "plain")
