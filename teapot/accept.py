"""
Accept header management
########################

.. autoclass:: AbstractPreference
   :members: rfc_match

.. autoclass:: CharsetPreference

.. autoclass:: LanguagePreference

.. autoclass:: MIMEPreference

Preference lists
================

.. autoclass:: AbstractPreferenceList
   :members: append_header, get_candidates, get_quality, best_match,
             get_sorted_by_preference

.. autoclass:: CharsetPreferenceList
   :members: inject_rfc_values

.. autoclass:: LanguagePreferenceList

.. autoclass:: MIMEPreferenceList

"""

import abc
import copy
import logging

from . import mime

logger = logging.getLogger(__name__)

def parse_locale(localestr):
    if not isinstance(localestr, str):
        return tuple(localestr)

    localestr = localestr.lower()

    if "_" in localestr:
        lang, _, variant = localestr.partition("_")
    else:
        lang, _, variant = localestr.partition("-")

    variant, _, encoding = variant.partition(".")
    if not variant:
        variant = None

    return lang, variant

def sanitize_preference_values(values):
    # print(values)
    return tuple(
        stripped_value if stripped_value != '*' else None
        for stripped_value in (
            value if value is None else value.strip()
            for value in values
        )
    )

def match_tuple(a, b, rhs_wildcard=True):
    if len(a) != len(b):
        raise ValueError("Tuples must have equal length")

    wildcard_penalty = 0
    for av, bv in zip(a, b):
        # the last clause is to catch rhs_wildcard pulling the rhs of the first
        # check to False
        if ((av is None) ^ (rhs_wildcard and bv is None)) and av is not bv:
            wildcard_penalty += 1
            continue

        if av != bv:
            return False, 0

    return True, wildcard_penalty

