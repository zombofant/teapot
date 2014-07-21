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

.. _teapot.routing.return_protocols.response_body:

Response body
-------------

Common for all protocols is the definition of a *response body*. A response body
may be represented by a *single object* or a *sequence*. If it is a
**single object**, it must be one of the following:

1. :data:`None`, to indicate that no response body is to be sent
2. a single :class:`bytes` instance or an object supporting the buffer protocol,
   which constitutes the whole response body
3. a single file-like, whose contents resemble the response body

If it is a **sequence**, the sequence must match one of the following patterns:

1. the empty sequence
2. one or more :class:`bytes` instances or other objects which support the
   buffer protocol (they can be mixed)
3. exactly one file-like, whose contents resemble the response body

The gateway implementation **may** interpret :data:`None` (or the empty
sequence, respectively) and a single empty :class:`bytes` instance (or a file
without any contents) differently.

return-by-generator
-------------------

The callable is a generator or returns an iterable. The first element of that
iterable is a :class:`~teapot.response.Response` instance with a :data:`None`
value in the :attr:`~teapot.response.Response.body` attribute. After that,
a :ref:`teapot.routing.return_protocols.response_body` sequence follows.

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
:attr:`~teapot.response.Response.body` attribute must be a
:ref:`teapot.routing.return_protocols.response_body` object.

If the iterator has a :attr:`close` attribute, it is called. The remainder of
the iterator is ignored.

return-by-value
---------------

The callable returns a single value. It is a :class:`~teapot.response.Response`
instance with a proper value in the :attr:`~teapot.response.Response.body`
attribute. After charset negotiation, the :attr:`~teapot.response.Response.body`
must be a :ref:`teapot.routing.return_protocols.response_body` object.

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

.. autoclass:: teapot.routing.selectors.webform

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

Unrouting
=========

Unrouting can be performed with the following two functions to a different level
of detail:

.. autofunction:: unroute

.. autofunction:: unroute_to_url

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
import teapot.mime
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

        self.method = request_method
        self.original_request = original_request
        self.path = path
        self._query_data = {} if query_data is None else query_data
        self._post_data = None
        self._cookie_data = None
        self._scheme = scheme

    def __deepcopy__(self, copydict):
        result = Context.from_request(self)
        result._args = copy.copy(self._args)
        result._kwargs = copy.copy(self._kwargs)
        result._query_data = copy.deepcopy(self.query_data)
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
    def query_data(self):
        return self._query_data

    @property
    def post_data(self):
        if self._post_data is None:
            if self.original_request is None:
                self._post_data = {}
            else:
                self._post_data = self.original_request.post_data
        return self._post_data

    @property
    def cookie_data(self):
        if self._cookie_data is None:
            if self.original_request is None:
                self._cookie_data = {}
            else:
                self._cookie_data = self.original_request.cookie_data
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

        class_routenodes.sort(key=lambda x: x.order,
                              reverse=False)
        instance_routenodes.sort(key=lambda x: x.order,
                                 reverse=False)

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

def make_routable(initial_selectors, order=0, make_constructor_routable=False):
    """
    Make a method or function routable. Except if developing extensions with
    custom decorators, you’ll usually not need this function. Use :func:`route`
    instead.

    Usually, *make_routable* will refuse to make a constructor routable, because
    it does not make lots of sense. If you know what you are doing and if you
    want to make a constructor routable, you can pass :data:`True` to
    *make_constructor_routable* and decorate the class.

    The given sequence of *initial_selectors* is added as selectors to the
    decorator destination.
    """

    def decorator(obj):
        if isroutable(obj):
            raise ValueError("{!r} already has a route".format(obj))

        kwargs = {"order": order}
        obj_selectors = initial_selectors[:]

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
                raise TypeError("{!r} cannot be made routable (must be callable"
                                "or classmethod or staticmethod)".format(obj))

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

