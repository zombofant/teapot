"""
Web Form Handling
#################

Teapot provides sophisticated means to deal with web forms, whose contents are
submitted as POST data.

To create a form, the easiest way is to inherit from the :class:`Form` class and
use :class:`field` decorators to annotate the form fields. Example::

    class Form(teapot.forms.Form):
        @teapot.forms.field
        def test_int(self, value):
            return int(value)

        @teapot.forms.field
        def test_int_with_default(self, value):
            return int(value)

        @test_int_with_default.default
        def test_int_with_default(self):
            return 10

This form has two fields, ``test_int`` and ``test_int_with_default``. Both are
validated against and converted to integers on assignment. The second one,
however, returns ``10`` when read before an assignment, while the first returns
:data:`None`.

Documentation for the different descriptors/decorators is also available:

.. autoclass:: field
   :members: key, load

.. autoclass:: boolfield

.. autoclass:: rows

Also the base classes:

.. autoclass:: Form

.. autoclass:: Row

The metaclasses:

.. autoclass:: Meta

.. autoclass:: RowMeta

And last, but not least, the exception type:

.. autoclass:: ValidationError

"""

import abc
import collections
import itertools
import operator

import teapot.utils

ACTION_PREFIX = "action:"

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

    def __init__(self, err, field, instance):
        super().__init__(
            "field validation failed for {} on {}: {}".format(
                field,
                instance,
                err))
        self.field = field
        self.instance = instance

    def register(self):
        self.instance.add_error(self.field, self)

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
            if isinstance(value, (field, rows))
        ]

        for base in reversed(bases):
            if hasattr(base, "field_descriptors"):
                field_descriptors[:0] = base.field_descriptors

        namespace["field_descriptors"] = field_descriptors
        cls = super().__new__(mcls, name, bases, namespace)

        for name, descriptor in namespace.items():
            if isinstance(descriptor, rows):
                # fix rows names
                if descriptor.rowcls is None:
                    descriptor.rowcls = cls
                descriptor.name = name

        return cls

class RowMeta(Meta):
    """
    This metaclass has no further implementation, but is there for future
    extension of the row classes, if neccessary.
    """

class field:
    """
    This decorator converts a function *validator* into a form field, using the
    function as validator for the field.

    Whenever an assignment to the property is performed, the value assigned is
    passed to the *validator* function (as second argument -- the first argument
    is, as usual, the object instance) and it is expected that the *validator*
    function returns the value which is ultimately to be assigned to the
    property.

    The :class:`field` takes care of value storage by itself -- the *validator*
    function does not need to (and should not) manage the storage by itself.

    If validation fails, :class:`ValueError` or :class:`TypeError` exceptions
    should be thrown. These are caught by the :class:`field` and re-raised as
    :class:`ValidationError` exceptions with the proper arguments.

    """

    def __init__(self,
                 validator,
                 default=None,
                 defaultcon=None,
                 name=None):
        if default and defaultcon:
            raise ValueError("At most one of default and defaultcon must be given")

        if name is None:
            name = validator.__name__

        self.name = name
        self.validator = validator
        self.defaultcon = defaultcon or (lambda x: default)

    def __get__(self, instance, cls):
        if instance is None:
            return self

        try:
            return instance.fields[self.name]
        except KeyError:
            value = self.defaultcon(instance)
            instance.fields[self.name] = value
            return value

    def __set__(self, instance, value):
        try:
            value = self.validator(instance, value)
        except ValidationError as err:
            raise
        except (ValueError, TypeError) as err:
            raise ValidationError(err, self, instance,
                                  original_value=value) from err

        instance.fields[self.name] = value

    def __delete__(self, instance):
        try:
            del instance.fields[self.name]
        except KeyError:
            pass

    def key(self, instance):
        """
        Return the full name of the HTML form element in the context of a given
        form (or row) *instance*.
        """
        return instance.get_html_field_key() + self.name

    def load(self, instance, post_data):
        """
        Try to load the data for this field for the given *instance* from the
        *post_data*. If loading fails, :class:`ValidationError` exceptions are
        thrown.
        """
        try:
            values = post_data.pop(self.name)
            value = values.pop()
            if len(values) > 0:
                raise ValueError("too many values")

        except ValueError as err:
            return ValidationError(
                "Unexpected amount of values (must be exactly 1)",
                self,
                instance)
        except KeyError as err:
            return ValidationError(
                "Missing POST data",
                self,
                instance)

        self.__set__(instance, value)

    def default(self, callable):
        """
        Set the constructor for the default value to *callable*.
        """
        self.defaultcon = callable
        return self

    def postvalidate(self, instance, request):
        """
        Run post-validation using the given *request* for the given
        *instance*. This is a noop by default.
        """

    def __str__(self):
        return "<field name={!r}>".format(self.name)

