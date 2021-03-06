"""
MIME type representation
########################

The :mod:`~teapot.mime` module provides utilities to represent MIME types.

.. autoclass:: Type
   :members:
"""
import copy
import codecs
import itertools

def normalize_charset(charset):
    """
    Normalize the given *charset* using the python codec database. The charset
    ``binary`` is treated specially and returnet verbatim.
    """

    if charset == "binary":
        return charset

    codec = codecs.lookup(charset)
    return codec.name

class Type:
    """
    This is a immutable class which represents a MIME type. Through
    immutability, instances can be arbitrarily reused.

    *type_* and *subtype* comprise the MIME type. *charset* is the ``charset``
    attribute, which must be a string representing the encoding. It is
    canonicalized through :func:`codecs.lookup`.

    *custom_parameters* can be a dictionary adding more custom parameters to the
    MIME type. Any specific keyword arguments for parameters (such as *charset*)
    override the settings provided in this dictionary.

    Comparision operators for equality exist. The following attributes provides
    global instances of commonly used MIME types.

    .. attribute:: text_plain

       ``text/plain`` MIME type.

    .. attribute:: text_html

       ``text/html`` MIME type.

    The following further members exist:
    """

    def __init__(self, type_, subtype,
                 charset=None,
                 custom_parameters={}):
        self.__type = type_
        self.__subtype = subtype
        self.__parameters = dict(custom_parameters)
        charset = charset or custom_parameters.get("charset", None)
        if charset is not None:
            charset = normalize_charset(charset)

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
        """
        Return a copy of this :class:`Type` with a different *charset*.
        """
        return Type(self.__type, self.__subtype,
                    charset=charset,
                    custom_parameters=copy.copy(self.__parameters))

    @property
    def type(self):
        return self.__type

    @property
    def subtype(self):
        return self.__subtype

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
            type(self).__qualname__,
            self.__type,
            self.__subtype,
            repr(self.__parameters))

    def __eq__(self, other):
        return (self.__type == other.__type and
                self.__subtype == other.__subtype and
                self.__parameters == other.__parameters)

    def __neq__(self, other):
        return not (self == other)

    def __hash__(self):
        return hash((self.__type, self.__subtype,
                     frozenset(self.__parameters.items())))

Type.text_plain = Type("text", "plain")
Type.text_html = Type("text", "html")
Type.application_xhtml = Type("application", "xhtml+xml")
Type.application_xml = Type("application", "xml")

class CaseFoldedDict(dict):
    class __undefined:
        pass

    _transform_key = staticmethod(str.casefold)

    @classmethod
    def _transform_item(cls, item):
        return (cls._transform_key(item[0]), item[1])

    @classmethod
    def _transform_items_iterable(cls, iterable):
        return map(cls._transform_item, iterable)

    @classmethod
    def _items_iterable_from_mapping_or_iterable(
            cls, mapping_or_iterable):
        try:
            items_iterable = mapping_or_iterable.items()
        except AttributeError:
            items_iterable = mapping_or_iterable
        return cls._transform_items_iterable(items_iterable)

    def __init__(self, mapping_or_iterable=__undefined, **kwargs):
        if mapping_or_iterable is not self.__undefined:
            items_iterable = self._items_iterable_from_mapping_or_iterable(
                mapping_or_iterable)
        else:
            items_iterable = None

        if kwargs:
            if items_iterable is not None:
                items_iterable = itertools.chain(
                    items_iterable,
                    self._transform_items_iterable(kwargs.items()))
            else:
                items_iterable = self._transform_items_iterable(kwargs.items())

        if items_iterable is not None:
            super().__init__(items_iterable)
        else:
            super().__init__()

    def __delitem__(self, key):
        return super().__delitem__(self._transform_key(key))

    def __getitem__(self, key):
        return super().__getitem__(self._transform_key(key))

    def __setitem__(self, key, value):
        return super().__setitem__(self._transform_key(key), value)

    def get(self, key, *args, **kwargs):
        return super().get(self._transform_key(key), *args, **kwargs)

    @classmethod
    def fromkeys(cls, sequence, *args, **kwargs):
        return super().fromkeys(
            map(cls._transform_key, sequence), *args, **kwargs)

    def pop(self, key, *args, **kwargs):
        return super().pop(self._transform_key(key), *args, **kwargs)

    def update(self, other):
        super().update(
            self._items_iterable_from_mapping_or_iterable(other))
