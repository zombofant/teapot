import abc
import copy
import functools

import teapot.errors
import teapot.request

import logging

logger = logging.getLogger(__name__)

routeinfo_attr = "__net_zombofant_teapot_routeinfo__"

__all__ = [
    "isroutable",
    "getrouteinfo",
    "route"]

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

class Context(teapot.request.Request):
    """
    The routing context is used to traverse through the request to
    find nodes to route to.

    It is a copy of the request and parts which are used during
    routing are removed from the request.
    """

    def __init__(self, request):
        super().__init__(
            request.method,
            request.path,
            request.scheme,
            copy.deepcopy(request.query_dict),
            copy.deepcopy(request.accept_info),
            original_request=request)

    def __deepcopy__(self, copydict):
        result = Context(self)
        result._original_request = self._original_request
        return result

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
            if not all(selector(localrequest)
                       for selector in self.selectors):
                # not all selectors did match
                return False, None
        except teapot.errors.ResponseError as err:
            return False, err
        return self._do_route(localrequest)

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
                 selectors=[],
                 **kwargs):
        super().__init__(selectors, cls_routenodes, **kwargs)
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
        return True, functools.partial(self.callable,
                                       localrequest)

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

    .. impl-detail::

        The attribute contains an instance of :class:`Info`, which
        defines the routing of the class. The :class:`Info` instance
        most likely will contain references to methods, which are
        resolved using a ``__get__`` override.
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

def path_selector(path, request):
    try:
        request.rebase(path)
    except ValueError:
        return False
    return True

def or_selector(selectors, request):
    return any(selector(request) for selector in selectors)

def route(path, *paths, order=0):
    """
    Decorate a (static-, class- or instance-) method or function with
    routing information. Note that decorating a class using this
    decorator is not possible.

    The *order* determines the order in which routing information is
    visited upon looking up a route. The lower the value of *order*,
    the more precedence has a route.

    In classes, routes defined inside the class itself take precedence
    over routes defined in the base classes, independent of the order.
    """

    paths = [path] + list(paths)

    def decorator(obj):
        if isroutable(obj):
            raise ValueError("{!r} already has a route".format(obj))

        selectors = [
            functools.partial(
                or_selector,
                [
                    functools.partial(path_selector, path)
                    for path in paths
                ])
        ]
        kwargs = {"order": order}

        if isinstance(obj, staticmethod):
            info = Leaf(selectors, obj.__func__, **kwargs)
            setrouteinfo(obj.__func__, info)
        elif isinstance(obj, classmethod):
            info = LeafPrototype(selectors,
                                 obj.__func__,
                                 False,
                                 **kwargs)
            setrouteinfo(obj.__func__, info)
        else:
            if not hasattr(obj, "__call__"):
                raise TypeError("{!r} is not routable (must be "
                                "callable or classmethod or "
                                "staticmethod)".format(obj))

            info = LeafPrototype(selectors,
                                 obj,
                                 True,
                                 **kwargs)

        setrouteinfo(obj, info)
        return obj

    return decorator

def rebase(prefix):
    """
    Decorates an object such that the routing is rebased by the given
    path *prefix*.
    """

    def decorator(obj):
        if not isroutable(obj):
            raise ValueError("{!r} does not have routing "
                             "information".format(
                                 obj))

        info = getrouteinfo(obj)
        info.selectors.insert(
            0,
            functools.partial(
                path_selector,
                prefix))

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

    localrequest = Context(request)
    return getrouteinfo(root).route(localrequest)
