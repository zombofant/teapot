"""
``xsltea.namespaces`` – XML namespace utilities
###############################################

This module contains some utilities to work with XML namespaces and the
ElementTree API. Besides predefined namespaces, the :class:`NamespaceMeta`
metaclass is available to define custom namespaces.

.. autoclass:: NamespaceMeta

Predefined namespaces
=====================

.. autoclass:: xml

For internal use only
---------------------

.. autoclass:: shared_ns

.. autoclass:: internal_copyable_ns

.. autoclass:: internal_noncopyable_ns
"""

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
    """
    Defines the ``http://www.w3.org/XML/1998/namespace`` namespace, used for
    example for the ``@xml:id`` attribute.
    """

    xmlns = "http://www.w3.org/XML/1998/namespace"
    cache = {"id"}

class xhtml_ns(metaclass=NamespaceMeta):
    """
    Defines the ``http://www.w3.org/1999/xhtml`` namespace.
    """

    xmlns = "http://www.w3.org/1999/xhtml"

class xlink_ns(metaclass=NamespaceMeta):
    """
    Defines the ``http://www.w3.org/1999/xlink`` namespace.
    """

    xmlns = "http://www.w3.org/1999/xlink"

class svg_ns(metaclass=NamespaceMeta):
    """
    Defines the ``http://www.w3.org/2000/svg`` namespace.
    """

    xmlns = "http://www.w3.org/2000/svg"

class shared_ns(metaclass=NamespaceMeta):
    """
    Defines the ``https://xmlns.zombofant.net/xsltea/processors`` namespace,
    which is used by multiple processors. It is best bound to the ``tea:``
    prefix.

    Do **not** use this for your own processors. This namespace is reserved.
    """

    xmlns = "https://xmlns.zombofant.net/xsltea/processors"

class internal_copyable_ns(metaclass=NamespaceMeta):
    """
    Defines an internal namespace for attributes which are to be preserved
    across tree deepcopy operations.
    """

    xmlns = "https://xmlns.zombofant.net/xsltea/internal#copyable"

class internal_noncopyable_ns(metaclass=NamespaceMeta):
    """
    Defines an internal namespace for attributes which are *not* preserved
    across tree deepcopy operations (they will be missing in the new copy).
    """

    xmlns = "https://xmlns.zombofant.net/xsltea/internal#noncopyable"
