"""
Web Form Handling
#################

Teapot provides sophisticated means to deal with web forms, whose contents are
submitted as POST data.

To create a form, the easiest way is to inherit from the :class:`Form` class and
use the field classes provided by this module:

    class Form(teapot.forms.Form):
        test_int = teapot.forms.IntField()
        test_int_with_default = teapot.forms.IntField(default=10)
        some_text = teapot.forms.TextField()

Several built in field types are provided.

.. note::

   If using xsltea (or any other HTML serializer for that matter), you should
   also take a look at :mod:`teapot.html`, which provides fields specialized for
   the use with HTML output. For example, to support the HTML5 date and time
   fields, you need to use :class:`teapot.html.DateTimeField`.

.. autoclass:: TextField

.. autoclass:: IntField

.. autoclass:: FlagField

.. autoclass:: DateTimeField

.. autoclass:: Rows

To create forms and rows, the following two classes are needed. :class:`Row`
should be used as a base class if the objects are (also) used as rows in other
forms. :class:`Row` instances can also be used standalone.

.. autoclass:: Form

.. autoclass:: Row

Extending existing functionality
================================

To implement custom field types, the following base classes are provided, which
implement most of the field functionality.

.. autoclass:: CustomField

.. autoclass:: StaticDefaultField

.. autoclass:: CustomRows

The forms and rows are using the following metaclasses to annotate the fields
with additional required information which is not available at field
instanciation time:

.. autoclass:: Meta

.. autoclass:: RowMeta

And last, but not least, the exception type:

.. autoclass:: ValidationError

"""

import abc
import collections
import copy
import functools
import itertools
import operator
import weakref

import teapot.utils

from datetime import datetime, timedelta

ACTION_PREFIX = "action:"

def generator_aware_map(func, iterable):
    iterator = iter(iterable)
    while True:
        yield func(next(iterator))

def parse_key(key):
    parts = key.split(".")
    for i, part in enumerate(list(parts)):
        name, bracket, subscript = part.partition("[")
        if bracket is not None and subscript.endswith("]"):
            parts[i] = (name, int(subscript[:-1]))
        else:
            parts[i] = (name, )
    return parts

class ValidationError(ValueError):
    """
    A value error related to field validation. Indicates that the error *err*
    caused the field *field* (which refers to the descriptor, i.e. the
    :class:`rows` or :class:`field` instance) to fail validation on the given
    *instance*.

    On throwing a :class:`ValidationError` instance, it is recommended to give
    the causing exception as context using the ``raise .. from ..`` syntax.

    .. attribute:: field

       The *field* passed to the constructor.

    .. attribute:: instance

       The *instance* passed to the constructor.

    """

    def __init__(self, err, field, instance, original_value=None):
        super().__init__(
            "field validation failed for {} on {}: {}".format(
                field,
                instance,
                err))
        self.err = err
        self.field = field
        self.instance = instance
        self.original_value = original_value

    def __deepcopy__(self, d):
        result = copy.copy(self)
        result.err = copy.deepcopy(self.err, d)
        result.instance = copy.deepcopy(self.instance, d)
        return result

    def register(self):
        self.instance.add_error(self.field, self)

class FormErrors:
    """
    This namespace provides constructors for often-used errors in forms, to
    consolidate error messages. This eases i18n.
    """

    __new__ = None
    __init__ = None

    @staticmethod
    def must_not_be_empty():
        return ValueError("Must not be empty")

    @staticmethod
    def one_or_more_rows_have_errors():
        return ValueError("One or more rows have errors")

    @staticmethod
    def not_a_valid_integer():
        return ValueError("Must be a valid integer number")


class Meta(type):
    """
    A metaclass used to describe :class:`Form`. It takes care of collecting all
    the field descriptors and aggregating them in a list, which is stored as
    class attribute called :attr:`Form.field_descriptors`.

    All forms should use this metaclass.
    """

    def __new__(mcls, name, bases, namespace):
        field_descriptors = [
            value
            for value in namespace.values()
            if isinstance(value, CustomField)
        ]

        for base in reversed(bases):
            if hasattr(base, "field_descriptors"):
                field_descriptors[:0] = base.field_descriptors

        namespace["field_descriptors"] = field_descriptors
        cls = super().__new__(mcls, name, bases, namespace)

        for name, descriptor in namespace.items():
            if isinstance(descriptor, CustomField):
                if hasattr(descriptor, "rowcls") and descriptor.rowcls is None:
                    descriptor.rowcls = cls
                # fix rows names
                descriptor.name = name

        return cls