def route(*paths, order=0, methods=None, make_constructor_routable=False):
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

    .. warning::
       Although it is currently possible, it is explicitly not supported to
       decorate an object more than once with :func:`route`. In the future, we
       will disable this for the sake of disambiguation.

       Applying multiple :func:`route` decorators is non-intuitive. Use
       :class:`~teapot.routing.selectors.rebase` or similar decorators instead.

    """

    paths = [path if hasattr(path, "select")
                  else teapot.routing.selectors.formatted_path(path)
             for path in paths]

    if paths:
        selectors = [teapot.routing.selectors.one_of(paths)]
    else:
        selectors = []
    if methods is not None:
        selectors.append(teapot.routing.selectors.method(*methods))
    del paths

    inherited_decorator = make_routable(
        selectors,
        order=order,
        make_constructor_routable=make_constructor_routable)

    def decorator(obj):
        if not isroutable(obj):
            return inherited_decorator(obj)

        info = getrouteinfo(obj)
        info.order = order
        info.selectors[:0] = selectors

        return obj

    return decorator

def traverse_to_root(routeinfo):
    while routeinfo:
        yield routeinfo
        routeinfo = routeinfo.parent

def get_routing_result(routecall):
    error = yield from routecall
    yield error

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

    This sets the :attr:`teapot.request.Request.accepted_content_type` attribute
    on the request.
    """

    if not isinstance(root, teapot.routing.info.Info):
        if not isroutable(root):
            raise TypeError("{!r} is not routable".format(root))
        info = getrouteinfo(root)
    else:
        info = root

    localrequest = Context.from_request(request)
    error = None
    candidates = list(get_routing_result(info.route(localrequest)))
    error = candidates.pop()

    if not candidates:
        return False, error

    unique_content_types = list(map_unique(
        lambda x: x,
        (content_type
         for candidate in candidates
         for content_type in candidate.content_types)))

    content_type_candidates = request.accept_content.get_candidates(
        [
            teapot.accept.MIMEPreference(*content_type, q=1.0)
            for content_type in reversed(unique_content_types)
            if content_type is not None
        ])

    routable_candidate = None
    try:
        # FIXME: language selection
        q, pref = content_type_candidates.pop()
        if q <= 0:
            best_match = None
        else:
            best_match = pref.values
    except IndexError:
        if None in unique_content_types:
            best_match = None
        else:
            # no matches at all, we use our preferences.
            # FIXME: check for HTTP/1.1, otherwise we might have to reply with
            # 406.
            routable_candidate = candidates[0]

    if routable_candidate is None:
        # search for the routable satisfying the given content type
        for candidate in candidates:
            if best_match in candidate.content_types:
                routable_candidate = candidate
                break

    # FIXME: deal with parameters and such
    if best_match is not None:
        request.accepted_content_type = \
            teapot.mime.Type(*best_match)
    else:
        request.accepted_content_type = None

    return True, candidate

def unroute(routable, *args,
            _template_request=None,
            _original_request=None,
            **kwargs):
    """
    Un-route the given *routable* and return a Request which would
    point to the given *routable*, inside the request tree to which the
    given *routable* belongs..
    """

    if _template_request is None:
        request = Context(path="")
    else:
        request = Context.from_request(_template_request)
    if _original_request is not None:
        request.original_request = _original_request
    request.args = args
    request.kwargs = kwargs
    getrouteinfo(routable).unroute(request)
    return request

def unroute_to_url(original_request, routable,
                   *args, **kwargs):
    """
    Perform unrouting and return a relative (that is, without host, port and
    scheme, but including the full path) URL which addresses the given
    *routable* with remaining arguments.
    """
    route_context = teapot.routing.unroute(
        routable,
        *args,
        _original_request=original_request,
        **kwargs)
    request = copy.copy(original_request)
    request.path = route_context.path
    request.post_data.clear()
    request.post_data.update(route_context.post_data)
    request.query_data.clear()
    request.query_data.update(route_context.query_data)
    try:
        return request.reconstruct_url(relative=True)
    except ValueError as err:
        raise ValueError("Failed to unroute routable: {}".format(routable)) from err

class Router:
    """
    A intermediate layer class which transforms the multiple supported response
    modes of the routables into a single defined response format. Routing takes
    place in the context of the root routable object *root*.

    The :ref:`teapot.routing.return_protocols` are supported.

    Before evaluating a response, the
    :meth:`~teapot.response.Response.negotiate_charset` method is called with
    the :attr:`~teapot.request.Request.accept_charset` preference list from
    the request.
    """

    def __init__(self, root=None):
        if root is None:
            self._owns_root = True
            self._root = teapot.routing.info.CustomGroup([])
        else:
            self._owns_root = False
            self._root = getrouteinfo(root)

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

    def post_response_cleanup(self, request):
        """
        After the result has been delivered to the web gateway, this function is
        called. It is even called when an exception in any stage after the
        execution of :meth:`pre_route_hook` happened.
        """

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
            yield response.body

    def route_request(self, request):
        """
        Routes a given *request* using the set up routing root and returns the
        response format described at :meth:`wrap_result`.
        """
        self.pre_route_hook(request)

        try:
            success, data = find_route(self._root, request)

            if not success:
                if data is None:
                    return self.handle_not_found(request)
                raise data

            request.current_routable = data.routable
            result = data()
            yield from self.wrap_result(request, result)
        finally:
            self.post_response_cleanup(request)

    def route(self, *args, **kwargs):
        """
        This takes the same arguments as :func:`~teapot.routing.route`, but
        immediately mounts the callable decorated with the returned decorator in
        the routing tree.

        This throws :class:`ValueError`, if the *root* argument to the
        constructor of :class:`Router` has not been :data:`None`.
        """
        if not self._owns_root:
            raise ValueError("Cannot use @Router.route with routers which "
                             "have been created with non-empty root.")

        def decorator(obj):
            obj = route(*args, **kwargs)(obj)
            self._root.add(getrouteinfo(obj))
            return obj

        return decorator
