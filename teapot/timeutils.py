import calendar
import email.utils
import wsgiref.handlers
from datetime import datetime, timedelta

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
