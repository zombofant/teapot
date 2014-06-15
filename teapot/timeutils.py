"""
Date and time utility functions
###############################

These functions provide supplementary features, which are based on the standard
:mod:`datetime` module and other standard modules.

Date and time parsing
=====================

.. py:currentmodule:: teapot.timeutils

.. autofunction:: parse_http_date

.. autofunction:: parse_isodate_full

.. autofunction:: parse_datetime

.. autofunction:: weekmonday

Date and time conversion/formatting
===================================

.. autofunction:: to_unix_timestamp

.. autofunction:: format_http_date

"""

import calendar
import email.utils
import re
import wsgiref.handlers

from datetime import datetime, timedelta, timezone

__all__ = [
    "to_unix_timestamp",
    "parse_http_date",
    "format_http_date",
    "parse_isodate_full",
    "parse_datetime"
]

full_isodate_format = "%Y-%m-%dT%H:%M:%S.%f"

datetime_parsable_formats = [
    full_isodate_format,
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d",
    "%H:%M:%S.%f",
    "%H:%M:%S",
    "%Y-%m"
]

microsecond_re = re.compile(
    r"[0-9]+(\.[0-9]+)?")
weekdate_re = re.compile(
    r"([0-9]{4})-W([0-9]{1,2})")

def weekmonday(year, isoweek):
    """
    Return the monday of the ISO week *isoweek* in the given *year* as
    :class:`datetime.datetime` object, pointing to midnight on that day.
    """

    return datetime(year, 1, 1) + timedelta(
        days=isoweek*7-(datetime(year, 1, 4).isoweekday()+3))

def to_unix_timestamp(datetime):
    """
    Convert *datetime* to a UTC unix timestamp.
    """

    return calendar.timegm(datetime.utctimetuple())

def parse_http_date(httpdate):
    """
    Parse the string *httpdate* as a date according to RFC 2616 and return the
    resulting :class:`~datetime.datetime` instance.

    .. note::
        This uses :func:`email.utils.parsedate`.
    """

    return datetime(*email.utils.parsedate(httpdate)[:6])

def format_http_date(datetime):
    """
    Convert the :class:`~datetime.datetime` instance *datetime* into a string
    formatted to be compliant with the HTTP RFC.

    .. note::
        This uses :func:`wsgiref.handlers.format_date_time`.
    """

    return wsgiref.handlers.format_date_time(to_unix_timestamp(datetime))

def parse_isodate_full(s):
    """
    Parse a UTC ISO-formatted date+time string. The time zone specifier must be
    an appended ``Z``, or missing. This function supports parsing of
    milliseconds.

    Raises a :class:`ValueError` if parsing fails.
    """

    if s.endswith("Z"):
        s = s[:-1]

    return datetime.strptime(s, full_isodate_format)

def parse_datetime(s):
    """
    Parse a variety of datetime formats, according to the HTML5
    specfication. Supported formats are:

    * Full ISO datetime, with microsecond (ex.: 2014-06-15T14:04:08.124357)
    * Full ISO datetime, without microsecond (ex.: 2014-06-15T14:04:08)
    * Partial ISO datetime (ex.: 2014-06-15T14:04)
    * ISO date (ex.: 2014-06-15)
    * Month (ex.: 2014-06)
    * Week (pointing to the monday) (ex.: 2014-W24)

    All formats allow the specification of a UTC offset, by appending an offset
    like `+0100` or `-1200` or by giving explicit UTC reference by appending a
    `Z`. A timestamp with neither offset nor `Z` is treated as UTC.

    .. note::
       Note that due to specification of timezones, even inputs
       which should point to full dates (like for example 2014-06-15+1200) will
       contain non-zero values in the ``hour`` and possibly ``minute``
       attributes.

    """

    if isinstance(s, datetime):
        return s

    for fmt in datetime_parsable_formats:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass

        try:
            return datetime.strptime(s, fmt + "Z")
        except ValueError:
            pass

        fmt += "%z"
        try:
            dt = datetime.strptime(s, fmt)
        except ValueError:
            continue

        return dt.astimezone(timezone.utc).replace(tzinfo=None)


    # last resort: try to parse a week. we have to do this manually.

    m = weekdate_re.match(s)
    if m:
        yearstr, weekstr = m.groups()
        return weekmonday(int(yearstr), int(weekstr))

    raise ValueError("Not a valid UTC timestamp".format(s))
