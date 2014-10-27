import abc
import collections
import functools

import teapot.forms

from datetime import datetime, timedelta

__all__ = [
    "DateTimeMode",
    "TextField",
    "IntField",
    "DateTimeField",
    "CheckboxField",
    "EnumField",
    "PasswordField"
]

class Supermode:
    @abc.abstractmethod
    def dtformat(self, dt):
        raise NotImplementedError()

    @abc.abstractproperty
    def max_level(self):
        raise NotImplementedError()

    @property
    def week_support(self):
        return True

class _SupermodeDateTime(Supermode):

    @property
    def max_level(self):
        return DateTimeMode.LEVEL_MICROSECOND

    def __str__(self):
        return "DateTime"

SupermodeDateTime = _SupermodeDateTime()

class _SupermodeTime(Supermode):
    def dtformat(self, dt):
        return dt.strftime("%H:%M") + "{:06.3f}".format(
            dt.second + (dt.microsecond / 1000000))

    @property
    def max_level(self):
        return DateTimeMode.LEVEL_MICROSECOND

    @property
    def week_support(self):
        return False

    def __str__(self):
        return "Time"

SupermodeTime = _SupermodeTime()

class _SupermodeDate(Supermode):
    def dtformat(self, dt):
        return dt.strftime("%Y-%m-%d")

    @property
    def max_level(self):
        return DateTimeMode.LEVEL_DAY

    def __str__(self):
        return "Date"

SupermodeDate = _SupermodeDate()

_DateTimeMode = collections.namedtuple(
    "_DateTimeMode",
    (
        'supermode',
        'level',
        'week'
    ))

class DateTimeMode(_DateTimeMode):
    """
    Specify a datetime mode for a HTML5 datetime input. The following fully
    qualified modes are predefined (these attributes are attributes on the
    **class** :class:`DateTimeMode`):

    .. attribute:: DateTime

       This mode preserves all fields of the :class:`datetime.datetime` object.

    .. attribute:: Date

       This mode preserves only the year, month and day fields of a
       :class:`datetime.datetime` object.

    .. attribute:: Time

       This mode preserves all fields of the :class:`datetime.datetime` object,
       but does not allow pointing to weeks.

    These modes can be restricted by combining them (using the ``&`` operator)
    with one or more of the following modes:

    .. attribute:: Year

       Preserve only the year.

    .. attribute:: Month

       Preserve only the year and the month.

    .. attribute:: Day

       Preserve only the year, the month and the day.

    .. attribute:: Week

       Preserve only the year, the month and the day, and point to a week.

    .. attribute:: Hour

       Preserve only the year, the month, the day and the hour.

    .. attribute:: Minute

       Preserve everything but the second and the microsecond.

    .. attribute:: Second

       Preserve everything but the microsecond.

    Example::

      # a mode which provides values accurate to the minute
      mode = teapot.html.DateTimeMode.Full & teapot.html.DateTimeMode.Minute


    """

    LEVEL_YEAR = 0
    LEVEL_MONTH = 1
    LEVEL_DAY = 2
    LEVEL_HOUR = 3
    LEVEL_MINUTE = 4
    LEVEL_SECOND = 5
    LEVEL_MICROSECOND = 6

    @classmethod
    def validate(cls, supermode, level, week):
        if supermode is None:
            return

        if level > supermode.max_level:
            raise ValueError("Level {} not supported by supermode"
                             " {}".format(level, supermode))
        if week and not supermode.week_support:
            raise ValueError("Supermode {} does not support weeks".format(
                supermode))

    def __new__(cls, supermode, level, week):
        cls.validate(supermode, level, week)
        return _DateTimeMode.__new__(cls, supermode, level, week)

    def __and__(self, other):
        if self.supermode is not None and other.supermode is not None:
            if self.supermode != other.supermode:
                raise ValueError("Supermodes must be equal or None")

        if self.week != other.week:
            raise ValueError("Week-pinning must be equal")

        new_supermode = self.supermode or other.supermode
        new_level = min(self.level, other.level)
        new_week = self.week or other.week
        if new_week:
            new_level = min(self.LEVEL_DAY, new_level)

        return type(self)(new_supermode, new_level, new_week)

    def __iand__(self, other):
        return self & other

    def truncate_datetime(self, dt):
        props = [
            ("month", 1),
            ("day", 1),
            ("hour", 0),
            ("minute", 0),
            ("second", 0),
            ("microsecond", 0)
        ]
        truncation = dict(props[self.level:])
        return dt.replace(**truncation)

    def format(self, dt):
        if not self.supermode:
            raise ValueError("Supermode not specified")
        return self.supermode.dtformat(dt, self.week)

DateTimeMode.Year = DateTimeMode(None, DateTimeMode.LEVEL_YEAR, False)
DateTimeMode.Month = DateTimeMode(None, DateTimeMode.LEVEL_MONTH, False)
DateTimeMode.Day = DateTimeMode(None, DateTimeMode.LEVEL_DAY, False)
DateTimeMode.Minute = DateTimeMode(None, DateTimeMode.LEVEL_MINUTE, False)
DateTimeMode.Hour = DateTimeMode(None, DateTimeMode.LEVEL_HOUR, False)
DateTimeMode.Second = DateTimeMode(None, DateTimeMode.LEVEL_SECOND, False)
DateTimeMode.Microsecond = DateTimeMode(None,
                                        DateTimeMode.LEVEL_MICROSECOND,
                                        False)
