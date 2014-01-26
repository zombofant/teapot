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

.. autoclass:: rebase

.. autoclass:: queryarg

.. autoclass:: postarg

.. autoclass:: cookie

.. autoclass:: formatted_path

.. autoclass:: one_of


Utilities to get information from routables
===========================================

These utilities can be used to introspect the routing information of a given
object.

.. autofunction:: isroutable

.. autofunction:: getrouteinfo

.. autofunction:: setrouteinfo

.. autofunction:: requirerouteinfo

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
:ref:`teapot.routing.routable_decorators` section. The ``Context`` class is the
data class on which the selectors operate.

.. autoclass:: Selector
   :members: select, unselect, __call__

.. autoclass:: ArgumentSelector

.. autoclass:: Context
   :members:

Internal API
============

This API is subject to unnotified change. Not only the names, attributes and
methods can change, but also the usage. Do not rely on anything here, even if it
is tested against in a testsuite.

.. autoclass:: Info
   :members:

.. autoclass:: Group
   :members:

.. autoclass:: Object
   :members:

.. autoclass:: Class
   :members:

.. autoclass:: Leaf
   :members:

.. autoclass:: MethodLeaf
   :members:

.. autoclass:: LeafPrototype
   :members:

"""
import abc
import copy
import functools
import string
import re

import teapot.errors
import teapot.request

import logging

logger = logging.getLogger(__name__)

routeinfo_attr = "__net_zombofant_teapot_routeinfo__"

__all__ = [
    "isroutable",
    "getrouteinfo",
    "route",
    "rebase",
    "queryarg",
    "postarg",
    "cookie",
    "RoutableMeta"]

def isroutable(obj):
    """
    Test whether the given *obj* has teapot routing information.
    """
    global routeinfo_attr
    return hasattr(obj, routeinfo_attr)

def getrouteinfo(obj):
    """
    Return the routing information of *obj*. If *obj* has no routing
    information, :class:`AttributeError` is thrown (by Python itself).

    Note that this function also takes care of properly specializing
    the prototypes for methods, so it is always preferred over a
    simple attribute access.
    """
    global routeinfo_attr
    routeinfo = getattr(obj, routeinfo_attr)
    if hasattr(routeinfo, "get_for_external_use"):
        routeinfo = routeinfo.get_for_external_use(obj)
    return routeinfo

def setrouteinfo(obj, value):
    """
    Set the routing information of *obj*.
    """
    global routeinfo_attr
    return setattr(obj, routeinfo_attr, value)

def requirerouteinfo(obj):
    """
    Return the routing information of *obj*. If *obj* does not have routing
    information, a :class:`ValueError` with an appropriate error message is
    thrown.

    Internally, :meth:`getrouteinfo` is used, thus the same features apply.
    """
    if not isroutable(obj):
        raise ValueError("{!r} is not routable".format(obj))

    return getrouteinfo(obj)

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
            cookie_data=copy.copy(base.cookie_data),
            request_method=base.method,
            scheme=base.scheme)

    def __init__(self, *,
                 accept_content=None,
                 accept_language=None,
                 request_method=teapot.request.Method.GET,
                 original_request=None,
                 path="/",
                 query_data=None,
                 post_data=None,
                 cookie_data=None,
                 scheme="http"):
        super().__init__()
        self._args = []
        self._kwargs = {}

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
        self._post_data = {} if post_data is None else post_data
        self._cookie_data = {} if cookie_data is None else cookie_data
        self._scheme = scheme

    def __deepcopy__(self, copydict):
        result = Context.from_request(self)
        result._args = copy.copy(self._args)
        result._kwargs = copy.copy(self._kwargs)
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

@functools.total_ordering
class Info(metaclass=abc.ABCMeta):
    """
    Baseclass to implement routing information. *order* defines in
    which order the routers are evaluated.
    """

    def __init__(self, selectors, order=0, **kwargs):
        super().__init__(**kwargs)
        self.order = order
        self.selectors = selectors
        self.parent = None

    @abc.abstractmethod
    def _do_route(self, localrequest):
        """
        Subclasses must implement this. This method has to finalize or
        forward the routing to other :class:`Info` instances.

        The request object passed is the modified and rebased request.
        """

    def route(self, request):
        """
        Try to route the given *request*. The result is a tuple of two
        elements. The first element is a boolean indicating whether
        the routing was successful.

        If it is :data:`True`, the second element is a callable which
        can be called without arguments to handle the request.

        If it is :data:`False`, the second element is either
        :data:`None`, if no match could be found or an
        :class:`ResponseError` instance, if the router hit a node
        which wants to return an HTTP error.
        """
        localrequest = copy.deepcopy(request)
        try:
            if not all(selector.select(localrequest)
                       for selector in self.selectors):
                # not all selectors did match
                return False, None
        except teapot.errors.ResponseError as err:
            return False, err
        return self._do_route(localrequest)

    def unroute(self, request):
        """
        Reverse the route from this node up to the root of the routing
        tree this node belongs to. Unselect anything which would be
        selected on the given *request*.
        """
        for selector in reversed(self.selectors):
            selector.unselect(request)
        if self.parent:
            self.parent.unroute(request)

    def __lt__(self, other):
        return self.order < other.order

class Group(Info):
    """
    This is a generic group of *routenodes*. Upon routing, all
    routing nodes will be evaluated in the given order.
    """

    def __init__(self, selectors, routenodes, **kwargs):
        super().__init__(selectors)
        self.routenodes = routenodes
        for node in routenodes:
            node.parent = self

    def _do_route(self, localrequest):
        first_error = None
        try:
            logger.debug("entering routing group %r", self)
            for node in self.routenodes:
                success, data = node.route(localrequest)
                if success:
                    return success, data
                elif data:
                    first_error = first_error or data

            return False, first_error
        finally:
            logger.debug("leaving routing group %r", self)

class Object(Group):
    """
    This class provides the routing information for an object. It is
    an aggregate of other routing information providers, usually for
    the methods of the object. It can be created from a :class:`Class`
    routing information by supplying the objects instance.
    """

    def __init__(self, routenodes, selectors=[], **kwargs):
        super().__init__(selectors, routenodes, **kwargs)

class Class(Group):
    """
    This class provides the routing information for a class. It is
    used for two purposes.

    On the one hand, it provides the actual routing information of the
    class. It is possible to route a class, by decorating classmethods
    and staticmethods appropriately.

    On the other hand, it is used to create the routing information
    for the instance upon instanciation of the class.
    """

    def __init__(self,
                 cls_routenodes,
                 instance_routenodes,
                 selectors=None,
                 **kwargs):
        super().__init__([] if selectors is None else selectors,
                         cls_routenodes, **kwargs)
        self.instance_routenodes = instance_routenodes
        self._class_routenodes_initialized = False

    def _init_class_routenode(self, cls, node):
        if hasattr(node, "get"):
            return node.get(None, cls)
        return node

    def _init_class_routenodes(self, cls):
        if self._class_routenodes_initialized:
            return

        self.routenodes = list(map(
            functools.partial(self._init_class_routenode, cls),
            self.routenodes))
        self._class_routenodes_initialized = True

    def _init_instance_routenode(self, instance, cls, node):
        if hasattr(node, "get"):
            return node.get(instance, cls)
        else:
            return copy.copy(node)

    def _get_for_instance(self, instance, cls):
        nodes = list(map(
            functools.partial(self._init_instance_routenode,
                              instance, cls),
            self.instance_routenodes))

        return Object(nodes,
                      selectors=self.selectors,
                      order=self.order)

    def __get__(self, instance, cls):
        try:
            if instance is None:
                self._init_class_routenodes(cls)
                return self
            obj = self._get_for_instance(instance, cls)
            setrouteinfo(instance, obj)
            return obj
        except BaseException as err:
            print(err)

class Leaf(Info):
    """
    Implements a routing tree leaf. This is a node which can actually
    handle a route request, such as a method on an object.
    """

    def __init__(self, selectors, callable, **kwargs):
        super().__init__(selectors, **kwargs)
        self.callable = callable

    def _do_route(self, localrequest):
        return True, functools.partial(
            self.callable,
            *localrequest.args,
            **localrequest.kwargs)

class MethodLeaf(Leaf):
    """
    Implements a routing tree leaf of a (class- or instance-) method.
    """

    def __init__(self, selectors, callable, obj, **kwargs):
        super().__init__(
            selectors,
            functools.partial(callable, obj),
            **kwargs)

class LeafPrototype(Leaf):
    """
    Leaf prototypes are used for methods and free functions. For free
    functions, leaf prototypes behave exactly like normal leaves. For
    methods however, the owning :class:`Group` (usually a
    :class:`Class`), calls the :meth:`get` method from its own
    :meth:`Class.__get__` to fully bind the callable passed to the
    leaf prototype.
    """

    def __init__(self,
                 selectors,
                 base_callable,
                 is_instance_leaf,
                 **kwargs):
        super().__init__(selectors, base_callable, **kwargs)
        self._kwargs = kwargs
        self.is_instance_leaf = is_instance_leaf

    def get_for_external_use(self, instance):
        # here, instance is the function(!) object
        if not hasattr(instance, "__self__"):
            return self
        if isinstance(instance.__self__, type):
            node = self.get(None, instance.__self__)
            node.parent = getrouteinfo(instance.__self__)
        else:
            node = self.get(instance.__self__,
                            type(instance.__self__))
            node.parent = getrouteinfo(instance.__self__)
        return node

    def get(self, instance, cls):
        if self.is_instance_leaf:
            if instance is None:
                raise ValueError("instance must not be None for "
                                 "instance leaf prototypes.")
            return MethodLeaf(self.selectors,
                              self.callable,
                              instance,
                              **self._kwargs)
        return MethodLeaf(self.selectors,
                          self.callable,
                          cls,
                          **self._kwargs)

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

        namespace[routeinfo_attr] = Class(
            class_routenodes,
            instance_routenodes)

        return type.__new__(mcls, clsname, bases, namespace)


class Selector(metaclass=abc.ABCMeta):
    """
    Selectors are used throughout the routing tree to determine whether a path
    is legit for a given request.

    Selectors commonly appear in the form of decorators, which is why a
    :meth:`__call__` method is supplied. For a list of selectors see
    :ref:`teapot.routing.routable_decorators`.

    A selector class must implement two methods.
    """

    @abc.abstractmethod
    def select(self, request):
        """
        This method is called to route an incoming *request* to a
        :class:`Leaf`.

        The selector shall return :data:`True` if it matches on the
        given request object. It shall return :data:`False` if it does
        not match on the given request object. It shall raise an
        :class:`ResponseError` exception if it matches, but if a
        problem would occur if that path would be taken.

        The exception will be caught by the routing mechanism and
        propagated upwards. If another path can be found which matches
        and does not raise an error, that path is taken. Otherwise,
        the first path which raised an exception wins and its
        exception will be re-thrown.

        `select` *may* trim any parts of the request it uses to
        select. A path selector for example would remove the prefix it
        has successfully selected on from the path in the request.
        """

    @abc.abstractmethod
    def unselect(self, request):
        """
        This method is called to un-route from a given :class:`Leaf`.
        Un-routing means to construct a :class:`Context` object which
        would lead to the given :class:`Leaf` (and preferably only to
        that leaf).

        The `unselect` method must modify the *request* in such a way
        that after the modification, a call to :meth:`select` on the
        given *request* would succeed with a :data:`True`
        result. Ideally, after such an hypothetical call, the
        *request* object would have the same contents as before the
        call to `unselect`.

        If unselection fails due to missing arguments or arguments of the wrong
        type, :class:`ValueError` should be raised. If unselection is impossible
        in general for the selector, call ``super().unselect(request)``, which
        will raise an appropriate, implementation defined error.
        """

        raise NotImplementedError(
            "unselection is not possible with {!r}".format(self))

    def __call__(self, obj):
        """
        Append this selector to the selectors in the routing information of
        *obj*.

        Subclasses may override this to insert in a different position in the
        selector array to take precedence over other selectors.
        """
        info = requirerouteinfo(obj)
        info.selectors.append(self)
        return obj

class ArgumentSelector(Selector):
    """
    This abstract :class:`Selector` is the base class for request argument
    selectors that pick a specified argument from the set of all available
    arguments. Popular examples of such selectors are the
    :class:`queryarg`, the :class:`postarg` or the :class:`cookie`
    selector respectively. It behaves as follows:

    First, *argname* is looked up in the request data. The list of arguments
    passed with that key is extracted and we call that list *args*. The result
    which will be passed to the final routable will be called *result*.

    * if *argtype* is a callable, the first argument from *args* is removed and
      the *argtype* is called with that argument as the only argument. The
      result of callable is stored in *result*. If *args* is empty, the selector
      does not apply.
    * if *argtype* is a list containing exactly one callable, the callable is
      evaluated for all elements of *args* and the resulting list is stored in
      *result*. *args* is cleared.
    * if *argtype* is a tuple of length *N* containing zero or more callables,
      the first *N* elements from *args* are removed. On each of these elements,
      the corresponding callable is applied and the resulting tuple is stored in
      *result*. If *args* contains less than *N* elements, the selector does not
      apply.

    All other cases are invalid and raise a TypeError upon decoration.

    If *unpack_sequence* is true, *argtype* must be a sequence and *destarg*
    must be :data:`None` (if any of these conditions is not met, a ValueError is
    raised). In that case, the *result* sequence gets unpacked and appended to
    the argument list of the final routable.

    If the callables which are converting the strings to the desired type
    encounter any errors, they *must* throw :class:`ValueError`. All other
    exceptions propagate upwards unhandled.

    Subclasses of this abstract base class have to implement the
    :meth:`get_data_dict` method in order to supply the request parameter data.
    """

    @classmethod
    def procargs_list(cls, itemtype, args):
        result = list(args)
        args.clear()
        try:
            return list(map(itemtype, result))
        except ValueError as err:
            # revert and reraise
            args[:] = result
            raise

    @classmethod
    def procargs_tuple(cls, itemtypes, args):
        if len(args) < len(itemtypes):
            raise ValueError("not enough arguments")

        sliced_args = args[:len(itemtypes)]
        args[:] = args[len(itemtypes):]

        try:
            return tuple(
                itemtype(item)
                for item, itemtype
                in zip(sliced_args, itemtypes))
        except ValueError as err:
            # revert and reraise
            args[:0] = sliced_args
            raise

    @classmethod
    def procargs_single(cls, itemtype, args):
        if len(args) < 1:
            raise ValueError("not enough arguments")

        arg = args.pop(0)
        try:
            return itemtype(arg)
        except ValueError as err:
            # revert and reraise
            args.insert(0, arg)
            raise

    def __init__(self, argname, destarg,
                 argtype=str,
                 unpack_sequence=False, **kwargs):
        super().__init__(**kwargs)
        self._argname = argname
        self._destarg = destarg
        self._argtype = argtype
        self._is_sequence = False
        self._sequence_length = None
        self._unpack_sequence = unpack_sequence
        if unpack_sequence and destarg is not None:
            raise ValueError("unpacking argument lists and named arguments do"
                             " not mix.")

        procargs = None
        if hasattr(argtype, "__call__"):
            procargs = functools.partial(
                self.procargs_single,
                argtype)
            if self._unpack_sequence:
                raise ValueError("cannot unpack single argument")
        elif hasattr(argtype, "__len__"):
            self._is_sequence = True
            if isinstance(argtype, list):
                if len(argtype) == 1:
                    procargs = functools.partial(
                        self.procargs_list,
                        argtype[0])
            elif isinstance(argtype, tuple):
                self._sequence_length = len(argtype)
                procargs = functools.partial(
                    self.procargs_tuple,
                    argtype)

        if procargs is None:
            raise TypeError("argtype must be either a callable, or a list "
                            "containing exactly one callable or a tuple of"
                            " one or more callables")

        self._procargs = procargs

    @abc.abstractmethod
    def get_data_dict(self, request):
        """
        :class:`ArgumentSelector` subclasses must implement this method
        to supply the data dictionary.
        """
        raise NotImplementedError("no data can be get in {!r}".format(self))

    def select(self, request):
        try:
            args = [self._procargs(
                self.get_data_dict(request).get(self._argname, [])
                )]
        except ValueError as err:
            # processing the given request arguments failed, thus the selector
            # does not match
            # TODO: allow different failure modes
            return False

        if self._destarg is None:
            if self._unpack_sequence:
                args = args[0]
            request.args.extend(args)
        else:
            request.kwargs[self._destarg] = args[0]

        return True

    def unselect(self, request):
        logger.debug("queryarg: is_sequence=%s, unpack_sequence=%s,"
                     " sequence_length=%s",
                     self._is_sequence,
                     self._unpack_sequence,
                     self._sequence_length)
        logger.debug("queryarg: request.args=%r, request.kwargs=%r",
                     request.args,
                     request.kwargs)

        if self._unpack_sequence:
            if self._sequence_length is None:
                args = request.args[:]
                request.args.clear()
            else:
                args = request.args[:self._sequence_length]
                if len(args) != self._sequence_length:
                    raise ValueError("not enough arguments")
                request.args[:] = request.args[self._sequence_length:]
        else:
            try:
                if self._destarg is None:
                    args = request.args.pop()
                else:
                    args = request.kwargs[self._destarg]
            except KeyError as err:
                raise ValueError("missing argument: {}".format(str(err))) \
                    from None
            except IndexError as err:
                raise ValueError("not enough arguments") from None

        logger.debug("queryarg: args=%r", args)

        if not self._is_sequence:
            args = [args]

        args = list(map(str, args))
        self.get_data_dict(request).setdefault(self._argname, [])[:0] = args

class AnnotationProcessor(Selector):
    def inject_request(request, argname):
        request.kwargs[argname] = request.original_request

    annotation_processors = {
        teapot.request.Request: inject_request
    }

    def __init__(self, callable, **kwargs):
        super().__init__(**kwargs)
        # if callable is an object with __call__ method, we have to traverse
        # until we find the actual function with its annotations
        while not hasattr(callable, "__annotations__"):
            if hasattr(callable, "__func__"):
                callable = callable.__func__
            else:
                callable = callable.__call__

        annotations = callable.__annotations__
        processors = []
        for arg, annotation in annotations.items():
            processors.append(
                (arg, self.annotation_processors[annotation]))

        self.processors = processors

    def select(self, request):
        for arg, processor in self.processors:
            processor(request, arg)

        return True

    def unselect(self, request):
        return True

class rebase(Selector):
    """
    A path selector selects a static portion of the current request
    path. If the current path does not begin with the given *prefix*,
    the selection fails.
    """

    def __init__(self, prefix, **kwargs):
        super().__init__(**kwargs)
        self._prefix = prefix

    def select(self, request):
        logging.debug("rebase: request.path=%r, prefix=%r",
                      request.path, self._prefix)
        try:
            request.rebase(self._prefix)
        except ValueError:
            logging.debug("rebase: mismatch")
            return False
        logging.debug("rebase: match")
        return True

    def unselect(self, request):
        request.path = self._prefix + request.path

    def __call__(self, obj):
        info = requirerouteinfo(obj)
        info.selectors.insert(0, self)
        return obj

class formatted_path(Selector):
    """
    Select a portion of the current request path and extract
    information from it using
    `python formatter syntax
    <http://docs.python.org/3/library/string.html#format-string-syntax>`_.
    The given *format_string* defines the format of the path part. It
    is used to construct a parser for the path which will run against
    the current request path. If it does not match, the selector
    fails.

    Anything retrieved from the parsed data, which are numbered fields
    and named fields in the format string, is appended to the current
    contexts arguments (see :attr:`Context.args`).

    Upon unparsing, the arguments in the context are used to format
    the given *format_string*, which is then prepended to the current
    request path.

    .. warning::

       Only a subset of the python formatter syntax is
       supported.

       **Not supported features are:**

       * Alignment (and, thus, filling, except zero-padding for numbers)
       * Conversion modifiers
       * Not all types, see below

    **Supported types:**

    * Integers (``d``, ``x``, ``X``, ``b``)
    * Floats (``f``)
    * Strings (``s``)

    .. note::

       When using a string type, be aware that it will match
       everything until the end of the request path, except if you
       specify a width. In that case, it will match exactly that
       amount of characters, including slashes.

       If no width is set, the string can be used as a catch all,
       including slashes.

    Parsing always fails gracefully. If a number is expected and a
    string is found, the format simply does not match and a negative
    result is returned.

    If *strict* is set to :data:`True`, width, precision and
    zero-padding are enforced when parsing. Normally, any
    width/precision is accepted while parsing (except for strings). If
    *strict* is set, only those strings which would be the output of a
    format call with the same argument are accepted. For example,
    ``{:02d}`` would match against ``22`` and ``01``, but not against
    `` 1`` or ``1``.

    .. note::

       Strict mode parsing for numbers becomes expensive, due to the
       nature of the involved regular expressions, if zero-padding is
       not used (i.e. the values are padded with spaces).

    If *final* is false, the selector will even match if the parsing cannot
    consume the whole (remaining) request path.
    """

    def __init__(self, format_string, strict=False, final=True, **kwargs):
        super().__init__(**kwargs)
        self._strict = strict
        self._final = final
        self._format_string = format_string
        self._presentation_parsers = {
            "d": (
                functools.partial(self._int_regex, 10),
                functools.partial(self._int_converter, 10)),
            "x": (
                functools.partial(self._int_regex, 16),
                functools.partial(self._int_converter, 16)),
            "X": (
                functools.partial(self._int_regex, 16, upper_case=True),
                functools.partial(self._int_converter, 16)),
            "b": (
                functools.partial(self._int_regex, 2),
                functools.partial(self._int_converter, 2)),
            "s": (self._str_regex, self._str_converter),
            "f": (self._float_regex, self._float_converter)
        }
        self._parsed = list(self._parse_more(
            string.Formatter().parse(format_string)))

        self._numbered_count = 0
        self._keywords = set()
        for _, field, _ in self._parsed:
            if field is None:
                continue
            if not field:
                self._numbered_count += 1
            else:
                assert field not in self._keywords
                self._keywords.add(field)

    def _float_converter(self, match):
        return float(match.group(0))

    def _float_regex(self, width, precision, zero_pad, sign_pad,
                     alternate_form):
        if alternate_form:
            raise ValueError("alternate form is not supported for"
                             " floats")

        digit = r"\d"
        re_base = digit
        if sign_pad is None:
            sign_pad = "-"

        if width is not None and self._strict:
            if width == 0:
                re_base = ""
            else:
                if zero_pad:
                    re_base += r"{{{:d},}}".format(width)
                else:
                    re_base = self._get_strict_digit_padder(
                        re_base, r" ", width)
        else:
            re_base += r"+"

        if re_base:
            re_base = "(" + re_base + ".?|.)"

        if precision is not None and self._strict:
            if precision > 0:
                if not re_base:
                    re_base = "."
                re_base += digit + r"{{{:d}}}".format(precision)
        else:
            if not re_base:
                re_base = "."
            re_base += digit + r"*"

        if not re_base:
            raise ValueError("float with width={} and precision={} not"
                             " supported (in strict "
                             "mode)".format(width,
                                            precision))
        if self._strict:
            if sign_pad == "+":
                re_base = "[+-]" + re_base
            elif sign_pad == "-":
                re_base = "-?" + re_base
            elif sign_pad == " ":
                re_base = "[ -]" + re_base
            else:
                raise ValueError("unknown sign mode: {!r}".format(sign_pad))
        else:
            re_base = "[+-]?" + re_base

        return re_base

    def _get_strict_digit_padder(self, one_digit, one_space, width):
        # logger.warning(
        #     "using width and strict mode in formatter "
        #     "with large widths and without zero "
        #     "padding is highly inefficient!")
        re_base = "|".join(
            one_space+"{"+str(i)+"}"+one_digit+"{"+str(width-i)+",}"
            for i in range(1, width))
        re_base = ("("+one_space+"{"+str(width)+"}|"+
                   ((re_base+"|") if re_base else "")+
                   one_digit+"{"+str(width)+",})")
        return re_base

    def _int_converter(self, base, match):
        return int(match.group(0).strip(), base)

    def _int_regex(self,
                   base,
                   width,
                   precision,
                   zero_pad,
                   sign_pad,
                   alternate_form,
                   upper_case=False):
        if precision is not None:
            raise ValueError("precision is not supported for"
                             "integers")

        if sign_pad is None:
            sign_pad = "-"
        try:
            re_base = {
                10: r"\d",
                2: r"[01]",
                16: ((r"[0-9A-F]" if upper_case else r"[0-9a-f]")
                     if self._strict else r"[0-9a-fA-F]")
            }[base]
        except KeyError:
            raise ValueError("unsupported integer base: {:d}".format(base))

        if width is not None and self._strict:
            if zero_pad:
                re_base += r"{{{:d},}}".format(width)
            else:
                re_base = self._get_strict_digit_padder(
                    re_base, r" ", width)

        else:
            re_base += r"+"

        if alternate_form:
            re_base = {
                10: r"",
                2: r"0b",
                16: r"0x"
            }[base] + re_base

        if self._strict:
            if sign_pad == "+":
                re_base = "[+-]" + re_base
            elif sign_pad == "-":
                re_base = "-?" + re_base
            elif sign_pad == " ":
                re_base = "[ -]" + re_base
            else:
                raise ValueError("unknown sign mode: {!r}".format(sign_pad))
        else:
            re_base = "[+-]?" + re_base

        return re_base

    def _parse_width_and_alignment(self, spec):
        width = None
        zero_pad = False
        alternate_form = False
        sign_pad = None
        if not spec:
            return width, zero_pad, sign_pad, alternate_form

        # numbers can only occur at the end or as the first character,
        # if fill is set to a number
        numbers = "".join(filter(str.isdigit, spec))
        if spec[0].isdigit() and len(numbers) != len(spec):
            raise ValueError("alignment is not supported")
        remainder = spec[:-len(numbers)]
        if remainder.endswith("#"):
            alternate_form = True
            remainder = remainder[:-1]

        if remainder:
            if remainder[0] in [">", "<", "=", "^"]:
                raise ValueError("alignment is not supported")

            if remainder[0] in ["+", "-", " "]:
                sign_pad = remainder[0]
            else:
                raise ValueError("{!r} found where sign spec was "
                                 "expected".format(remainder))

            remainder = remainder[1:]
            if remainder:
                raise ValueError("no idea what that is supposed to "
                                 "be: {!r}".format(remainder))

        if numbers:
            if numbers.startswith("0"):
                zero_pad = True
                numbers = numbers[1:]

            if numbers:
                width = int(numbers)

        return width, zero_pad, sign_pad, alternate_form

    def _parse_more(self, parsed_format):
        for literal, field, format_spec, conversion in parsed_format:
            if conversion is not None:
                raise ValueError("conversion specifiers not "
                                 "supported")
            if field is None:
                yield literal, None, (None, None)
                continue

            spec = format_spec[:-1]
            presentation = format_spec[-1:]
            try:
                parser = self._presentation_parsers[presentation]
            except KeyError:
                raise ValueError(
                    "parsing of {!r} not supported: no "
                    "parser for presentation "
                    "{!r}".format(
                        format_spec,
                        presentation)) from None

            try:
                spec, precision = spec.rsplit(".", 1)
            except ValueError:
                # no precision
                precision = None
            else:
                precision = int(precision)

            if spec.endswith(","):
                raise ValueError(
                    "parsing of {!r} not supported: "
                    "no support for thousand seperators".format(
                        format_spec))

            try:
                width, zero_pad, sign_pad, alternate_form = \
                    self._parse_width_and_alignment(spec)
            except ValueError as err:
                raise ValueError(
                    "parsing of {!r} not supported: "
                    "{!s}".format(format_spec, err))

            regex_generator, converter = parser
            try:
                regex = regex_generator(
                    width, precision, zero_pad,
                    sign_pad, alternate_form)
            except ValueError as err:
                raise ValueError(
                    "parsing of {!r} not supported: "
                    "{!s}".format(format_spec, err))

            regex = re.compile(r"^" + regex)

            yield literal, field, (regex, converter)

    def _str_regex(self,
                   width,
                   precision,
                   zero_pad,
                   sign_pad,
                   alternate_form):
        if alternate_form:
            raise ValueError("alternate form (#) not supported for "
                             "strings")
        if precision is not None:
            raise ValueError("precision is not supported for strings")
        if sign_pad is not None:
            raise ValueError("sign is not supported for strings")
        if zero_pad:
            raise ValueError("zero padding is not supported for "
                             "strings")

        if width is not None:
            return r".{"+str(width)+"}"
        else:
            return r".*"

    def _str_converter(self, match):
        return match.group(0)

    def parse(self, s):
        if not self._parsed:
            if s:
                return False
            return [], {}, ""

        numbered = []
        keywords = {}
        for literal, field, (regex, converter) in self._parsed:
            if literal is not None:
                if not s.startswith(literal):
                    return False
                s = s[len(literal):]
            if field is None:
                continue

            match = regex.match(s)
            if not match:
                return False

            value = converter(match)
            if not field:
                numbered.append(value)
            else:
                keywords[field] = value

            s = s[len(match.group(0)):]

        return numbered, keywords, s

    def select(self, request):
        logging.debug("formatted_path: request.path=%r, format_string=%r",
                      request.path, self._format_string)
        result = self.parse(request.path)
        if not result:
            logging.debug("formatted_path: mismatch")
            return False

        numbered, keywords, remainder = result

        if self._final and remainder:
            logging.debug("formatted_path: mismatch (nonfinal)")
            return False

        request.args.extend(numbered)
        request.kwargs.update(keywords)

        logging.debug("formatted_path: match")
        return True

    def unselect(self, request):
        if self._numbered_count:
            args = request.args[-self._numbered_count:]
            request.args = request.args[:-self._numbered_count]
        else:
            args = []

        kwargs = {}
        for keyword in self._keywords:
            kwargs[keyword] = request.kwargs.pop(keyword)

        request.path = self._format_string.format(*args, **kwargs) + request.path

class one_of(Selector):
    """
    Take a collection of selectors. If any of the selectors match, this selector
    matches.

    For unrouting, the first selector in the collection (which is, internally,
    converted to a list), will be chosen to perform the unrouting.
    """

    def __init__(self, subselectors, **kwargs):
        super().__init__(**kwargs)
        self._subselectors = list(subselectors)

    def select(self, request):
        return any(selector.select(request)
                   for selector in self._subselectors)

    def unselect(self, request):
        # the choice is arbitrary
        if self._subselectors:
            self._subselectors[0].unselect(request)

class queryarg(ArgumentSelector):
    """
    This :class:`ArgumentSelector` implementation looks up an HTTP
    query argument.

    Example::

        @teapot.routing.queryarg("argname", "my_arg", str)
        @teapot.route("/query")
        def handle_query(self, my_arg):
            \"\"\"do something\"\"\"
    """

    def get_data_dict(self, request):
        return request.query_data

class postarg(ArgumentSelector):
    """
    This :class:`ArgumentSelector` implementation looks up an HTTP
    POST argument.

    File uploads will be passed as :data:`file-like` objects. You
    should not call read() on them, since this will load the whole
    file into memory.

    Example::

        @teapot.routing.postarg("argname", "my_arg")
        @teapot.route("/post")
        def handle_post(self, my_arg):
            \"\"\"do something\"\"\"
    """

    def get_data_dict(self, request):
        return request.post_data

class cookie(ArgumentSelector):
    """
    This :class:`ArgumentSelector` implementation looks up an HTTP
    cookie.

    Example::

        @teapot.routing.cookie("cookiename", "cookie")
        @teapot.route("/")
        def handle_index(self, cookie):
            \"\"\"do something\"\"\"
    """
    def get_data_dict(self, request):
        return request.cookie_data

def route(path, *paths, order=0, make_constructor_routable=False):
    """
    Decorate a (static-, class- or instance-) method or function with routing
    information. Note that decorating a class using this decorator is not
    possible.

    The *order* determines the order in which routing information is visited
    upon looking up a route. The lower the value of *order*, the more precedence
    has a route.

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
    paths = [path if hasattr(path, "select") else formatted_path(path)
             for path in paths]

    selectors = [one_of(paths)]
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
            obj_selectors.append(AnnotationProcessor(obj.__func__))
            info = Leaf(obj_selectors, obj.__func__, **kwargs)
            setrouteinfo(obj.__func__, info)
        elif isinstance(obj, classmethod):
            obj_selectors.append(AnnotationProcessor(obj.__func__))
            info = LeafPrototype(
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
                obj_selectors.append(AnnotationProcessor(obj))
            info = LeafPrototype(
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

def find_route(root, request):
    """
    Tries to find a route for the given *request* inside *root*, which
    must be an object with routing information.
    """

    if not isroutable(root):
        raise TypeError("{!r} is not routable".format(root))

    localrequest = Context.from_request(request)
    return getrouteinfo(root).route(localrequest)

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

        response = self.pre_headers_hook(request, response)

        # function does not want to return any data by itself
        # we wrap the response headers and everything else into the generator
        # format
        yield response
        if response.body is None:
            yield from result
        elif (hasattr(response.body, "__iter__") and
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
