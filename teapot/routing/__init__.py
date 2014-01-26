"""
Routing
#######

Teapot request routing is it’s valuable core. First on nomenclature. We call the
process of dispatching the clients HTTP (or whatever) request to the correct
python function “routing”.

During the process, different attributes of the request are processed to
determine which function is to be called (and with which arguments!). The most
obvious attribute here is the request path, followed by query arguments (the
part behind the ``?`` in the URL) and so on.

There are several methods available for declaring the ``route``, that is, the
set of attributes which must match for the function to be called. These ways are
described below and are mostly implemented using decorators.

The opposite of routing is “unrouting”. When *unrouting*, the user (that is
you!) specifies a function and a set of (possibly named) arguments and teapot
calculates a request object which would select the given function and would make
it being called with the given arguments, if that is possible.

Care has to be taken when using decorators which modify or specify the functions
arguments. It might seem to be straightforward to mix positional and named
arguments arbitrarily, however, there are caveats. If you mix named and
positional arguments, weird behaviour might occur when *unrouting*. The current
recommendation is to only use named arguments, except for passing arguments to
a catchall positional argument (``*foo``). **Don’t-Do-This** Example::

    @teapot.queryarg("arg1", None)   # positional argument
    @teapot.queryarg("arg2", "baz")  # named argument
    @teapot.queryarg("arg3", "kw1")  # named argument
    @teapot.route("/")
    def foo(bar, baz, *args, kw1=None, **kwargs):
        pass

This works perfectly fine for routing, but not for unrouting. In unrouting, you
could want do this, because it makes sense::

    teapot.routing.unroute(foo, "value1", "value2", kw1="value3")

It would not work, however, because the second queryarg will look for ``baz`` in
the *kwargs* dict and won’t find it, thus an error will occur. The only way to
avoid this, to our knowledge, would be to re-implement the argument passing
logic of python, which is not only lots of work, but also error-prone and
possibly (CPython) implementation-specific (not the logic itself, but inspection
of the function signature).

To work around this, a safe way is to only use positional arguments for the
catchall argument and otherwise only keyword arguments.

.. _teapot.routing.return_protocols:

Return protocols
================

Return protocols define the kind of values returned by the routed methods. They
are defined (or supported) by the interface which communicates with the client
(the HTTP interface). However, the default :class:`Router` supports conversion
from different return protocols to the unified return protocol which MUST be
supported by every client interface.

The default :class:`Router` supports three return protocols. In addition to the
specified return values, a callable may also throw
:class:`~teapot.errors.ResponseError` instances. In that case, the thrown
response is treated as if the callable had returned it via the return-by-value
protocol.

return-by-generator
-------------------

The callable is a generator or returns an iterable. The first element of that
iterable is a :class:`~teapot.response.Response` instance with a :data:`None`
value in the :attr:`~teapot.response.Response.body` attribute. The remaining
elements are :class:`bytes` instances which constitute the body of the
response.

The callable takes care of properly encoding the response in a way which the
clients understands.

.. note::

   This is the protocol returned by the :class:`Router` intermediate layer and
   it MUST be natively supported by all client interfaces. Client interfaces
   MUST NOT check for the body attribute of the response, except if they also
   implement the other return protocols (not recommended).

return-by-generator-with-body
-----------------------------

The callable is a generator or returns an iterable. The first element of that
iterable is a :class:`~teapot.response.Response` instance with a proper value in
the :attr:`~teapot.response.Response.body` attribute. After charset
negotiation (via :meth:`~teapot.response.Response.negotiate_charset`), the
:attr:`~teapot.response.Response.body` attribute must be a :class:`bytes`
object or :data:`None`, if no body is to be returned. It is forwarded as the
response body to the client interface.

If the iterator has a :attr:`close` attribute, it is called. The remainder of
the iterator is ignored.

return-by-value
---------------

The callable returns a single value. It is a :class:`~teapot.response.Response`
instance with a proper value in the :attr:`~teapot.response.Response.body`
attribute. After charset negotiation, the :attr:`~teapot.response.Response.body`
attribute must be either an object supporting the buffer protocol
(e.g. :class:`bytes`) or :data:`None`, if no response body is desired. It is
forwarded as the response body to the client interface.

Decorators for functions and methods
====================================

To make a function or other generic callable routable, one has to
decorate it with the ``route`` decorator:

.. autofunction:: route

A class (and its instances) and all of its member functions can be
made routable using the following metaclass:

.. autoclass:: RoutableMeta

.. _teapot.routing.routable_decorators:

Decorators for routables
------------------------

The route of an object which is routable (that is, has been made routable by
applying the :class:`RoutableMeta` class or decorating it with :func:`route`),
the route can further be refined using the following decorators:

.. autoclass:: teapot.routing.selectors.rebase

.. autoclass:: teapot.routing.selectors.queryarg

.. autoclass:: teapot.routing.selectors.postarg

.. autoclass:: teapot.routing.selectors.cookie

.. autoclass:: teapot.routing.selectors.formatted_path

.. autoclass:: teapot.routing.selectors.one_of

.. autoclass:: teapot.routing.selectors.content_type

.. autoclass:: teapot.routing.selectors.method

Utilities to get information from routables
===========================================

These utilities can be used to introspect the routing information of a given
object.

.. autofunction:: teapot.routing.info.isroutable

.. autofunction:: teapot.routing.info.getrouteinfo

.. autofunction:: teapot.routing.info.setrouteinfo

.. autofunction:: teapot.routing.info.requirerouteinfo

Router for server interfaces
============================

Server interfaces require a router which transforms the request into an
iterable which contains all the response metadata and contents.

.. autoclass:: Router
   :members:

Extension API
=============

If you want to extend the routing or implement custom functionallity for the
router, the following classes are of special interest for you. The ``Selector``
class is the base class of all the decorators from the
:ref:`teapot.routing.routable_decorators` section. The :class:`Context` class is
the data class on which the selectors operate.

.. autoclass:: teapot.routing.selectors.Selector
   :members: select, unselect, __call__

.. autoclass:: teapot.routing.selectors.ArgumentSelector

.. autoclass:: Context
   :members:

Internal API
============

This API is subject to unnotified change. Not only the names, attributes and
methods can change, but also the usage. Do not rely on anything here, even if it
is tested against in a testsuite.

.. autoclass:: teapot.routing.info.Info
   :members:

.. autoclass:: teapot.routing.info.Group
   :members:

.. autoclass:: teapot.routing.info.Object
   :members:

.. autoclass:: teapot.routing.info.Class
   :members:

.. autoclass:: teapot.routing.info.Leaf
   :members:

.. autoclass:: teapot.routing.info.MethodLeaf
   :members:

.. autoclass:: teapot.routing.info.LeafPrototype
   :members:

"""
import abc
import copy
import functools
import string
import re
import itertools
import logging