DateTimeMode.DateTime = DateTimeMode(SupermodeDateTime,
                                     DateTimeMode.LEVEL_MICROSECOND,
                                     False)
DateTimeMode.Full = DateTimeMode.DateTime
DateTimeMode.Time = DateTimeMode(SupermodeTime,
                                 DateTimeMode.LEVEL_MICROSECOND,
                                 False)
DateTimeMode.Date = DateTimeMode(SupermodeDate,
                                 DateTimeMode.LEVEL_DAY,
                                 False)
DateTimeMode.Week = DateTimeMode(None, DateTimeMode.LEVEL_DAY, True)

class HTMLField:
    """
    This is a mixin for HTML fields. These fields can be shown more or less
    automatically by xsltea. They provide an additional property over normal
    fields.

    .. autoproperty: field_type
    """

    @property
    def field_type(self):
        """
        The default HTML field type for this field. This is only a suggestion
        and may be overriden by the specific view.
        """

        return "text"


class TextField(teapot.forms.TextField, HTMLField):
    """
    A plain ``text`` input field.
    """

class IntField(teapot.forms.IntField, HTMLField):
    """
    A ``number`` input field, taking an integer number.
    """

    @property
    def field_type(self):
        """
        The default field type for this field is a ``number`` input.
        """

        return "number"

class CheckboxField(teapot.forms.FlagField, HTMLField):
    """
    A check box compatible field.
    """

    @property
    def field_type(self):
        """
        The default field type for this field is a ``checkbox`` input.
        """

        return "checkbox"

def _generic_format(fmt, dt):
    return dt.strftime(fmt)

def _microseconds_format(basefmt, dt):
    return dt.strftime(basefmt) + "{:06.3f}".format(
        dt.second + (dt.microsecond / 1000000))

class DateTimeField(teapot.forms.DateTimeField, HTMLField):
    """
    Supports any of the HTML5 date time fields. *mode* must be a
    :class:`DateTimeMode` instance specifying the semantics of the field. Using
    :attr:`DateTimeMode.DateTime` is fine for most cases; you should only change
    this if you want to truncate the default date, for example.

    The *field_type* is the field type suggested to an HTML renderer -- this
    might be overriden by the handler, and the field is ready to support that
    and return the correct value according to the HTML standard.

    As with :class:`teapot.forms.DateTimeField`,
    :func:`~teapot.timeutils.parse_datetime` is used for parsing, and the
    semantics and supported formats apply. This implies that a
    :class:`DateTimeField` will accept *any* value which is valid according to
    the HTML5 standard, regardless of the *mode* and *field_type*. The value
    obtained through user submitted input is not truncated through *mode*. One
    can use the :attr:`mode` attribute to execute truncation, if required.

    Example::

      class MyFancyForm(teapot.forms.Form):
          # a <input type="datetime" />-optimized field, whose default value
          # will be cut off to the most recent whole minute
          some_datetime = teapot.html.DateTimeField(
              teapot.html.DateTimeMode.Full & teapot.html.DateTimeMode.Minute,
              "datetime")

    .. attribute:: mode

       The *mode* provided at construction time.

    """

    FORMATTERS = {
        "month": functools.partial(
            _generic_format,
            "%Y-%m"),
        "week": functools.partial(
            _generic_format,
            "%Y-W%V"),
        "date": functools.partial(
            _generic_format,
            "%Y-%m-%d"),
        "time": functools.partial(
            _microseconds_format,
            "%H:%M:"),
        "datetime": functools.partial(
            _microseconds_format,
            "%Y-%m-%dT%H:%M:")
    }


    def __init__(self, mode, field_type, **kwargs):
        super().__init__(**kwargs)
        self.mode = mode
        self._field_type = field_type

    def _default_default_generator(self):
        return self.mode.truncate_datetime(datetime.utcnow())

    @property
    def field_type(self):
        return self._field_type

    def to_field_value(self, instance, view_type):
        formatter = self.FORMATTERS.get(view_type, self.FORMATTERS["datetime"])
        return formatter(self.__get__(instance, type(instance))) + "Z"

class EnumField(teapot.forms.EnumField, HTMLField):
    @property
    def field_type(self):
        return "select"

class MultipleOptionField(teapot.forms.SetField, HTMLField):
    @property
    def field_type(self):
        return "select", "multiple"

class PasswordField(TextField):
    """
    A password field is a specialized text field, which uses the HTML
    ``"password"`` input type. In addition to that, values entered into the
    password field are not reflected to the client.
    """

    @property
    def field_type(self):
        return "password"

    def get_default(self, instance):
        return ""

    def _tag_error(self, instance, original_value, error):
        """
        This overrides the default implementation on
        :meth:`teapot.forms.CustomField._tag_error`, to prevent the original
        value to be sent back to the client (this is generally not desirable for
        password fields).
        """

        if isinstance(error, teapot.forms.ValidationError):
            error.field = self
            error.instance = instance
            return

        return teapot.forms.ValidationError(
            error,
            self,
            instance)

    def to_field_value(self, instance, view_type):
        return ""