class boolfield(field):
    """
    Due to the nature of HTML, it is required that boolean values, represented
    by checkboxes, have special handling: Checkboxes do not generate any post
    data if they are not checked.
    """

    def load(self, instance, post_data):
        """
        Handle the special case of a checkbox field. That is, a missing key is
        not a fatal condition, but is interpreted as :data:`False` value.

        See :meth:`field.load` for more information.
        """
        try:
            values = post_data.pop(self.name)
            value = values.pop()
            if len(values) > 0:
                raise ValueError("too many values")

        except ValueError as err:
            return ValidationError(
                "Unexpected amount of values (must be exactly 1)",
                self,
                instance)
        except KeyError as err:
            value = False
        else:
            value = True

        self.__set__(instance, value)

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

class rows:
    """
    This is not a decorator, but a plain descriptor to be used to host a list of
    elements in a :class:`Form`. The elements are instances of *rowcls*, or of
    the form itself, if *rowcls* is passed as :data:`None`.

    On loading the data from POST, elements are created as neccessary. It is
    possible to add elements after loading elements from POST or after empty
    construction and re-serialize the form to HTML without any issues.
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

    def __init__(self,
                 rowcls):
        super().__init__()
        self.rowcls = rowcls
        self.name = None

    def __get__(self, instance, cls):
        if instance is None:
            return self

        try:
            return instance.fields[self.name]
        except KeyError:
            return instance.fields.setdefault(
                self.name,
                RowList(self, instance))

    def __set__(self, instance, value):
        raise AttributeError("assigning to a rows instance is not supported")

    def __delete__(self, instance):
        raise AttributeError("deleting a rows instance is not supported")

    def key(self, instance):
        return instance.get_html_field_key() + self.name

    def load(self, instance, post_data):
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
        rows.extend(
            self.rowcls(post_data=sub_data)
            for sub_data in items)

    def postvalidate(self, instance, request):
        """
        Run post-validation on all rows.
        """
        rows = self.__get__(instance, type(instance))
        for row in rows:
            row.postvalidate(request)

        if any(bool(item.errors)
               for item in rows):
            ValidationError(
                "One or more rows have errors",
                self,
                instance).register()

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

    """
    def __init__(self, *args, request=None, post_data=None, **kwargs):
        self.fields = {}
        self.errors = {}
        super().__init__(*args, **kwargs)
        post_data = post_data or (
            request.post_data if request is not None else None)
        if post_data is not None:
            self.fill_post_data(post_data)
        if request is not None:
            self.postvalidate(request)
        for k in list(self.errors.keys()):
            if not self.errors[k]:
                # remove empty error lists
                del self.errors[k]

    def add_error(self, field, exc):
        self.errors.setdefault(field, []).append(exc)

    def get_html_field_key(self):
        """
        Return the empty string. Subclasses, such as rows, might need a
        different implementation here. This is the prefix for all fields which
        are described by this form.
        """
        return ""

    def fill_post_data(self, post_data):
        for descriptor in self.field_descriptors:
            try:
                descriptor.load(self, post_data)
            except ValidationError as err:
                err.register()

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