import teapot.errors
import teapot.request
import teapot.routing.info
import teapot.routing.selectors

from .info import *
from .info import routeinfo_attr, setrouteinfo

logger = logging.getLogger(__name__)

__all__ = [
    "route",
    "RoutableMeta"]

class Context:
    """
    The routing context is used to traverse through the request to
    find nodes to route to.

    To create a :class:`Context` from a :class:`~teapot.request.Request`, use
    the :meth:`from_request` class method.

    There is a difference between creating a context with another context as
    *base* argument and copying that context. Upon copying, the arguments which
    have already been found during request resolution are copied too. Thus,
    copying is suitable to have a local copy of the context for the next routing
    step. However, upon creating a context from a context passed as *base*
    argument, the argument lists will be initialized as empty.

    .. note::

       Although they share some concepts, we found it is more reasonable to keep
       the context and the request in separate classes. The rationale is that
       some request information is not needed during routing (such as user agent
       strings). Preserving the ability to cheaply copy requests and being able
       to construct them easily at the same time is more trouble than it’s
       worth.

       In addition we now have a clear definition of which fields of the request
       can be used for routing.
    """

    @classmethod
    def from_request(cls, base):
        """
        Create a blank :class:`Context` from a
        :class:`~teapot.request.Request`.

        .. note::

           *original_request* can also be another :class:`Context` instance, to
           copy a context without carrying any information generated during
           routing, such as function arguments.
        """

        # handy
        if hasattr(base, "original_request"):
            original_request = base.original_request
        else:
            original_request = base

        return cls(
            accept_content=base.accept_content,
            accept_language=base.accept_language,
            original_request=original_request,
            path=base.path,
            query_data=copy.copy(base.query_data),
            request_method=base.method,
            scheme=base.scheme)

    def __init__(self, *,
                 accept_content=None,
                 accept_language=None,
                 request_method=teapot.request.Method.GET,
                 original_request=None,
                 path="/",
                 query_data=None,
                 scheme="http"):
        super().__init__()
        self._args = []
        self._kwargs = {}
        self.content_types = None
        self.languages = None

        self._accept_content = \
            accept_content \
            if accept_content is not None \
            else teapot.accept.all_content_types()

        self._accept_language = \
            accept_language \
            if accept_language is not None \
            else teapot.accept.all_languages()

        self._method = request_method
        self._original_request = original_request
        self.path = path
        self._query_data = {} if query_data is None else query_data
        self._post_data = None
        self._cookie_data = None
        self._scheme = scheme

    def __deepcopy__(self, copydict):
        result = Context.from_request(self)
        result._args = copy.copy(self._args)
        result._kwargs = copy.copy(self._kwargs)
        result.content_types = copy.copy(self.content_types)
        result.languages = copy.copy(self.languages)
        return result

    @property
    def accept_content(self):
        return self._accept_content

    @property
    def accept_language(self):
        return self._accept_language

    @property
    def args(self):
        return self._args

    @args.setter
    def args(self, value):
        self._args[:] = value

    @property
    def kwargs(self):
        return self._kwargs

    @kwargs.setter
    def kwargs(self, value):
        self._kwargs.clear()
        self._kwargs.update(value)

    @property
    def method(self):
        return self._method

    @property
    def original_request(self):
        return self._original_request

    @property
    def query_data(self):
        return self._query_data

    @property
    def post_data(self):
        if self._post_data is None:
            if self._original_request is None:
                self._post_data = {}
            else:
                self._post_data = self._original_request.post_data
        return self._post_data

    @property
    def cookie_data(self):
        if self._cookie_data is None:
            if self._original_request is None:
                self._cookie_data = {}
            else:
                self._cookie_data = self._original_request.cookie_data
        return self._cookie_data

    @property
    def scheme(self):
        return self._scheme

    def rebase(self, prefix):
        """
        Rebases the context by removing the given *prefix* from the
        :attr:`path`, if the path currently has the given *prefix*. If
        it does not, a :class:`ValueError` exception is raised.
        """

        if not self.path.startswith(prefix) or (not prefix and self.path):
            raise ValueError("cannot rebase {!r} with prefix "
                             "{!r}".format(
                                 self.path,
                                 prefix))

        self.path = self.path[len(prefix):]

