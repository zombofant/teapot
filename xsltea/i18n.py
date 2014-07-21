"""
``xsltea.i18n`` — Internationalization services
###############################################

This module provides support classes for implementing internationalization as
well as a ready-to-use :mod:`gettext` and :mod:`babel` interface.

To get started, you need a :class:`TextDatabase` object which stores the text
sources you have. Text sources are commonly :class:`DictLookup` sources, which
take a dictionary and perform text lookups in that dictionary, or
:class:`GNUCatalog` sources, which use :mod:`gettext` to provide translated
texts.

Example
=======

Take the following as an example on how to use this module, given that `loader`
is a :class:`xsltea.template.TemplateLoader`::

  # when talking about locales, we can either use string notation like below,
  # or tuple notation, like ("en", "GB"). Case doesn’t matter.
  textdb = TextDatabase(fallback_locale="en_GB")

  # to add sources, just assign them to the corresponding locale slot
  textdb["en"] = DictLookup({
      "color": "colour"
  })
  # this is legal too
  textdb["en", "gb"] = textdb["en"]
  textdb["en", "us"] = DictLookup({
      "color": "color"
  })


  # we could obtain a localizer now to do some lookups or formatting
  localizer = textdb.get_localizer(("en", "us"))
  assert localizer.gettext("color") == "color"

  # de_DE is not in the db, so it will default to en_GB
  localizer = textdb.get_localizer(("de", "de"))
  assert localizer.gettext("color") == "colour"
  # nevertheless, dates and such will be formatted with german locale
  localizer.format_datetime(datetime.datetime.utcnow())  # yields german date


  # a processor for a loader is initialized as simple as this
  loader.add_processor(I18NProcessor(textdb))

Text sources
============

.. autoclass:: DictLookup
   :members: gettext

.. autoclass:: GNUCatalog

Text database
=============

.. autoclass:: TextDatabase
   :members:

Making use of localization sources
==================================

The :class:`TextDatabase` (above) provides you with an interface for acquiring a
:class:`Localizer` instance for a given locale, which then makes use of all
sources available for that locale to provide awesome internationalization.

.. autoclass:: Localizer
   :members:

Internationalization processor
==============================

.. autoclass:: I18NProcessor

Customizing internationalization support
========================================

Implementing custom text sources
--------------------------------

To implement custom text sources, it is recommended (although not required) to
subclass the :class:`TextSource` class.

.. autoclass:: TextSource
   :members:

.. autoclass:: TextDatabaseFallback
   :members:


"""

import abc
import ast
import functools
import gettext
import logging
import numbers
import os

from datetime import datetime, date, time, timedelta

import babel
import babel.dates
import babel.numbers

import teapot.accept

import xsltea.template
import xsltea.processor
import xsltea.exec

from xsltea.namespaces import NamespaceMeta

logger = logging.getLogger(__name__)

