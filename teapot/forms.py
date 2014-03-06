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

"""

import abc
import collections
import itertools
import operator

import teapot.utils

class ValidationError(ValueError):
    def __init__(self, err, field, instance):
        super().__init__(
            "field validation failed for {} on {}: {}".format(
                field,
                instance,
                err))
        self.field = field
        self.instance = instance

class Meta(type):
    def __new__(mcls, name, bases, namespace):
        field_descriptors = [
            value
            for value in namespace.values()
            if isinstance(value, (field, rows))
        ]

        for name, descriptor in namespace.items():
            if isinstance(descriptor, rows):
                # fix rows names
                descriptor.name = name

        for base in reversed(bases):
            if hasattr(base, "field_descriptors"):
                field_descriptors[:0] = base.field_descriptors

        namespace["field_descriptors"] = field_descriptors
        return super().__new__(mcls, name, bases, namespace)

class RowMeta(Meta):
    pass

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
            raise ValidationError(err, self, instance) from err

        instance.fields[self.name] = value

    def __delete__(self, instance):
        try:
            del instance.fields[self.name]
        except KeyError:
            pass

    def key(self, instance):
        return instance.key() + self.name

    def load(self, instance, post_data):
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
        self.defaultcon = callable
        return self

    def __str__(self):
        return "<field name={!r}>".format(self.name)

class boolfield(field):
    def load(self, instance, post_data):
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
        return instance.key() + self.name

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

        if any(bool(item.errors)
               for item in rows):
            raise ValidationError(
                "One or more rows have errors",
                self,
                instance)

class Form(metaclass=Meta):
    def __init__(self, *args, post_data=None, **kwargs):
        self.fields = {}
        self.errors = {}
        super().__init__(*args, **kwargs)
        if post_data is not None:
            self.errors = self.fill_post_data(post_data)

    def key(self):
        return ""

    def fill_post_data(self, post_data):
        errors = {}
        for descriptor in self.field_descriptors:
            try:
                descriptor.load(self, post_data)
            except ValidationError as err:
                errors[descriptor] = err

        return errors

class Row(Form, metaclass=RowMeta):
    def __init__(self, *args, **kwargs):
        self.parent = None
        self.index = None
        super().__init__(*args, **kwargs)

    def key(self):
        if self.parent is not None:
            return "{}[{}].".format(
                self.parent.field.key(self.parent.instance),
                "" if self.index is None else self.index)
        else:
            return ""
