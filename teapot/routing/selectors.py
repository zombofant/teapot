# the documentation for this module is covered by the __init__ of the
# teapot.routing package.

import abc
import functools
import string
import re
import logging

import teapot.request
import teapot.forms
from teapot.routing.info import *

__all__ = [
    "rebase",
    "queryarg",
    "postarg",
    "cookie",
    "content_type",
    "method",
    "formatted_path",
    "webform"
    ]

logger = logging.getLogger(__name__)

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

    Example::

        @teapot.rebase("/foo")
        class MyRoutable(metaclass=teapot.RoutableMeta):

            @teapot.route("/bar")
            def handle_foo_bar(self):
                \"\"\"this will match requests to /foo/bar\"\"\"
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

        @teapot.queryarg("argname", "my_arg", str)
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

        @teapot.postarg("argname", "my_arg")
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

        @teapot.cookie("cookiename", "cookie")
        @teapot.route("/")
        def handle_index(self, cookie):
            \"\"\"do something\"\"\"
    """
    def get_data_dict(self, request):
        return request.cookie_data

class content_type(Selector):
    """
    This :class:`Selector` adds a result content type to the possible results of
    the routable. If no ``content_type`` selector is attached to a routable, it
    is assumed that it can serve all content types and will perform content
    negotiation by itself.

    Specify the supported content types as arguments to the decorator. It is
    possible to attach the decorator multiple times. The effect is the same as
    if the content types had been passed one by one to one call of the
    decorator.

    Example::

        @teapot.content_type(
            "text/plain"),
            None)
        @teapot.route("/")
        def index_text(self):
            pass

        @teapot.content_type("image/png")
        @teapot.route("/")
        def index_image(self):
            pass

    In the above example, if a request where ``image/png`` is the most preferred
    MIME type is received, ``index_image`` will be picked. If a request with
    none of the above mentioned content types is received, ``index_text`` will
    be picked, because it has the catch all content type :data:`None`. Any
    specific content type takes precedence over :data:`None`, which is why
    ``index_image`` is picked in favour of ``index_text`` if the client accepts
    ``image/png``, but not ``text/plain``.

    For unrouting, this selector has no effect.
    """

    def __init__(self, *content_types, **kwargs):
        super().__init__(**kwargs)
        self._content_types = frozenset(
            str(content_type) if content_type is not None else None
            for content_type in content_types)

    def select(self, request):
        if request.content_types is not None:
            request.content_types |= self._content_types
        else:
            request.content_types = set(self._content_types)
        return True

    def unselect(self, request):
        pass

    def __repr__(self):
        return "<{} with {}>".format(
            type(self).__qualname__,
            self._content_types)

class method(Selector):
    """
    Select against the given HTTP *request methods*. If the request uses any of
    the given methods, the selector succeeds. At least one method must be
    supplied.

    For unrouting, the first method is used.
    """

    def __init__(self, unroute_request_method, *more_request_methods, **kwargs):
        super().__init__(**kwargs)
        self._request_method_default = unroute_request_method
        self._request_methods = set(more_request_methods)
        self._request_methods.add(unroute_request_method)

    def select(self, request):
        return request.method in self._request_methods

    def unselect(self, request):
        request.method = self._request_method_default

class webform(Selector):
    """
    A selector that selects a set of request arguments defined as form fields
    within *webform_class*, a :class:`WebForm` subclass, and passes an instance
    of it to the final routable either as keyword argument *destarg* or as
    positional argument, if *destarg* is :data:`None`.

    The selector does only match, if all defined webform fields in
    *webform_class* can be filled from available request arguments.

    Example::

        class MyForm(teapot.WebForm):
            @teapot.webformfield
            def a_form_field(value): pass

        @teapot.webform(MyForm, "the_form"):
        @teapot.route("/path")
        def handle_form_post(the_form):
            \"\"\"do something\"\"\"
    """

    def __init__(self, webform_class, destarg=None, **kwargs):
        super().__init__(**kwargs)
        self._webform_class = webform_class
        self._destarg = destarg

    def select(self, request):
        try:
            form = self._webform_class(request.post_data)
        except KeyError:
            # missing form fields in post_data
            logging.debug("missing data to create web form")
            return False
        if self._destarg is None:
            request.args.append(form)
        else:
            request.kwargs[self._destarg] = form
        return True

    def unselect(self, request):
        return True
