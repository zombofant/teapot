import lxml.builder

class NamespaceMeta(type):
    """
    Metaclass for namespace classes. Namespace classes must have an *xmlns*
    attribute which is the XML namespace they're representing. They may have
    a *cache* attribute which must be an iterable of strings. The contained
    strings will be precached.

    To retrieve the element name of an :class:`~xml.etree.ElementTree.Element`,
    access the elements name as attribute on a class using the namespace
    metaclass.
    """

    def __new__(mcls, name, bases, namespace):
        cache = namespace.get("cache", [])
        namespace["cache"] = dict()
        namespace["__init__"] = None
        cls = super(NamespaceMeta, mcls).__new__(mcls, name, bases, namespace)
        # prepopulate cache
        for entry in cache:
            getattr(cls, entry)
        namespace["cache"]["xmlns"] = namespace["xmlns"]
        namespace["cache"]["maker"] = lxml.builder.ElementMaker(
            namespace=namespace["xmlns"])
        return cls

    def __call__(cls, name, *args, **kwargs):
        return getattr(cls.__dict__["cache"]["maker"], name)(*args, **kwargs)

    def __getattr__(cls, name):
        cache = cls.__dict__["cache"]
        try:
            return cache[name]
        except KeyError:
            attr = "{{{0}}}{1}".format(cls.xmlns, name)
            cache[name] = attr
        return attr

    def __str__(cls):
        return cls.__dict__["xmlns"]

    def __repr__(cls):
        return "<xml namespace {!r}>".format(cls.__dict__["xmlns"])

class xml(metaclass=NamespaceMeta):
    xmlns = "http://www.w3.org/XML/1998/namespace"
    cache = {"id"}
