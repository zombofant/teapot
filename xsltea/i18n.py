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

    Localizer objects are callable; calling a localizer will do something sane
    with the value, if it knows something sane to do (and :class:`TypeError`
    otherwise). Date/time values are passed to the according babel formatter, as
    well as numbers (as we cannot distinguish between currency, percent and
    plain numbers, plain numbers are assumed). Strings are passed to
    :meth:`gettext`.
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

    def __init__(self, locale, text_source_chain):
        if not text_source_chain:
            raise ValueError("At least one source must be given")

        self._locale = locale
        self._locale_str = teapot.accept.format_locale(locale)
        self._text_source_chain = tuple(text_source_chain)

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

        self._map_functions(babel.dates, self.DATES_FUNCTIONS)
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
    def __init__(self, text_dict, fallback=None):
        super().__init__()
        self.texts = text_dict

    def gettext(self, key):
        return self.texts[key]


class TextDatabaseFallback(TextSource):
    def __init__(self, fallback_mode):
        super().__init__()
        self.fallback_mode = fallback_mode

    @property
    def fallback_mode(self):
        return self._fallback_mode

    @fallback_mode.setter
    def fallback_mode(self, value):
        if value == "error":
            self.gettext = self._gettext_error
        elif value == "key":
            self.gettext = self._gettext_key
        else:
            raise ValueError("Unknown fallback mode: {!r}".format(
                value))

        self._fallback_mode = value

    def _gettext_error(self, key):
        raise self.lookup_error(key)

    def _gettext_key(self, key):
        return key

    def gettext(self, key):
        # this method is substituted with the correct handler on initialization
        # time
        assert False


def _get_localizer(textdb, locale):
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

    return Localizer(locale, text_source_chain)


class TextDatabase:
    """
    A container to hold various :class:`TextSource` instances. Specific
    localizers for a given *locale* can be obtained by calling
    :meth:`get_localizer`.

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

    :class:`TextDatabase` support dictionary-like access for locales, both in
    string format (e.g. ``de-at`` or ``en``) and tuple format
    (e.g. ``('de', 'at')``, ``('de', None)``). That is, subscript operators (for
    getting, setting and deleting) as well as the ``in`` operator are
    supported. Iteration is supported as well, yielding all explicitly supported
    locales in tuple format. The iteration order is unspecified, but grouped
    (that is, all variants of a locale appear together).

    .. attribute:: fallback_locale

       The locale (in tuple notation) which is always included as the
       second-last source when constructing localizers. This can be set to
       :data:`None` (to disable this feature).

       Writing to this attribute invalidates the :meth:`get_localizer` cache.

    .. attribute:: fallback_handler

       A :class:`TextSource` object which is always added as last source to the
       text sources when constructing a localizer. Must not be set to
       :data:`None`.
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
        return self._fallback_locale

    @fallback_locale.setter
    def fallback_locale(self, value):
        self._fallback_locale = self._mapkey(value)
        self._clear_caches()

    @property
    def fallback_handler(self):
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

    def get_localizer(self, locale):
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
        """

        return self._cached_get_localizer(self._mapkey(locale))

    def get_localizer_by_client_preference(self, client_preferences):
        candidates = client_preferences.get_candidates(
            self.get_preference_list())

        best_pref = candidates.pop()[1]
        return self.get_localizer(best_pref.values)

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

        catalog = Catalog(for_locale, sourcefile, fallback=fallback)
        self[for_locale] = catalog


class I18NProcessor(xsltea.processor.TemplateProcessor):
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
            (str(self.xmlns), "date"): [
                functools.partial(
                    self.handle_elem_type,
                    "date")],
            (str(self.xmlns), "datetime"): [
                functools.partial(
                    self.handle_elem_type,
                    "datetime")],
            (str(self.xmlns), "time"): [
                functools.partial(
                    self.handle_elem_type,
                    "time")],
            (str(self.xmlns), "timedelta"): [
                functools.partial(
                    self.handle_elem_type,
                    "timedelta")],
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

        lookup_result = ast.Call(
            ast.Attribute(
                self._access_var(template, ast.Load(), sourceline),
                type_,
                ast.Load(),
                lineno=sourceline,
                col_offset=0),
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

        valuecode = self._lookup_type(template, value, "_", sourceline)

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
                    "Unexpected attribute on i18n:text: {} "
                    "(in namespace {})".format(
                        name, ns),
                    context,
                    sourceline)

        elemcode = [
            template.ast_yield(
                self._lookup_type(template, elem.text, "_", sourceline, attrs),
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

    def provide_vars(self, template, tree, context):
        textdb_key = template.store(self._textdb)
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
                    ast.Attribute(
                        template.ast_get_stored(
                            textdb_key,
                            0),
                        "catalog_by_preference",
                        ast.Load(),
                        lineno=0,
                        col_offset=0),
                    [
                        ast.Attribute(
                            template.ast_get_request(0),
                            "accept_language",
                            ast.Load(),
                            lineno=0,
                            col_offset=0)
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