class RowMeta(Meta):
    """
    This metaclass has no further implementation, but is there for future
    extension of the row classes, if neccessary.
    """

class CustomField(metaclass=abc.ABCMeta):
    """
    Base class for defining form fields. The base class offers interfaces for
    serializers and parsers to access the fields data and metadata.

    The control flows for the different operations on fields are described in
    detail here, to help implementing custom subclasses.

    * **Retrieving a value from POST data**

      The :class:`teapot.request.Request` object along with a list of values
      applying to the field is passed to :meth:`from_field_values`. By default,
      this method calls :meth:`_extract_values` to retrieve **one** value,
      wrapped in a tuple (subclasses might return more than one value in their
      own implementation, but this also requires overriding
      :meth:`from_field_values`).

      The default implementation of :meth:`from_field_values` then continues to
      yield from the :meth:`input_validate` generator, which receives the
      request passed and the value obtained from :meth:`_extract_values`. The
      further interface of :meth:`input_validate` is described in its
      documentation.

    * **Providing values for display**

      When a serialized text representation is required, :meth:`to_field_value`
      is called. Usually, a single string is expected; for different field
      types, it might be sensible to return multiple values. To distinguish the
      display modes, check the *view_type* attribute.

    .. automethod:: from_field_values

    .. automethod:: get_field_options

    .. automethod:: get_default

    .. automethod:: key

    .. automethod:: input_validate

    .. automethod:: to_field_value

    .. automethod:: __set__

    .. automethod:: __get__

    .. automethod:: __delete__

    .. attribute:: name

       This is initially set to :data:`None`. If the class which has this object
       as a member does not use the :class:`Meta` metaclass, it must set this
       value manually.

       The :class:`Meta` metaclass will automatically assign the name of the
       attribute to which this object was assigned.

    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = None

    def __get__(self, instance, class_):
        """
        If this object is accessed through another object (that is, *instance*
        is not :data:`None`), the current value of the field is
        returned. Otherwise, this object is returned.
        """

        if instance is None:
            return self

        try:
            return instance._field_data[self]
        except KeyError:
            return instance._field_data.setdefault(
                self,
                self.get_default(instance))

    def __set__(self, instance, value):
        """
        Assign a new value to the field. Directly assigned values do not need to
        pass through input validation.
        """

        instance._field_data[self] = value

    def __delete__(self, instance):
        """
        Reset the field to the value provided by :prop:`default`. The evaluation
        of the :prop:`default` property takes place on the next read of the
        field.
        """

        try:
            del instance._field_data[self]
        except KeyError:
            pass

    def _extract_value(self, values):
        """
        Extract the value from the *values* supplied by client. If too many or
        too few values are present, raise :class:`ValueError`, otherwise return
        the acquired value.

        A value might of course be a list of values.
        """

        if len(values) != 1:
            raise ValueError("Too much or no field data supplied")

        return (values.pop(), )

    def _tag_error(self, instance, original_value, error):
        """
        Tag an *error* with metadata, by wrapping it in a
        :class:`ValidationError` instance pointing to this field.

        If *error* is a validation error, the attributes are updated to point to
        this field.
        """

        if isinstance(error, ValidationError):
            error.field = self
            error.instance = instance
            error.original_value = original_value
            return error

        return ValidationError(
            error,
            self,
            instance)

    @abc.abstractmethod
    def get_default(self, instance):
        """
        A default value to be returned when no value is assigned to the
        field. This must be implemented by deriving classes.

        This property is only accessed *once* per access for which no value is
        assigned.
        """

        return None

    def get_field_options(self, instance, request):
        """
        Provide a sequence of tuples which represent the options possible for
        this field. If the field has no restricted set of fields, call the
        default implementation, which will raise an appropiate exception..
        """
        raise NotImplementedError("This field does not support option"
                                  " enumeration")

    def from_field_values(self, instance, request, values):
        """
        Parse the *values* from the *request*. *values* must be a list of
        strings as supplied by the client. This method removes all values used
        from the list.

        This method is a generator. It yields a list of errors, if any, which
        must be fully evaluated for the changes to take place on the field.

        The default implementation checks for the presence of exactly one
        string, and will pass that string on to the :meth:`input_validate`
        method. If :meth:`input_validate` raises a :class:`ValueError`, it will
        be swallowed and evaluation aborts, without any changes made to the
        object. The error is propagated upwards as if it had been yielded, too.

        .. note::

           Deriving classes should perform any *parsing* and *conversion* of the
           values provided by the client in this method, while range checking
           and other validation should take place in :meth:`input_validate`.

        Any kind of errors which point to input manipulation, such as too few or
        too many values in the list of values, or values which should not be
        possible except in forged requests are expected to be raised during the
        first iteration of the generator, before any value is returned.

        Malformatted strings should never raise, but yield the error.

        After the whole generator has been evaluated, the field of *instance*
        carries the processed value.
        """

        value, = self._extract_value(values)
        try:
            result = yield from generator_aware_map(
                functools.partial(self._tag_error, instance, value),
                self.input_validate(request, value))
        except ValueError as err:
            # input_validate requests to no change to take place to the field
            yield self._tag_error(instance, value, err)
            return
        self.__set__(instance, result)

    def input_validate(self, request, value):
        """
        Validate the input and return the validated value. This allows the
        validation to non-fatally constraint values.
        """
        return value
        # required to make input_validate a generator
        yield None

    def key(self, instance):
        """
        Return a fully qualified string which uniquely points to this field.
        """
        return instance.get_html_field_key() + self.name

    def load(self, instance, request, data):
        """
        Find the appropriate key(s) and their values and call
        :meth:`from_field_values` on the values. Yields any errors encountered.

        The *data* dictionaries keys must be rebased such that they can be
        indexed by using the field :attr:`name`.
        """

        values = data.pop(self.name, [])
        yield from self.from_field_values(instance, request, values)

    def postvalidate(self, instance, request):
        """
        Perform any validation which is only possible after all other fields
        have been filled.
        """

    def to_field_value(self, instance, view_type):
        """
        Convert the value of the field on *instance* to a string which should be
        used with HTML views. *view_type* is a token which identifies the kind
        of view which will be used to display the field. Usually, it will be a
        string corresponding to the value of the ``type`` attribute of the HTML
        field used to show the contents.

        The default implementation returns the empty string if the value is
        :data:`None`, else it returns the value.
        """

        value = self.__get__(instance, type(instance))
        if value is None:
            return ""
        return str(value)

class StaticDefaultField(CustomField):
    """
    The :class:`StaticDefaultField` implements the :meth:`get_default` by
    returning the value provided in the *default* argument to the
    constructor. Direct use of this class is rarely useful; instead, use some of
    its subclasses, or derive your own class using a static default.
    """

    def __init__(self, *, default=None, **kwargs):
        super().__init__(**kwargs)
        self._default = default

    def get_default(self, instance):
        return self._default

class TextField(StaticDefaultField):
    """
    The :class:`TextField` does no validation; it takes the value provided as
    text, and defaults to the given *default*.
    """

    def __init__(self, default="", **kwargs):
        super().__init__(default=default, **kwargs)

class IntField(StaticDefaultField):
    """
    Parses the user submitted value as integer. If the value is empty and
    *allow_none* is :data:`True`, the value is set to :data:`None`, otherwise,
    for an empty value, an error is returned. Invalid integers also create an
    error.
    """

    def __init__(self, default=0, allow_none=False, **kwargs):
        super().__init__(default=default, **kwargs)
        self.allow_none = allow_none

    def input_validate(self, request, value):
        if not value:
            if self.allow_none:
                if hasattr(self.allow_none, "__call__"):
                    return self.allow_none()
                else:
                    return None

            raise FormErrors.must_not_be_empty()

        try:
            return int(value)
        except ValueError:
            raise FormErrors.not_a_valid_integer() from None

        yield None

class FlagField(StaticDefaultField):
    """
    This implements a boolean field which considers itself :data:`True` if
    exactly one value is present in the user submitted data (no matter what its
    contents are) and :data:`False` if no values are present.
    """

    def __init__(self, *, default=None, **kwargs):
        super().__init__(default=default, **kwargs)

    def _extract_value(self, values):
        if not values:
            return (False, )
        if len(values) > 1:
            raise ValueError("Too many values")

        values.pop()
        return (True,)

class DateTimeField(CustomField):
    """
    A :class:`DateTimeField` parses a variety of input formats as dates and/or
    times (see :func:`teapot.timeutils.parse_datetime` for a list of supported
    formats and conversion semantics).

    The value produced by :meth:`to_field_value` is always a full ISO date
    including microseconds and UTC offset specifier.
    """

    def __init__(self, *, default_generator=None, **kwargs):
        super().__init__(**kwargs)
        self._default_generator = (default_generator
                                   or self._default_default_generator)

    def _default_default_generator(self):
        return datetime.utcnow()

    def get_default(self, instance):
        return self._default_generator()

    def input_validate(self, request, value):
        try:
            return teapot.timeutils.parse_datetime(value)
        except Exception as err:
            print(err)
            raise
        yield None

    def to_field_value(self, instance, view_type):
        dt = self.__get__(instance, type(instance))
        return dt.strftime("%Y-%m-%dT%H:%M:%S.%f+0000")

class RowList(teapot.utils.InstrumentedList):
    """
    A custom list implementation which sets and unsets the :attr:`parent`
    attribute on all its children on insertion / removal. The attribute is set
    to the list itself, so that one can retrace the full path up to the root
    form for all list children.

    Retrieving elements from the list through iteration or subscript
    (e.g. ``l[x]``) makes the list mutate the elements insofar, as that an
    :attr:`index` is set on them to the current index of the element in the
    list. This is hacky, but required to track the index during form creation.

    .. attribute:: instance

       The :class:`Form` instance to which this list belongs

    .. attribute:: field

       The :class:`rows` field descriptor attached to the type of the
       :attr:`instance` to which this list is associated.


    """

    def __init__(self, field, instance):
        super().__init__()
        self.instance = instance
        self.field = field

    def _acquire_item(self, item):
        if item.parent is not None:
            raise ValueError("{} is already in another row list".format(item))
        item.parent = self

    def _release_item(self, item):
        item.parent = None

    def _map_index(self, sequence, slice):
        for i, item in zip(range(*slice.indices(len(self))), sequence):
            item.index = i
            yield item

    def __getitem__(self, index):
        item_s = super().__getitem__(index)
        if isinstance(index, slice):
            return list(self._map_index(item_s, index))
        else:
            item_s.index = index
            return item_s

    def __iter__(self):
        return self._map_index(
            super().__iter__(),
            slice(None))

class CustomRows(CustomField):
    """
    This is an abstract base class for descriptors which allow forms to contain
    fields which consist of multiple rows.

    The class of each row is defined by the :meth:`get_row_instance` method,
    which must be implemented by subclasses.

    On loading the data from POST, elements are created as neccessary. It is
    possible to add elements after loading elements from POST or after empty
    construction and re-serialize the form to HTML without any issues.

    The most common subclass is :class:`rows`, which implements rows of a static
    subclass.
    """

    @staticmethod
    def _splitkey(name, key):
        key = key[len(name)+1:]
        index, middle, field = key.partition("].")
        if not middle:
            raise ValueError(
                "{!r} is not a valid array accessor for name {!r}".format(
                    key, name))

        try:
            index = int(index)
        except ValueError as err:
            raise ValueError("Not a valid array index: {}".format(err)) from None

        return index, field

    def __init__(self):
        super().__init__()
        self.name = None

    def __set__(self, instance, value):
        raise AttributeError("assigning to a rows instance is not supported")

    def __delete__(self, instance):
        raise AttributeError("deleting a rows instance is not supported")

    def get_default(self, instance):
        return RowList(self, instance)

    @abc.abstractmethod
    def get_row_instance(self, request, subdata):
        """
        Return a row instance suitable to hold the given *subdata*.
        """

    def key(self, instance):
        return instance.get_html_field_key() + self.name

    def load(self, instance, request, post_data):
        prefix = self.name + "["
        try:
            grouped_data = [
                (self._splitkey(self.name, key), value)
                for key, value in post_data.items()
                if key.startswith(prefix)
            ]
        except ValueError as err:
            raise ValidationError(
                str(err),
                self,
                instance)

        grouped_data.sort(key=lambda x: x[0][0])
        items = []
        for key, iterable in itertools.groupby(grouped_data, key=lambda x: x[0][0]):
            items.append({
                valuekey: value
                for (_, valuekey), value in iterable
            })

        rows = self.__get__(instance, type(instance))
        instances = list(filter(
            lambda x: x is not None,
            (self.get_row_instance(request, subdata)
             for subdata in items)))
        rows.extend(instances)
        if any(instance.errors for instance in instances):
            yield FormErrors.one_or_more_rows_have_errors()

class Rows(CustomRows):
    """
    This is not a decorator, but a plain descriptor to be used to host a list of
    elements in a :class:`Form`. The elements are instances of *rowcls*, or of
    the form itself, if *rowcls* is passed as :data:`None`.
    """

    def __init__(self, rowcls):
        super().__init__()
        self.rowcls = rowcls

    def get_row_instance(self, request, subdata):
        return self.rowcls(request=request, post_data=subdata)

class Form(metaclass=Meta):
    """
    Base class for forms. Forms can either be default-constructed, that is,
    without any extra arguments, or constructed from *post_data*, which must be
    a dict ``{ name => [value] }``, that is, mapping the field names to a list
    of values.

    Instead of or in addition to *post_data*, *request* can be given. If
    *request* is given instead of *post_data*, the POST data is retrieved from
    the *request* object. If the *request* object is given, :meth:`postvalidate`
    is called with the *request* as argument after the POST data has been
    loaded, and before the error dict is cleaned up.

    On non-empty construction, the dict is parsed for data and the
    :attr:`errors` attribute is filled accordingly.

    .. attribute:: fields

       This is internal storage for the field descriptors to put their values
       in. It is not supposed to be touched by applications.

    .. attribute:: errors

       Maps descriptors to a :class:`ValidationError` instance, if any, which
       represents the error which occured while parsing the data from the
       *post_data* dict.

    Forms support copying and deep-copying through the standard python
    :mod:`copy` module. By default, only the field values (and thus, the rows in
    any multi-row fields) and the errors are deep-copied. If you need to
    deepcopy more fields, override the ``__deepcopy__`` method.
    """

    def __init__(self, *args, request=None, post_data=None, **kwargs):
        self._field_data = {}
        self.errors = {}
        super().__init__(*args, **kwargs)
        if request is not None:
            self.fill_post_data(request, post_data or request.post_data)
            self.postvalidate(request)
        for k in list(self.errors.keys()):
            if not self.errors[k]:
                # remove empty error lists
                del self.errors[k]

    def __deepcopy__(self, d):
        result = copy.copy(self)
        result.fields = copy.deepcopy(self.fields, d)
        result.errors = copy.deepcopy(self.errors, d)
        return result

    def add_error(self, field, exc):
        self.errors.setdefault(field, []).append(exc)

    def get_html_field_key(self):
        """
        Return the empty string. Subclasses, such as rows, might need a
        different implementation here. This is the prefix for all fields which
        are described by this form.
        """
        return ""

    def fill_post_data(self, request, post_data):
        for descriptor in self.field_descriptors:
            for error in descriptor.load(self, request, post_data):
                error.register()

    def find_action_by_key(self, key):
        try:
            path = parse_key(key)
        except ValueError:
            return None

        node = self
        for item in path[:-1]:
            name = item[0]
            try:
                node = getattr(node, name)
            except AttributeError:
                return None

            for subscript in item[1:]:
                try:
                    node = node[subscript]
                except (IndexError, KeyError):
                    return None

        return node, path[-1][0]

    def find_action(self, post_data):
        possible_actions = [
            key for key in post_data.keys()
            if key.startswith(ACTION_PREFIX)]
        if not possible_actions:
            return None

        action = possible_actions[0]
        del possible_actions

        action = action[len(ACTION_PREFIX):]
        return self.find_action_by_key(action)

    def postvalidate(self, request):
        """
        This method is called from within the constructor if the optional
        *request* keyword argument has been passed, after all POST data has been
        loaded.

        Note that this method is always called, even if errors occured during
        validation. As errors are cumulative, this allows to display full error
        messages right from the beginning.

        By default, this method only calls the postvalidators of any nested
        forms (that is, rows).
        """

        for field in self.field_descriptors:
            field.postvalidate(self, request)

    def to_post_data(self):
        """
        Construct and return a dictionary containing the POST data which would
        be required to fill the form in the state as it currently is.
        """

        d = {}
        for field in self.field_descriptors:
            field.to_post_data(d)
        return d

class Row(Form, metaclass=RowMeta):
    """
    This class should be used as baseclass for all rows in a form, but can also
    be used as a baseclass for a normal form.

    .. attribute:: parent

       This is set by the :class:`RowList` upon insertion to the
       :class:`RowList` instance itself, so that the form to which this row
       belongs can be retrieved by accessing :attr:`RowList.instance`.

    .. attribute:: index

       The index of the row inside the :class:`RowList`. This attribute is only
       set upon retrieval from the :class:`RowList` through iteration or direct
       subscript access (i.e. ``l[x]``). After modification of the list, the
       value of the attribute is not reliable anymore, until the object is
       re-fetched from the list.

    """

    def __init__(self, *args, **kwargs):
        self.parent = None
        self.index = None
        super().__init__(*args, **kwargs)

    def get_html_field_key(self):
        """
        If a :attr:`parent` is set, this returns the fully qualified name of the
        field to which the row belongs. Otherwise, the empty string is returned.
        """
        if self.parent is not None:
            return "{}[{}].".format(
                self.parent.field.key(self.parent.instance),
                "" if self.index is None else self.index)
        else:
            return ""
