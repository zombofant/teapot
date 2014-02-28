"""
Web Form Handling
#################

.. autoclass:: WebFormError
    :members:

.. autoclass:: WebForm
    :members:

"""

import abc
import inspect

class ValidationError(ValueError):
    def __init__(self, err, field, instance):
        super().__init__(
            "field validation failed for {} on {}: {}".format(
                field.name,
                instance,
                err))
        self.field = field
        self.instance = instance

class Meta(type):
    def __new__(mcls, name, bases, namespace):
        field_descriptors = [
            value
            for value in namespace.values()
            if isinstance(value, field)
        ]

        namespace["field_descriptors"] = field_descriptors
        return super().__new__(mcls, name, bases, namespace)

class RowMeta(Meta):
    pass

class field:
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
        raise AttributeError("deleting is not supported")

    def default(self, callable):
        self.defaultcon = callable
        return self

class Form(metaclass=Meta):
    def __init__(self, *args, **kwargs):
        self.fields = {}
        super().__init__(*args, **kwargs)