class RoutableMeta(type):
    """
    Metaclass which should be used for all classes whose instances
    which have routable members. Note that a routable class ``A.B``
    defined inside class ``A`` is not a routable member of an instance
    ``a`` of class ``A``.

    This metaclass defines an attribute
    ``__net_zombofant_teapot_routeinfo__``, whose contents are to be
    considered implementation details of teapot.

    Access to routing information should, as always, happen through
    :func:`getrouteinfo` and related.

    .. note::

       **Implementation detail:**
       The attribute contains an instance of :class:`Info`, which
       defines the routing of the class. The :class:`Info` instance
       most likely will contain references to methods, which are
       resolved using a ``__get__`` override.

    Example::

      @rebase("/")
      class Foo(metaclass=RoutableMeta):
          @route("", "index"):
          def index(self):
              \"\"\"called for /index and / requests\"\"\"

          @route("static"):
          @classmethod
          def index(cls):
              \"\"\"called for /static requests\"\"\"
    """

    def __new__(mcls, clsname, bases, namespace):
        # find all routables in the namespace. use a list, as we order
        # later
        instance_routenodes = list()
        class_routenodes = list()

        for name, obj in namespace.items():
            try:
                info = getrouteinfo(obj)
            except AttributeError as err:
                continue

            if (    not hasattr(info, "is_instance_leaf") or
                    not info.is_instance_leaf):
                class_routenodes.append(info)
            instance_routenodes.append(info)

        for base in bases:
            try:
                info = getrouteinfo(base)
            except AttributeError as err:
                continue

            class_routenodes.extend(info.routenodes)
            instance_routenodes.extend(info.instance_routenodes)

        namespace[routeinfo_attr] = teapot.routing.info.Class(
            class_routenodes,
            instance_routenodes)

        return type.__new__(mcls, clsname, bases, namespace)