class AbstractPreference(metaclass=abc.ABCMeta):
    """
    Abstract base object to hold a generic preference. The *values* (of which
    there must be at least one) define what the preference is for. The *q* gives
    the strength of the preference and *parameters* are additional parameters
    which might be taken into account depending on the exact situation.

    This base class is used to implement the three different preference types
    from the `HTTP/1.1 RFC <https://tools.ietf.org/html/rfc2616>`_ (``Accept``,
    ``Accept-Charset``, ``Accept-Language``).

    For more details on the different preference types, please refer to the
    descendant classes:

    * :class:`MIMEPreference` – for ``Accept``-style content type preferences
    * :class:`CharsetPreference` – for ``Accept-Charset``-style charset
      preferences
    * :class:`LanguagePreference` – for ``Accept-Language``-style language
      preferences

    :class:`AbstractPreference` objects and their descendants are supposed to be
    immutable. Trying to modify members will lead to weird, undefined behaviour,
    which is why they are well hidden and guarded by read-only properties.

    .. attribute:: values

       The tuple of values defining the preference. This tuple has different
       meanings depending on the subclass being used.

    .. attribute:: q

       The quality value of the preference.

    .. attribute:: parameters

       A copy of the internal dictionary holding the additional parameters of
       the preference.

    .. attribute:: wildcards

       The number of wildcards (:data:`None` values) occuring in *values*.

    .. attribute:: specifity

       If :attr:`wildcards` is nonzero, this is ``-wildcards``, otherwise it is
       the amount of parameters. This can be used to achieve specifity ordering
       in the sense of the RFC.

    :class:`AbstractPreference` instances are hashable and compare equal if
    their values, their q values and their parameters match.
    """

    def __init__(self, *values, q=1.0, parameters={}):
        if not values:
            raise ValueError("Preference must have at least one value")

        super().__init__()
        self.__values = sanitize_preference_values(values)
        self.__q = q
        self.__parameters = parameters or {}

        self.__parameters_hash = hash(frozenset(self.__parameters.items()))

        # wildcards are less specific
        self.__wildcards = sum(1 for value in self.values if value is None)

        self.__specifity = (-self.__wildcards) or len(self.__parameters)

    @abc.abstractclassmethod
    def parse(cls, s, drop_parameters=False):
        """
        This method must be implemented by subclasses. It is given a string *s*
        which should be parsed as a single preference definition.

        Return the new instance holding that preference. If *drop_parameters* is
        true, the new instance has an empty parameters dict.
        """

    @classmethod
    def _parse_parameters(cls, s):
        value, *parameter_strs = s.lower().strip().split(";")
        parameters = {}
        for param in parameter_strs:
            param_key, _, param_value = param.partition("=")
            param_key = param_key.strip()
            param_value = param_value.strip()
            if not param_key or not param_value:
                continue

            parameters[param_key] = param_value

        try:
            qstr = parameters.pop("q")
            q = float(qstr)
        except KeyError:
            q = 1.0
        except ValueError:
            raise ValueError("not a valid q value: {}".format(qstr))

        return value, q, parameters

    @classmethod
    def _simple_parse(cls, s, value_delimiter):
        value, q, parameters = cls._parse_parameters(s)
        # print(value, q, parameters)
        value_parts = value.split(value_delimiter)
        return value_parts, q, parameters

    @classmethod
    def from_header_section(cls, s):
        logger.warn("use of deprecated function: from_header_section")
        return cls.parse(s)

    @property
    def values(self):
        return self.__values

    @property
    def q(self):
        return self.__q

    @property
    def values(self):
        return self.__values

    @property
    def parameters(self):
        return copy.copy(self.__parameters)

    @property
    def wildcards(self):
        return self.__wildcards

    @property
    def specifity(self):
        return self.__specifity

    @abc.abstractmethod
    def __str__(self):
        pass

    def _format_parameters(self):
        params_str = ";".join(
            "{}={}".format(key, value)
            for key, value in self.__parameters.items())
        if params_str:
            return ";" + params_str
        return ""

    def __hash__(self):
        return hash(self.__values) ^ self.__parameters_hash

    def __eq__(self, other):
        return ((self.__values, self.__q, self.__parameters) ==
                (other.__values, other.__q, other.__parameters))

    def __ne__(self, other):
        return not (self == other)

    def __repr__(self):
        return ("{type!s}({values}, q={q!r}, "
                         "parameters={parameters!r})".format(
                             type=type(self).__name__,
                             values=", ".join(map(repr, self.values)),
                             q=self.q,
                             parameters=self.parameters))

    @classmethod
    def _values_match(cls, my_values, other_values):
        """
        The function to use for matching the tuple values. Usually, this is the
        wildcard-aware :func:`match_tuple` function.
        """
        return match_tuple(my_values, other_values)

    def rfc_match(self, server):
        """
        Matches a client preference (*self*) against a server preference
        (*server*).

        The order matters; extra parameter keys missing in the client preference
        are fatal (leading to a mismatch), while extra parameter keys in the
        server preference can be ignored.

        Return a tuple ``(matched, key)``. *matched* is a boolean value which is
        :data:`True` on a match and :data:`False` otherwise. If *matched* is
        true, *key* is a tuple which can be used to compare matches against each
        other. If *matched* is false, *key* is an unspecified value which should
        not be used.
        """

        matches, wildcard_penalty = self._values_match(
            self.values,
            server.values)

        # print("{!s} <-> {!s}: {} {}".format(
        #     self, server, matches, wildcard_penalty))

        if not matches:
            return False, ()

        my_keys = frozenset(self.parameters.keys())
        server_keys = frozenset(server.parameters.keys())

        if my_keys - server_keys:
            return False, ()

        common_keys = my_keys & server_keys
        for key in common_keys:
            if self.parameters[key] != server.parameters[key]:
                return False, ()
        specifity = len(common_keys)

        skipped_keys = server_keys - my_keys

        return True, (-wildcard_penalty, specifity, -len(skipped_keys))