class Localizer:
    """
    A :class:`Localizer` is a convenience object to provide general
    internationalization utilities for a specific *locale* (in tuple notation,
    e.g. ``('en', 'gb')`` or ``('en', None)``). Texts are sourced from the
    sources provided in *text_source_chain*. The first source to be able to
    provide a translation wins. If no source is able to provide a translation,
    the error of the last source is raised. At least one source must be given.

    If the given *locale* is not known to :mod:`babel`, a :class:`ValueError` is
    raised upon construction.

    In addition to the documented functions, each :class:`Localizer` instance
    also has all formatting and introspection functions from the
    :mod:`babel.dates` and :mod:`babel.numbers` modules. Their *locale*
    parameter is pinned to the locale of this object.

    If the *timezone* argument is not :data:`None`, it must be a valid timezone
    for :class:`datetime.datetime` objects. All :class:`datetime.datetime`
    objects will be translated into that timezone before printing. If the
    objects have no timezone assigned, they are assumed to be UTC.

    Localizer objects are callable; calling a localizer will do something sane
    with the value, if it knows something sane to do (and :class:`TypeError`
    otherwise). Date/time values are passed to the according babel formatter, as
    well as numbers (as we cannot distinguish between currency, percent and
    plain numbers, plain numbers are assumed). Strings are passed to
    :meth:`gettext`.

    .. note::

       Generally, it is tedious to create a :class:`Localizer` instance, which
       is why you should use a :class:`TextDatabase` to do so.

    """

    NUMBERS_FUNCTIONS = [
        funcname
        for funcname in dir(babel.numbers)
        if funcname.startswith("format_") or funcname.startswith("get_")
    ]
    DATES_FUNCTIONS = [
        funcname
        for funcname in dir(babel.dates)
        if funcname.startswith("format_") or funcname.startswith("get_")
    ]

    def _map_functions(self, from_module, namelist):
        for name in namelist:
            obj = getattr(from_module, name)
            # safeguard against babel adding non-callable module members with
            # the name patterns from above here
            if not hasattr(obj, "__call__"):
                continue

            setattr(self, name, self.locale_ifyer(obj))

    def _map_datetimes(self, from_module, namelist):
        if self.timezone is not None:
            def wrap(func):
                @functools.wraps(func)
                def wrapper(value, *args, **kwargs):
                    if hasattr(value, "tzinfo"):
                        value = self.to_timezone(value)
                    return func(value, *args, **kwargs)
                return wrapper
        else:
            def wrap(func):
                return func

        for name in namelist:
            obj = getattr(from_module, name)
            # safeguard against babel adding non-callable module members with
            # the name patterns from above here
            if not hasattr(obj, "__call__"):
                continue

            setattr(self, name, self.locale_ifyer(wrap(obj)))

    def __init__(self, locale, text_source_chain, timezone=None):
        if not text_source_chain:
            raise ValueError("At least one source must be given")

        self._locale = locale
        self._locale_str = teapot.accept.format_locale(locale)
        self._text_source_chain = tuple(text_source_chain)
        self._timezone = timezone

        babel_locale_str = self._locale_str
        try:
            babel.numbers.format_number(1, locale=babel_locale_str)
        except babel.core.UnknownLocaleError:
            babel_locale_str = teapot.accept.format_locale(
                locale[:1] + (None,))
            try:
                babel.numbers.format_number(1, locale=babel_locale_str)
            except babel.core.UnknownLocaleError:
                raise ValueError("Babel doesn’t know {}".format(
                    self._locale_str)) from None
            else:
                logger.warn("Using fallback locale for babel "
                            "(%s instead of %s)",
                            babel_locale_str,
                            self._locale_str)

        self.locale_ifyer = functools.partial(
            functools.partial,
            locale=babel_locale_str)

        self._map_datetimes(babel.dates, self.DATES_FUNCTIONS)
        self._map_functions(babel.numbers, self.NUMBERS_FUNCTIONS)

    def __hash__(self):
        return hash(self._locale) ^ hash(self._text_source_chain)

    def __eq__(self, other):
        if self._locale != other._locale:
            return False

        if len(self._text_source_chain) != len(other._text_source_chain):
            return False

        for my_source, other_source in zip(self._text_source_chain,
                                           other._text_source_chain):
            if my_source is not other_source:
                return False

        return True

    def __ne__(self, other):
        return not (self == other)

    @property
    def locale(self):
        """
        The locale, in tuple notation, served by this :class:`Localizer`.
        """
        return self._locale

    @property
    def text_sources(self):
        """
        The tuple of text sources (in the order they are checked).
        """
        return self._text_source_chain

    @property
    def timezone(self):
        """
        The timezone used to display dates and times.
        """
        return self._timezone

    def gettext(self, key):
        last_error = None
        for source in self._text_source_chain:
            try:
                return source.gettext(key)
            except LookupError as err:
                last_error = err
        else:
            raise last_error

    def ngettext(self, singular_key, plural_key, n):
        last_error = None
        for source in self._text_source_chain:
            try:
                return source.ngettext(singular_key, plural_key, n)
            except LookupError as err:
                last_error = err
        else:
            raise last_error

    def to_timezone(self, value):
        if not value.tzinfo:
            return self._timezone.fromutc(value)
        else:
            return value.astimezone(self._timezone)

    def __call__(self, value):
        if isinstance(value, numbers.Real):
            return self.format_number(value)
        elif isinstance(value, datetime):
            return self.format_datetime(value)
        elif isinstance(value, date):
            return self.format_date(value)
        elif isinstance(value, time):
            return self.format_time(value)
        elif isinstance(value, timedelta):
            return self.format_timedelta(value)
        elif isinstance(value, str):
            return self.gettext(value)
        else:
            raise TypeError("Unsupported type for magic call: {}".format(
                type(value)))