def route(path, *paths, order=0, methods=None, make_constructor_routable=False):
    """
    Decorate a (static-, class- or instance-) method or function with routing
    information. Note that decorating a class using this decorator is not
    possible.

    The *order* determines the order in which routing information is visited
    upon looking up a route. The lower the value of *order*, the more precedence
    has a route.

    *methods* can be an iterable of requests methods which are supported by this
    routable. If *methods* is :data:`None`, no restrictions are implemented. The
    contents of the iterable are passed to :class:`method`.

    In classes, routes defined inside the class itself take precedence over
    routes defined in the base classes, independent of the order.

    Example::

        @route("/index")
        def index():
            \"\"\"do something fancy\"\"\"

    Usually, *route* will refuse to make a constructor routable, because it does
    not make lots of sense. If you know what you are doing and if you want to
    make a constructor routable, you can pass :data:`True` to
    *make_constructor_routable* and decorate the class.

    To make all routable methods of a class routable, see the
    :class:`RoutableMeta` metaclass.
    """

    paths = [path] + list(paths)
    paths = [path if hasattr(path, "select")
                  else teapot.routing.selectors.formatted_path(path)
             for path in paths]

    selectors = [teapot.routing.selectors.one_of(paths)]
    if methods is not None:
        selectors.append(teapot.routing.selectors.method(*methods))
    del paths

    def decorator(obj):
        if isroutable(obj):
            raise ValueError("{!r} already has a route".format(obj))

        kwargs = {"order": order}
        obj_selectors = selectors[:]

        if isinstance(obj, type) and not make_constructor_routable:
            # this is a class
            raise TypeError("I don’t want to make a constructor routable. See"
                            "the docs for details and a workaround.")

        if isinstance(obj, staticmethod):
            obj_selectors.append(
                teapot.routing.selectors.AnnotationProcessor(obj.__func__))
            info = teapot.routing.info.Leaf(
                obj_selectors, obj.__func__, **kwargs)
            setrouteinfo(obj.__func__, info)
        elif isinstance(obj, classmethod):
            obj_selectors.append(
                teapot.routing.selectors.AnnotationProcessor(obj.__func__))
            info = teapot.routing.info.LeafPrototype(
                obj_selectors,
                obj.__func__,
                False,
                **kwargs)
            setrouteinfo(obj.__func__, info)
        else:
            if not hasattr(obj, "__call__"):
                raise TypeError("{!r} is not routable (must be "
                                "callable or classmethod or "
                                "staticmethod)".format(obj))

            if not isinstance(obj, type):
                obj_selectors.append(
                    teapot.routing.selectors.AnnotationProcessor(obj))
            info = teapot.routing.info.LeafPrototype(
                obj_selectors,
                obj,
                True,
                **kwargs)

        setrouteinfo(obj, info)
        return obj

    return decorator

def traverse_to_root(routeinfo):
    while routeinfo:
        yield routeinfo
        routeinfo = routeinfo.parent

def get_routing_result(routecall):
    error = yield from routecall
    if error is not None:
        raise error

def map_unique(func, l):
    values = set()
    for item in l:
        value = func(item)
        if value not in values:
            values.add(value)
            yield value

def find_route(root, request):
    """
    Tries to find a route for the given *request* inside *root*, which
    must be an object with routing information.

    This first takes all candidates and then performs content negotiation,
    whereas result content type takes precedence over language selectors.
    """

    if not isroutable(root):
        raise TypeError("{!r} is not routable".format(root))

    localrequest = Context.from_request(request)
    error = None
    try:
        candidates = list(get_routing_result(
            getrouteinfo(root).route(localrequest)))
    except teapot.errors.ResponseError as err:
        error = err

    if not candidates:
        return False, error

    # content_types = [
    #     (candidate_type, candidate)
    #     for candidate in candidates
    #     for candidate_type in candidate.content_types
    # ]

    unique_content_types = list(map_unique(
        lambda x: x,
        (content_type
         for candidate in candidates
         for content_type in candidate.content_types)))

    content_type_candidates = request.accept_content.get_candidates(
        [teapot.accept.AcceptPreference(content_type, q=1.0)
         for content_type in unique_content_types
         if content_type is not None],
        match_wildcard=True)

    candidate = None

    if not content_type_candidates:
        if None in unique_content_types:
            best_match = None
        else:
            # no matches at all, we use our preferences.
            # FIXME: check for HTTP/1.1, otherwise we might have to reply with
            # 406.
            candidate = candidates[0]
    else:
        # if we ever do more than one lookup here, we might be better off with a
        # dictionary: type_map = dict(reversed(content_types))

        # FIXME: language selection
        best_match = content_type_candidates.pop()[1]

    if candidate is None:
        # we will find a match here
        for candidate in candidates:
            if best_match in candidate.content_types:
                break

    return True, candidate

def unroute(routable, *args, template_request=None, **kwargs):
    """
    Un-route the given *routable* and return a Request which would
    point to the given *routable*, inside the request tree to which the
    given *routable* belongs..
    """

    if template_request is None:
        request = Context(path="")
    else:
        request = Context.from_request(template_request)
    request.args = args
    request.kwargs = kwargs
    getrouteinfo(routable).unroute(request)
    return request