class CharsetPreference(AbstractPreference):
    """
    Hold a character set preference for the character set *charset*. *charset*
    may be :data:`None` to designate a wildcard. Otherwise, it will be
    normalized through :func:`teapot.mime.normalize_charset`.

    .. attribute:: value

       The character set for which this object represents a preference.

    """

    def __init__(self, charset, q=1.0, parameters={}):
        if charset == "*" or charset is None:
            charset = None
        else:
            charset = mime.normalize_charset(charset)
        super().__init__(charset, q=q, parameters=parameters)

    @classmethod
    def parse(cls, s, drop_parameters=False):
        value, q, parameters = cls._parse_parameters(s)
        if drop_parameters:
            parameters = {}

        try:
            return cls(value, q=q, parameters=parameters)
        except LookupError as err:
            raise ValueError(str(err)) from None

    def __str__(self):
        return "{};q={}{}".format(
            self.values[0],
            self.q,
            self._format_parameters())

    @property
    def value(self):
        return self.values[0]

class LanguagePreference(AbstractPreference):
    """
    A preference for an ISO designator of language. The main language
    (e.g. ``en``) is given in *lang* and the variant (e.g. ``gb``) is given in
    *variant*.

    .. warning::

       Despite ISO designators are usually upper-case in the variant, it is
       expected that the *variant* argument is lower-case.

       This is enforced when parsing, but not when passing the argument to the
       constructor directly.

    """

    def __init__(self, lang, variant, *, q=1.0, parameters={}):
        if parameters:
            raise ValueError("Parameters not supported for languages")

        super().__init__(lang, variant, q=q, parameters=parameters)

    @classmethod
    def parse(cls, s, drop_parameters=False):
        parsed = cls._simple_parse(s, "-")
        values, q, parameters = parsed
        if len(values) == 1:
            values = values[0], None
        try:
            lang, variant = values
        except ValueError:
            values, *_ = parsed
            raise ValueError("Not a valid lanugage: {!r}".format(
                "-".join(values)))

        if drop_parameters:
            parameters = {}

        try:
            return cls(lang, variant, q=q, parameters=parameters)
        except LookupError as err:
            raise ValueError(str(err)) from None

    def __str__(self):
        return "{};q={}{}".format(
            "-".join(value for value in self.values if value),
            self.q,
            self._format_parameters())

    @property
    def value(self):
        return "-".join(value for value in self.values if value)

    @classmethod
    def _values_match(cls, my_values, other_values):
        return match_tuple(my_values, other_values,
                           rhs_wildcard=False)


class MIMEPreference(AbstractPreference):
    """
    Represent a content type preference for the MIME type
    *supertype*/*subtype*.
    """

    def __init__(self, supertype, subtype, *, q=1.0, parameters={}):
        super().__init__(supertype, subtype, q=q, parameters=parameters)

    @classmethod
    def parse(cls, s, drop_parameters=False):
        parsed = cls._simple_parse(s, "/")
        try:
            (supertype, subtype), q, parameters = parsed
        except ValueError:
            values, *_ = parsed
            raise ValueError("Not a valid MIME type: {!r}".format(
                "/".join(values)))

        return cls(supertype, subtype, q=q, parameters=parameters)

    def __str__(self):
        return "{};q={}{}".format(
            "/".join(value or "*" for value in self.values),
            self.q,
            self._format_parameters())

    @property
    def value(self):
        return "/".join(value or "*" for value in self.values)