class TextSource(metaclass=abc.ABCMeta):
    """
    A text source provides direct translations and singular and plural strings,
    indexed by keys (which may be original text, thus the keys have no
    restrictions regarding characters occuring in the keys etc.).
    """

    @staticmethod
    def lookup_error(key):
        return LookupError(key)

    @abc.abstractmethod
    def gettext(self, key):
        """
        Return the translation keyed by *key*.
        """

        raise self.lookup_error(key)

    def ngettext(self, singular_key, plural_key, n):
        """
        Return the translation of *singular_key* if *n* equals 1 and the
        translation of *plural_key* otherwise. By default, this method delegates
        to :meth:`gettext`, so the same implications apply.
        """

        return self.gettext(singular_key if n == 1 else plural_key)


class GNUCatalog(TextSource):
    """
    Provide a translator sourcing the strings from a GNU :mod:`gettext`
    file. The translator will advertise the given *locale* and load strings from
    *sourcefile*.
    """

    class RaisingFallback:
        """
        This is a helper class which can be used to throw if a :mod:`gettext`
        lookup fails (instead of returning the key).
        """

        def gettext(self, key):
            raise TextSource.lookup_error(key)

        def ngettext(self, singular_key, plural_key, n):
            raise TextSource.lookup_error(
                singular_key if n == 1 else plural_key)

    def __init__(self, sourcefile):
        super().__init__()
        self.translations = gettext.GNUTranslations(sourcefile)
        self.translations.add_fallback(self.RaisingFallback())

    def gettext(self, key):
        result = self.translations.gettext(key)
        logger.debug("lookup: %s -> %s", key, result)
        return result

    def ngettext(self, singular, plural, n):
        return self.translations.ngettext(singular, plural, n)


class DictLookup(TextSource):
    """
    Use the given *text_dict* to initialize the :attr:`texts` attribute, from
    which lookups are sourced.

    .. attribute:: texts

       A mapping which maps translation keys to texts to translated strings.
    """

    def __init__(self, text_dict):
        super().__init__()
        self.texts = text_dict

    def gettext(self, key):
        """
        Return the *key* from the :attr:`texts` dictionary, or raise
        :class:`KeyError` if the key is not available.
        """
        return self.texts[key]


class TextDatabaseFallback(TextSource):
    """
    This fallback is a fake text source whose behaviour depends on the *mode*
    attribute value.

    By default, the :class:`TextDatabase` uses a :class:`TextDatabaseFallback`
    object as the last source when creating a :class:`Localizer`, so that the
    *mode* of the fallback governs the result of any failed lookup in any
    localizer created by the :class:`TextDatabase`.
    """
    def __init__(self, mode):
        super().__init__()
        self.mode = mode

    @property
    def mode(self):
        """
        This attribute can take one of the following values:

        * ``"error"``: Each lookup will throw :class:`LookupError`, with the *key*
          looked up as the only argument.
        * ``"key"``: Return the *key* looked up as the value. This is equivalent to
          using plain :mod:`gettext`.

        Attempting to assign a different value will raise a :class:`ValueError`.
        """
        return self._mode

    @mode.setter
    def mode(self, value):
        if value == "error":
            self.gettext = self._gettext_error
        elif value == "key":
            self.gettext = self._gettext_key
        else:
            raise ValueError("Unknown fallback mode: {!r}".format(
                value))

        self._mode = value

    def _gettext_error(self, key):
        raise self.lookup_error(key)

    def _gettext_key(self, key):
        return key

    def gettext(self, key):
        # this method is substituted with the correct handler on initialization
        # time
        assert False