class Router:
    """
    A intermediate layer class which transforms the multiple supported response
    modes of the routables into a single defined response format. Routing takes
    place in the context of the root routable object *root*.

    The following result types are supported:

    * A routable may simply return a completely set up
      :class:`~teapot.response.Response` object which contains the respones to
      be delivered.
    * A routable may return an iterable (e. g. by being a generator), whose
      first element must be a :class:`~teapot.response.Response` object
      containing all required metadata to create the response headers. Iteration
      on the iterable does not continue until the response headers are sent.

      Now different things can happen:

      * either, the :attr:`~teapot.response.Response.body` attribute of the
        response is :data:`None`. In that case it is assumed that the remaining
        elements of the iterable are :class:`bytes` objects which form the
        response body.
      * or, the :attr:`~teapot.response.Response.body` attribute contains a
        bytes instance. It is returned as response body (yielded once).
      * or, the :attr:`~teapot.response.Response.body` attribute is another
        iterable, which is then iterated over and forwarded using
        ``yield from``.

    Before evaluating a response, the
    :meth:`~teapot.response.Response.negotiate_charset` method is called with
    the :attr:`~teapot.request.Request.accept_charset` preference list from
    the request.
    """

    def __init__(self, root):
        self._root = root

    def handle_not_found(self, request):
        """
        Handle a failure while routing the *request*.

        By default, this raises a ``404 Not Found`` error.
        """
        raise teapot.errors.make_response_error(
            404, "cannot find resource {!r}".format(request.path))

    def handle_charset_negotiation_failure(self, request, response):
        """
        Handle unability to encode the *response* in a manner which satisfies
        the client (see *request*).

        By default, this raises a ``400 Not Acceptable`` error.
        """
        raise teapot.errors.make_response_error(
            400, "cannot find accepted charset for response")

    def pre_route_hook(self, request):
        """
        This is called before any routing takes place. It must modify the
        request in-place, the return value is ignored.
        """

    def pre_headers_hook(self, request, response):
        """
        This is called before any headers are passed to the HTTP
        interface. *request* contains the original request from the client and
        *response* contains the response object returned by either the orignial
        destination of the request or an error handler.

        By default, this hook handles ``If-Modified-Since`` headers in the
        request and raises an ``304 Not Modified`` response, if the timestamp in
        that header does exactly match the timestamp in the response, if any.

        It is expected to either return the response or raise a
        :class:`~teapot.errors.ResponseError` exception.
        """
        if response.last_modified is not None and \
           request.if_modified_since is not None:
            if abs((response.last_modified -
                    request.if_modified_since).total_seconds()) < 1:
                raise teapot.errors.ResponseError(304, None, None)
        return response

    def wrap_result(self, request, result):
        """
        Performs converting the result in a uniform format for passing the
        response to the web server interface.

        *request* must be the request object. It is used for error handling and
        to negotiate the response charset. *result* must be the result obtained
        from calling the routable.

        Returns an iterable, which first yields a
        :class:`~teapot.routing.Response` object containing all metadata of the
        request and afterwards yields zero or more :class:`bytes` instances
        which form the body of the response.
        """
        if hasattr(result, "__iter__"):
            # data was a generator or pretends to be one. the only thing we need
            # to make sure is that it didn’t put it’s data into the Response
            # object
            result = iter(result)
            response = next(result)
            try:
                response.negotiate_charset(request.accept_charset)
            except UnicodeEncodeError as err:
                yield from self.wrap_result(
                    self.handle_charset_negotiation_failure(
                        self, request, response))
                return
        else:
            response = result
            try:
                response.negotiate_charset(request.accept_charset)
            except UnicodeEncodeError as err:
                yield from self.wrap_result(
                    self.handle_charset_negotiation_failure(
                        self, request, response))
                return

        try:
            response = self.pre_headers_hook(request, response)
        except:
            if hasattr(result, "close"):
                result.close()
            raise

        # function does not want to return any data by itself
        # we wrap the response headers and everything else into the generator
        # format
        yield response
        if response.body is None:
            if hasattr(result, "__iter__"):
                yield from result
        else:
            if hasattr(result, "close"):
                result.close()
            if (    hasattr(response.body, "__iter__") and
                    not isinstance(response.body, bytes)):
                yield from response.body
            else:
                yield response.body

    def route_request(self, request):
        """
        Routes a given *request* using the set up routing root and returns the
        response format described at :meth:`wrap_result`.
        """
        self.pre_route_hook(request)

        success, data = find_route(self._root, request)

        if not success:
            if data is None:
                return self.handle_not_found(request)
            raise data

        result = data()
        yield from self.wrap_result(request, result)
