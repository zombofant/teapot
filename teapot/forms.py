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

__all__ = [
    "WebFormError",
    "WebForm",
    "webformfield"
    ]

class WebFormError(Exception):
    """
    An :class:`Exception` that is thrown on webform errors.

    Example::

        class MyForm(WebForm):
            @teapot.webformfield
            def fieldname(value):
                # validate it
                if value != 'expected_value':
                    raise WebFormError("unexpected value!")

    """
    pass

class webformfield:
    """
    This class allows to decorate your :class:`WebForm` methods as a
    webform field.

    """
    _webformfield_attr = "__zombofant_net_teapot_webformfield__"

    @classmethod
    def iswebformfield(cls, obj):
        return hasattr(obj, cls._webformfield_attr)

    def __init__(self, func):
        self._func = func
        self._setwebformfield(func.__name__)

    def __call__(self):
        def webformfield_decorator(*args, **kwargs):
            return self._func(*args, **kwargs)
        return webformfield_decorator

    def __get__(self, instance, owner):
        try:
            return getattr(instance, "_values_dict")[self.field_name]
        except KeyError:
            return self

    def _setwebformfield(self, name):
        setattr(self, self._webformfield_attr, name)

    def set_values(self, instance, values):
        self._func(values) # validate
        getattr(instance, "_values_dict")[self.field_name] = values

    @property
    def field_name(self):
        return getattr(self, self._webformfield_attr)

class WebForm(metaclass=abc.ABCMeta):
    """
    This class is the abstract base for web formular representations in
    teapot. In order to encapsulate the data of your own webform, you just
    have to describe it as a subclass of :class:`WebForm`.

    To mark a method as a form field, you can decorate it with
    :class:`webformfield`. Within the method, you may validate the form
    field's value or simply pass (see example below).

    Some common validation constraints are also available as decorators.

    See the :class:`webform` selector on how to bind your form description to
    real form data inside a routable.

    Example::

        # describe my web form
        class MyForm(teapot.WebForm):

            @teapot.webformfield
            def name(value): pass

            @teapot.webformfield
            def password(value):
                if is_bad_pw(value):
                    raise teapot.WebFormError("Password is bad!")

        # pass webform to routable and handle it
        @teapot.webform(MyForm, "the_form")
        @teapot.route("/form")
        def my_routable(the_form):
            if the_form.has_errors():
                errors = the_form.get_error_dict()
                \"\"\"do something\"\"\"
            else:
                name = the_form.name
                password = the_form.password

    """

    def __init__(self, field_value_dict):
        self._error_dict = {}
        self._values_dict = {}
        self._find_webformfields()
        self._apply_field_values(field_value_dict)

    def _find_webformfields(self):
        self._webformfields = []
        for member in inspect.getmembers(self):
            if member[0].startswith("_"):
                continue
            if webformfield.iswebformfield(member[1]):
                self._webformfields.append(member[1])

    def _apply_field_values(self, field_values_dict):
        if None in field_values_dict.values():
            raise ValueError("webform field values must not be None")
        for field in self._webformfields:
            try:
                field.set_values(self, field_values_dict[field.field_name])
            except WebFormError as error:
                self._error_dict.setdefault(
                        field.field_name,
                        []).append(str(error))

    def get_error_dict(self):
        """
        Return the dictionary containing fieldname keys and the list of error
        strings related to that field as value. See :class:`WebFormError` on
        how to raise webform errors.

        See also: :meth:`has_errors`

        """
        return self._error_dict

    def has_errors(self):
        """
        Returns wheter or not :class:`WebFormError`s have occured when
        applying form data to this webform.

        """
        return bool(self._error_dict)