def _get_localizer(textdb, locale, timezone):
    """
    .. warning::

       Do not call this directly. This is the outsourced implementation of
       :meth:`TextDatabase.get_localizer`. The actual implementation on
       :class:`TextDatabase` objects is equipped with a cache.

    """

    text_source_chain = []
    try:
        text_source_chain.append(textdb[locale])
    except KeyError:
        pass

    if locale[1] is not None:
        try:
            text_source_chain.append(textdb[(locale[0], None)])
        except KeyError:
            pass

    fallback_locale = textdb.fallback_locale
    if (    fallback_locale is not None and
            locale != fallback_locale):
        try:
            text_source_chain.append(textdb[fallback_locale])
        except KeyError as err:
            logger.warn("fallback locale %s not available",
                        fallback_locale)

    text_source_chain.append(textdb._fallback_handler)

    return Localizer(locale, text_source_chain,
                     timezone=timezone)


class TextDatabase:
    """
    The text database provides a mapping from locales to text sources. It
    provides an interface (:meth:`get_localizer`) to obtain a :class:`Localizer`
    instance for a given locale.

    The *fallback_locale* argument provides the initial value for the
    :attr:`fallback_locale` attribute. *fallback_mode* can either be a string,
    which is then passed to the constructor of :class:`TextDatabaseFallback` to
    initialize the :attr:`fallback_handler` attribute, or a :class:`TextSource`
    object which used as initial value for the :attr:`fallback_handler`
    attribute.

    *cache_size* is the maximum amount of :class:`Localizer` objects which are
    cached. If set to :data:`None`, the cache may grow indefinitely, which is
    not recommended if untrusted input can cause :class:`Localizer` classes to
    be created (e.g. ``Accept-Language`` HTTP headers). To disable caching
    altogether, set *cache_size* to a non-positive number (e.g. ``0``).

    The cache is automatically cleared when the :class:`TextDatabase` is altered
    in any relevant way.

    :class:`TextDatabase` support dictionary-like access for locales, both in
    string format (e.g. ``de-at`` or ``en``) and tuple format
    (e.g. ``('de', 'at')``, ``('de', None)``). That is, subscript operators (for
    getting, setting and deleting) as well as the ``in`` operator are
    supported. Iteration is supported as well, yielding all explicitly supported
    locales in tuple format. The iteration order is unspecified, but grouped
    (that is, all variants of a locale appear together).
    """

    def __init__(self, fallback_locale, fallback_mode="error", cache_size=32):
        super().__init__()
        self._source_tree = {}
        self._cached_get_localizer = functools.partial(_get_localizer, self)
        if cache_size is None or cache_size > 0:
            # only apply lru_cache if a cache is requested
            self._cached_get_localizer = functools.lru_cache(
                maxsize=cache_size
            )(
                self._cached_get_localizer
            )

        self.fallback_handler = TextDatabaseFallback(fallback_mode)
        self.fallback_locale = fallback_locale

        self._preferences_cache = None

    def _clear_caches(self):
        try:
            self._cached_get_localizer.cache_clear()
        except AttributeError:
            # this happens if cache_size=0
            pass

        self._preferences_cache = None

    @property
    def fallback_locale(self):
        """
        The locale (in tuple notation) which is always included as the
        second-last source when constructing localizers. This can be set to
        :data:`None` (to disable this feature).

        Writing to this attribute invalidates the :meth:`get_localizer` cache.
        """
        return self._fallback_locale

    @fallback_locale.setter
    def fallback_locale(self, value):
        self._fallback_locale = self._mapkey(value)
        self._clear_caches()

    @property
    def fallback_handler(self):
        """
        A :class:`TextSource` object which is always added as last source to the
        text sources when constructing a localizer. Must not be set to
        :data:`None`.
        """
        return self._fallback_handler

    @fallback_handler.setter
    def fallback_handler(self, handler):
        if handler is None:
            raise TypeError("fallback_handler must not be None")
        self._fallback_handler = handler
        self._clear_caches()

    def get_preference_list(self):
        if self._preferences_cache is not None:
            return self._preferences_cache

        self._preferences_cache = [
            teapot.accept.LanguagePreference(*item, q=1.0)
            for item in self
        ]
        return self._preferences_cache

    def _mapkey(self, locale):
        if isinstance(locale, str):
            return teapot.accept.parse_locale(locale)
        else:
            return tuple(None if value is None else value.lower()
                         for value in locale)

    def _get_text_source(self, locale):
        lang, variant = self._mapkey(locale)
        try:
            return self[lang, variant]
        except KeyError as err:
            try:
                return self[lang, None]
            except KeyError as err:
                if (lang, variant) != self._fallback_locale:
                    return self._get_text_source(self._fallback_locale)

    def __getitem__(self, locale):
        lang, variant = self._mapkey(locale)
        try:
            return self._source_tree.get(lang, {})[variant]
        except KeyError:
            raise KeyError((lang, variant)) from None

    def __setitem__(self, locale, text_source):
        lang, variant = self._mapkey(locale)
        self._source_tree.setdefault(lang, {})[variant] = text_source
        self._clear_caches()

    def __delitem__(self, locale):
        lang, variant = self._mapkey(locale)
        try:
            variants = self._source_tree[lang]
            try:
                del variants[variant]
            finally:
                if not variants:
                    del self._source_tree[lang]
        except KeyError:
            raise KeyError((lang, variant)) from None

        self._clear_caches()

    def __contains__(self, locale):
        lang, variant = self._mapkey(locale)
        try:
            self._source_tree[lang][variant]
        except KeyError:
            return False
        return True

    def __iter__(self):
        return (
            (lang, variant)
            for lang, variants in self._source_tree.items()
            for variant in variants.keys())

    def __len__(self):
        return sum(
            len(variants)
            for variants in self._source_tree.values())

    def get_localizer(self, locale, timezone=None):
        """
        Return a :class:`Localizer` for the given locale. The following sources
        are added to the localizer, in this order, and only if available.

        * ``self[locale]``: The source for the specific given locale
        * (if the variant of the locale is not :data:`None`)
          ``self[locale[0], None]``: The source for the base variant of the given
          locale
        * (if :attr:`fallback_locale` is not :data:`None` and *locale* is not
          equal to :attr:`fallback_locale`)
          ``self[self.fallback_locale]``: The source for the fallback locale
        * :attr:`fallback_handler`: The final handler

        As :class:`Localizer` objects are immutable, changes to the
        :class:`TextDatabase` do not affect it directly. However, changes to
        sources (e.g. changing the :attr:`TextDatabaseFallback.mode` attribute
        or adding texts) will affect living :class:`Localizer` objects. Adding
        or replacing texts sources will not affect already created
        :class:`Localizer` objects.

        The *timezone* argument is passed to the :class:`Localizer` constructor.
        """

        return self._cached_get_localizer(self._mapkey(locale),
                                          timezone=timezone)

    def get_localizer_by_client_preference(self, client_preferences,
                                           **kwargs):
        """
        Determine the best possible language from the *client_preferences* and
        the list of text sources available. The result of this is passed to
        :meth:`get_localizer`, along with the *kwargs*, to create and return a
        new :class:`Localizer`.
        """

        if len(self):
            candidates = client_preferences.get_candidates(
                self.get_preference_list())

            locale = candidates.pop()[1].values
        else:
            try:
                locale = client_preferences.get_sorted_by_preference()[0].values
            except IndexError:
                locale = self.fallback_locale

        return self.get_localizer(locale, **kwargs)

    def load_all(self, base_path):
        for filename in os.listdir(base_path):
            if not filename.endswith(".mo"):
                continue
            locale, _ = os.path.splitext(filename)
            locale = teapot.accept.parse_locale(locale)

            if locale == self._fallback_locale:
                continue

            with open(os.path.join(base_path, filename), "rb") as f:
                self.load_catalog(locale, f)

    def load_catalog(self, for_locale, sourcefile):
        for_locale = teapot.accept.parse_locale(for_locale)

        if for_locale in self:
            raise ValueError("Locale {} already loaded".format(
                "_".join(for_locale)))

        try:
            fallback = self.catalog_for_locale(self._fallback_locale).translations
        except KeyError:
            fallback = None

        catalog = GNUCatalog(for_locale, sourcefile, fallback=fallback)
        self[for_locale] = catalog


