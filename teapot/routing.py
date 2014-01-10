import abc
import copy
import functools

import teapot.errors

routeinfo_attr = "__net_zombofant_teapot_routeinfo__"

def isroutable(obj):
    global routeinfo_attr
    return hasattr(obj, routeinfo_attr)

def getrouteinfo(obj):
    global routeinfo_attr
    return getattr(obj, routeinfo_attr)

def setrouteinfo(obj, value):
    global routeinfo_attr
    return setattr(obj, routeinfo_attr, value)

@functools.total_ordering
class Info(metaclass=abc.ABCMeta):
    """
    Baseclass to implement routing information. *order* defines in
    which order the routers are evaluated.
    """

    def __init__(self, selectors, order=0, **kwargs):
        super().__init__(**kwargs)
        self._order = order
        self._selectors = selectors

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
        localrequest = copy.copy(request)
        try:
            if not all(selector(request)
                       for selector in self._selectors):
                # not all selectors did match
                return False, None
        except teapot.errors.ResponseError as err:
            return False, err
        return self._do_route(localrequest)

    def __lt__(self, other):
        return self.order < other.order

class Group(Info):
    """
    This is a generic group of *routables*. Upon routing, all
    routables will be evaluated in the given order.
    """

    def __init__(self, selectors, routables, **kwargs):
        super().__init__(selectors)
        self._routables = routables

    def _do_route(self, localrequest):
        first_error = None
        for routable in self._routables:
            success, data = routable.route(localrequest)
            if success:
                return success, data
            elif data:
                first_error = first_error or data

        return False, first_error

class Object(Group):
    """
    This class provides the routing information for an object. It is
    an aggregate of other routing information providers, usually for
    the methods of the object. It can be created from a :class:`Class`
    routing information by supplying the objects instance.
    """

    def __init__(self, routables, selectors=[], **kwargs):
        super().__init__(selectors, routables, **kwargs)

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
                 clsroutables,
                 instanceroutables,
                 selectors=[],
                 **kwargs):
        super().__init__(selectors, clsroutables, **kwargs)
        self._instanceroutables = instanceroutables
        self._class_routables_initialized = False

    def _init_class_routable(self, cls, routable):
        if hasattr(routable, "get"):
            return routable.get(None, cls)
        return routable

    def _init_class_routables(self, cls):
        if self._class_routables_initialized:
            return

        self._routables = list(map(
            functools.partial(self._init_class_routable, cls),
            self._routables))
        self._class_routables_initialized = True

    def _init_instance_routable(self, instance, cls, routable):
        if hasattr(routable, "get"):
            return routable.get(instance, cls)
        return routable

    def _get_for_instance(self, instance, cls):
        routables = list(map(
            functools.partial(self._init_instance_routable,
                              instance, cls),
            self._instanceroutables))

        return Object(routables,
                      selectors=self._selectors,
                      order=self._order)

    def __get__(self, instance, cls):
        if instance is None:
            self._init_class_routables(cls)
            return self
        try:
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
        self._callable = callable

    def _do_route(self, localrequest):
        return True, functools.partial(self._callable,
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
    def __init__(self,
                 selectors,
                 base_callable,
                 is_instance_leaf,
                 **kwargs):
        super().__init__(selectors, base_callable, **kwargs)
        self._kwargs = kwargs
        self.is_instance_leaf = is_instance_leaf

    def get(self, instance, cls):
        if self.is_instance_leaf:
            if instance is None:
                raise ValueError("instance must not be None for "
                                 "instance leaf prototypes.")
            return MethodLeaf(self._selectors,
                              self._callable,
                              instance,
                              **self._kwargs)
        return MethodLeaf(self._selectors,
                          self._callable,
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
        instanceroutables = list()
        classroutables = list()

        for name, obj in namespace.items():
            try:
                info = getrouteinfo(obj)
            except AttributeError as err:
                continue

            if (    not hasattr(info, "is_instance_leaf") or
                    not info.is_instance_leaf):
                classroutables.append(info)
            instanceroutables.append(info)

        for base in bases:
            try:
                info = getrouteinfo(base)
            except AttributeError as err:
                continue

            classroutables.extend(info._routables)
            instanceroutables.extend(info._instanceroutables)

        namespace[routeinfo_attr] = Class(
            classroutables,
            instanceroutables)

        return type.__new__(mcls, clsname, bases, namespace)

def route(path, order=0):
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

    def decorator(obj):
        if isroutable(obj):
            raise ValueError("{!r} already has a route".format(obj))

        if not hasattr(obj, "__call__"):
            raise TypeError("{!r} is not routable (must be "
                            "callable)".format(obj))

        selectors = []
        kwargs = {"order": order}

        if isinstance(obj, staticmethod):
            info = Leaf(selectors, obj.__func__, **kwargs)
        elif isinstance(obj, classmethod):
            info = LeafPrototype(selectors,
                                 obj.__func__,
                                 False,
                                 **kwargs)
        else:
            info = LeafPrototype(selectors,
                                 obj,
                                 True,
                                 **kwargs)

        setrouteinfo(obj, info)
        return obj

    return decorator
