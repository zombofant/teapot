# the documentation for this module is covered by the __init__ of the
# teapot.routing package.

import abc
import collections.abc
import copy
import functools
import logging

from teapot.utils import sortedlist

__all__ = [
    "isroutable",
    "getrouteinfo",
    "requirerouteinfo"
    ]

logger = logging.getLogger(__name__)

routeinfo_attr = "__net_zombofant_teapot_routeinfo__"

import teapot.errors

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

class RouteDestination:
    def __init__(self,
                 callable,
                 content_types=None,
                 languages=None,
                 **kwargs):
        super().__init__(**kwargs)
        self._callable = callable
        self.content_types = {None} if content_types is None \
                             else set(content_types)
        self.languages = {None} if languages is None \
                         else set(languages)

    def __call__(self):
        return self._callable()

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
        Subclasses must implement this. This *generator* method has to finalize
        or forward the routing to other :class:`Info` instances.

        The request object passed is the modified and rebased request.
        """
        return []

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
                return None
        except teapot.errors.ResponseError as err:
            return err
        result = yield from self._do_route(localrequest)
        return result

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
                error = yield from node.route(localrequest)
                if first_error is None and error is not None:
                    first_error = error

            return first_error
        finally:
            logger.debug("leaving routing group %r", self)

class CustomGroup(Group, collections.abc.MutableSet):
    """
    This is a group of *routenodes* which are automatically sorted for their
    *order* values. This is different from the default :class:`Group`
    implementation, which is both not expected to change after instanciation and
    expects that their routenodes are already sorted correctly.

    The :class:`CustomGroup` can be used to group routables together by
    hand. Its methods provide means to modify the set of routables during
    runtime. It is based on a sortedlist implementation, which is either sourced
    from the blist package, if it is available, or from a much slower drop-in
    replacement provided by teapot.
    """

    def __init__(self, selectors, routenodes=None, **kwargs):
        super().__init__(selectors, [], **kwargs)
        self.routenodes = sortedlist()
        if routenodes:
            self.routenodes.extend(routenodes)

        for routenode in self.routenodes:
            routenode.parent = self

    def __contains__(self, other):
        return other in self.routenodes

    def __iter__(self):
        return iter(self.routenodes)

    def __len__(self):
        return len(self.routenodes)

    def add(self, other):
        self.routenodes.add(other)

    def discard(self, other):
        self.routenodes.discard(other)

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
        yield RouteDestination(
            functools.partial(
                self.callable,
                *localrequest.args,
                **localrequest.kwargs),
            content_types=localrequest.content_types,
            languages=localrequest.languages)

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
