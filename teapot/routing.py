"""
Routing
#######

Teapot request routing is it’s valuable core.

Decorators for functions and methods
====================================

To make a function or other generic callable routable, one has to
decorate it with the ``route`` decorator:

.. autofunction:: route

A class (and its instances) and all of its member functions can be
made routable using the :class:`RoutableMeta` metaclass:

.. autoclass:: RoutableMeta

Decorators for routables
------------------------

An object which is already routable can further be modified using the
following decorators:

.. autofunction:: rebase


Request data selectors
======================

.. autoclass:: PathSelector
   :members:

.. autoclass:: PathFormatter
   :members:

Utilities to get information from routables
===========================================

.. autofunction:: isroutable

.. autofunction:: getrouteinfo

.. autofunction:: setrouteinfo

Router for server interfaces
============================

Server interfaces require a router which transforms the request into an
iterable which contains all the response metadata and contents.

.. autoclass:: Router
   :members:

Internal API
============

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

class Context:
    """
    The routing context is used to traverse through the request to
    find nodes to route to.

    *base* can be either another :class:`Context` instance (to create a blank
    context from another one, see below) or a :class:`~teapot.request.Request`
    to create a new context from a request.

    There is a difference between creating a context with anotehr context as
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

    def __init__(self, base,
                 request_method=teapot.request.Method.GET,
                 path="/",
                 scheme="http",
                 **kwargs):
        super().__init__(**kwargs)
        self._accept_content = \
            base.accept_content if base else \
            teapot.accept.all_content_types()
        self._accept_language = \
            base.accept_language if base else \
            teapot.accept.all_languages()
        self._args = []
        self._kwargs = {}
        self._method = \
            base.method if base else \
            request_method
        if hasattr(base, "original_request"):
            self._original_request = base.original_request
        else:
            self._original_request = base
        self.path = \
            base.path if base else path
        self._post_data = \
            None if base else {}
        self._query_data = \
            copy.copy(base.query_data) if base else \
            {}
        self._scheme = \
            base.scheme if base else \
            scheme

    def __deepcopy__(self, copydict):
        result = Context(self)
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
    def post_data(self):
        return self._post_data

    @property
    def query_data(self):
        return self._query_data

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
    Selectors are used throughout the routing tree to determine
    whether a path is legit for a given request.

    The most commonly used selector is the :class:`PathSelector` which
    selects on a portion of the request path.

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
        """

class PathSelector(Selector):
    """
    A path selector selects a static portion of the current request
    path. If the current path does not begin with the given *prefix*,
    the selection fails.
    """

    def __init__(self, prefix, **kwargs):
        super().__init__(**kwargs)
        self._prefix = prefix

    def select(self, request):
        try:
            request.rebase(self._prefix)
        except ValueError:
            return False
        return True

    def unselect(self, request):
        request.path = self._prefix + request.path

class PathFormatter(Selector):
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
    contexts arguments (see :prop:`Context.args`).

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

    """

    def __init__(self, format_string, strict=False, **kwargs):
        super().__init__(**kwargs)
        self._strict = strict
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
        result = self.parse(request.path)
        if not result:
            return False

        numbered, keywords, remainder = result

        request.args.extend(numbered)
        request.kwargs.update(keywords)

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

class OrSelector(Selector):
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
    paths = [path if hasattr(path, "select") else PathFormatter(path)
             for path in paths]

    selectors = [OrSelector(paths)]
    del paths

    def decorator(obj):
        if isroutable(obj):
            raise ValueError("{!r} already has a route".format(obj))

        kwargs = {"order": order}

        if isinstance(obj, type) and not make_constructor_routable:
            # this is a class
            raise TypeError("I don’t want to make a constructor routable. See"
                            "the docs for details and a workaround.")

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
            PathSelector(prefix))

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

def unroute(routable, *args, template_request=None, **kwargs):
    """
    Un-route the given *routable* and return a Request which would
    point to the given *routable*, inside the request tree to which the
    given *routable* belongs..
    """

    if template_request is None:
        request = Context(None, path="")
    else:
        request = Context(template_request)
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
    the :prop:`~teapot.request.Request.accept_charset` preference list from the
    request.
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

            if response.body is None:
                # function generates the data
                yield response
                yield from result
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

        # function does not want to return any data by itself
        # we wrap the response headers and everything else into the generator
        # format
        yield response
        if hasattr(response.body, "__iter__") and \
           not isinstance(response.body, bytes):
            yield from response.body
            return

        yield response.body

    def route_request(self, request):
        """
        Routes a given *request* using the set up routing root and returns the
        response format described at :meth:`wrap_result`.
        """
        success, data = find_route(self._root, request)

        if not success:
            if data is None:
                return self.handle_not_found(request)
            raise data

        result = data()
        yield from self.wrap_result(request, result)