class AbstractPreferenceList(metaclass=abc.ABCMeta):
    """
    Holds a list of descendants *cls* of :class:`AbstractPreference` objects and
    provides a bunch of useful operations.

    For each preference type, there is a subclass of this class to offer
    specialized services:

    * :class:`MIMEPreferenceList` for :class:`MIMEPreference` values
    * :class:`CharsetPreferenceList` for :class:`CharsetPreference` values
    * :class:`LanguagePreferenceList` for :class:`LanguagePreference` values

    .. warning::

       If dealing with :class:`CharsetPreferenceList`, make sure to call the
       :meth:`CharsetPreferenceList.inject_rfc_values` method correctly!

    .. note::

       Although possible, this class is not meant for direct instanciation. In
       the future, it might be impossible to instanciate it directly.

    """

    def __init__(self, cls, items=[]):
        super().__init__()
        self._items = list(items)
        self.cls = cls

    def __iter__(self):
        return iter(self._items)

    def __len__(self):
        return len(self._items)

    def append_header(self, header, drop_parameters=False):
        """
        Append a comma separated list of preference definitions from *header*
        into the current list. If *drop_parameters* is true, parameter suffixes
        (except for ``q``) are ignored and dropped.

        If any element from *header* fails to parse, a message is logged as
        warning and the element is skipped.
        """
        if not header:
            return

        for section in header.split(","):
            try:
                item = self.cls.parse(section, drop_parameters=drop_parameters)
            except ValueError as err:
                logger.warn("dropped malformed %s: %r (%s)",
                            str(self.cls),
                            section,
                            err)
                continue

            self._items.append(item)

    def get_candidates(self, server_preferences):
        """
        Match the client side preferences in this list against the given list of
        server side preferences.

        Return an descendingly sorted list of tuples ``(q, pref)``, where *q* is
        the quality of the match and *pref* is the preference object from
        *server_preferences* which has been matched.
        """
        self._items.sort(key=lambda x: x.specifity,
                         reverse=True)

        results = []
        for server_pref in server_preferences:
            candidates = []
            for client_pref in self._items:
                matched, sort_key = client_pref.rfc_match(server_pref)

                # print("{!s} <-> {!s}: {} {}".format(
                #     client_pref, server_pref,
                #     matched, sort_key))
                if not matched:
                    continue

                candidates.append((sort_key, client_pref.q))

            # print("{!s} -> {!s}".format(
            #     server_pref,
            #     candidates))

            if not candidates:
                best_q = 0
                sort_key = 0, 0, 0
            else:
                candidates.sort(key=lambda x: x[0],
                                reverse=True)
                sort_key, best_q = candidates[0]

            results.append(((best_q, sort_key), server_pref))

        results.sort(key=lambda x: x[0])

        results = [
            (q, server_pref)
            for (q, _), server_pref in results]

        return results

    def get_sorted_by_preference(self):
        """
        Return a sorted list of preferences from this list, ordered by a tuple
        of ``(wildcards, q, len(parameters))``, where *wildcards* is the amount
        of wildcards in the preference and *parameters* is the dictionary
        holding the parameters.
        """
        return sorted(
            self,
            key=lambda x: (x.wildcards, x.q, len(x.parameters)),
            reverse=True)

    def get_quality(self, server_preference):
        """
        Return the quality of the best match obtained when using only
        *server_preference* as preferences in :meth:`get_candidates`.
        """
        candidates = self.get_candidates([server_preference])
        return candidates.pop()[0]

    def best_match(self, server_preferences):
        """
        Return the best preference from *server_preferences* to match the
        clients wishes.
        """
        candidates = self.get_candidates(server_preferences)
        return candidates.pop()[1]

class CharsetPreferenceList(AbstractPreferenceList):
    def __init__(self, *args):
        super().__init__(CharsetPreference, *args)

    def inject_rfc_values(self):
        """
        This method **must** be called after all header values have been parsed
        with :meth:`append_header` to achieve full compliance with the RFC.

        This inserts a ``*`` preference if no values are present and a
        ``iso-8859-1;q=1.0`` preference if no ``*`` preference and no
        `iso-8859-1`` is present.
        """
        if not self._items:
            self._items.append(CharsetPreference("*", 1.0))
        else:
            charsets = [pref.values[0] for pref in self._items]
            if (not any(charset is None for charset in charsets) and
                not any(charset == "iso8859-1" for charset in charsets)):

                self._items.append(CharsetPreference("iso8859-1"))

class LanguagePreferenceList(AbstractPreferenceList):
    def __init__(self, *args):
        super().__init__(LanguagePreference, *args)

class MIMEPreferenceList(AbstractPreferenceList):
    def __init__(self, *args):
        super().__init__(MIMEPreference, *args)


def all_content_types():
    return MIMEPreferenceList([
        MIMEPreference("*", "*", q=1.0)
    ])

def all_languages():
    return LanguagePreferenceList([
        LanguagePreference("*", "*", q=1.0)
    ])

def all_charsets():
    return CharsetPreferenceList([
        CharsetPreference("*", q=1.0)
    ])