class I18NProcessor(xsltea.processor.TemplateProcessor):
    """
    Processor which allows the use of the *textdb* :class:`TextDatabase` object
    in XML templates.

    The following nodes are available:

    * ``i18n:_``: Is replaced with the text obtained from looking up the text
      content of the element via :meth:`Localizer.gettext` in the localizer from
      the current request.

      Any attributes are taken as key-value pairs for running :meth:`str.format`
      on the result of the lookup. Attributes in the ``exec:`` namespace are
      first interpreted according to the specified *safety_level* and then
      passed to :meth:`str.format`.

    * ``i18n:date``, ``i18n:datetime``, ``i18n:time``, ``i18n:timedelta``,
      ``i18n:number``: Format the respective datatype using the current
      :class:`Localizer` and replace the element with the formatted text. The
      value is obtained by interpreting the text as python code using the given
      *safety_level*.

    * ``i18n:any``: Calls the :class:`Localizer` instance itself with the value
      obtained from interpreting the element text as python code according to
      the current *safety_level*. Replaces the element with the text obtained
      from the call.

    * ``i18n:timezone``: Translate the timezone name of the given timezone or
      datetime object, using :func:`babel.dates.get_timezone_name`.

    * ``@i18n:*``: The contents of attributes in the ``i18n:`` namespace on
      arbitrary elements are taken as a key for a ``gettext`` lookup. The result
      is used as the new attribute value, with the namespace removed from the
      attribute.

    In addition to the node processing, the processor adds an attribute with
    the name *varname* to the ``context`` object in the template scope.

    The value of that attribute depends on the state of the ``request`` object:

    * if the request has an ``localizer`` attribute, its value is taken
    * otherwise, use the :attr:`teapot.request.Request.accept_language`
      attribute to negotiate a language.

      In that case, if the request has a ``timezone`` attribute, it will be used
      to specify the output timezone.

    The namespace of ``i18n:`` elements is
    ``https://xmlns.zombofant.net/xsltea/i18n``.
    """

    class xmlns(metaclass=NamespaceMeta):
        xmlns = "https://xmlns.zombofant.net/xsltea/i18n"

    def __init__(self, textdb,
                 safety_level=xsltea.safe.SafetyLevel.conservative,
                 varname="i18n",
                 **kwargs):
        super().__init__(**kwargs)

        self.attrhooks = {
            (str(self.xmlns), None): [self.handle_attr],
        }
        self.elemhooks = {
            (str(self.xmlns), "_"): [self.handle_elem],
            (str(self.xmlns), "any"): [
                functools.partial(
                    self.handle_elem_type,
                    None)],
            (str(self.xmlns), "timezone"): [
                functools.partial(
                    self.handle_elem_type,
                    "get_timezone_name")],
            (str(self.xmlns), "date"): [
                functools.partial(
                    self.handle_elem_type,
                    "format_date")],
            (str(self.xmlns), "datetime"): [
                functools.partial(
                    self.handle_elem_type,
                    "format_datetime")],
            (str(self.xmlns), "time"): [
                functools.partial(
                    self.handle_elem_type,
                    "format_time")],
            (str(self.xmlns), "timedelta"): [
                functools.partial(
                    self.handle_elem_type,
                    "format_timedelta")],
            (str(self.xmlns), "number"): [
                functools.partial(
                    self.handle_elem_type,
                    "format_number")],
        }
        self.globalhooks = [self.provide_vars]

        self._textdb = textdb
        self._varname = varname
        self._safety_level = safety_level

    def _access_var(self, template, ctx, sourceline):
        return template.ast_get_from_object(
            self._varname,
            "context",
            sourceline,
            ctx=ctx)

    def _lookup_type(self, template, key, type_, sourceline, attrs={}):
        lookup_key = template.ast_or_str(key, sourceline)

        attrs_dict = ast.Dict([], [], lineno=sourceline, col_offset=0)
        for key, value in attrs.items():
            attrs_dict.keys.append(
                ast.Str(
                    key,
                    lineno=sourceline,
                    col_offset=0))
            attrs_dict.values.append(value)

        to_call = self._access_var(template, ast.Load(), sourceline)

        if type_ is not None:
            to_call = ast.Attribute(
                to_call,
                type_,
                ast.Load(),
                lineno=sourceline,
                col_offset=0)

        lookup_result = ast.Call(
            to_call,
            [
                lookup_key
            ],
            [],
            None,
            None,
            lineno=sourceline,
            col_offset=0)

        if not attrs:
            return lookup_result

        return ast.Call(
            ast.Attribute(
                lookup_result,
                "format",
                ast.Load(),
                lineno=sourceline,
                col_offset=0),
            [],
            [],
            None,
            attrs_dict,
            lineno=sourceline,
            col_offset=0)

    def handle_attr(self, template, elem, key, value, context):
        sourceline = elem.sourceline or 0

        ns, name = xsltea.template.split_tag(key)

        keycode = ast.Str(
            name,
            lineno=sourceline,
            col_offset=0)

        valuecode = self._lookup_type(template, value, None, sourceline)

        return [], [], keycode, valuecode, []

    def handle_elem(self, template, elem, context, offset):
        sourceline = elem.sourceline or 0

        attrs = {}
        for key, value in elem.attrib.items():
            ns, name = xsltea.template.split_tag(key)
            if ns == str(xsltea.exec.ExecProcessor.xmlns):
                expr = compile(value,
                               context.filename,
                               "eval",
                               ast.PyCF_ONLY_AST).body
                self._safety_level.check_safety(expr)
                attrs[name] = expr
            elif ns is None:
                attrs[name] = ast.Str(
                    value,
                    lineno=sourceline,
                    col_offset=0)
            else:
                raise template.compilation_error(
                    "Unexpected attribute on i18n:_: {} "
                    "(in namespace {})".format(
                        name, ns),
                    context,
                    sourceline)

        elemcode = [
            template.ast_yield(
                self._lookup_type(template, elem.text,
                                  "gettext",
                                  sourceline, attrs),
                sourceline)
        ]
        elemcode.extend(template.preserve_tail_code(elem, context))

        return [], elemcode, []

    def handle_elem_type(self, type_, template, elem, context, offset):
        sourceline = elem.sourceline or 0

        key_code = compile(
            elem.text,
            context.filename,
            "eval",
            ast.PyCF_ONLY_AST).body
        self._safety_level.check_safety(key_code)

        elemcode = template.preserve_tail_code(elem, context)
        elemcode.insert(
            0,
            template.ast_yield(
                self._lookup_type(template, key_code, type_, sourceline),
                sourceline)
        )

        return [], elemcode, []

    def negotiate_language(self, request):
        if hasattr(request, "localizer") and request.localizer is not None:
            return request.localizer

        if hasattr(request, "timezone"):
            timezone = request.timezone
        else:
            timezone = pytz.UTC

        return self._textdb.get_localizer_by_client_preference(
            request.accept_language,
            timezone=timezone)

    def provide_vars(self, template, tree, context):
        precode = [
            ast.Assign(
                [
                    ast.Attribute(
                        ast.Name(
                            "context",
                            ast.Load(),
                            lineno=0,
                            col_offset=0),
                        self._varname,
                        ast.Store(),
                        lineno=0,
                        col_offset=0),
                ],
                ast.Call(
                    template.ast_get_stored(
                        template.store(self.negotiate_language),
                        0),
                    [
                        template.ast_get_request(0),
                    ],
                    [],
                    None,
                    None,
                    lineno=0,
                    col_offset=0),
                lineno=0,
                col_offset=0)
        ]

        return precode, []
