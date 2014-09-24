import unittest

from datetime import date, time, datetime, timedelta

import teapot.accept

from . import i18n
from . import template
from . import exec
from . import safe
from . import errors

def simple_preflist(s):
    preflist = teapot.accept.LanguagePreferenceList()
    preflist.append_header(s)
    return preflist

class TestLocalizer(unittest.TestCase):
    def test_enforce_at_least_one_source(self):
        with self.assertRaises(ValueError):
            i18n.Localizer(("de", "de"), [])

    def test_enforce_valid_locale(self):
        items = [None]
        # ensure that it’s not the fault of the item list if this test passes
        i18n.Localizer(("de", "de"), items)
        with self.assertRaises(ValueError):
            i18n.Localizer(("foo", "bar"), items)

    def test_hashable(self):
        l = i18n.Localizer(("de", "de"), [None])
        hash(l)

    def test_equality(self):
        obj = object()
        l1 = i18n.Localizer(("de", "de"), [obj])
        l2 = i18n.Localizer(("de", "de"), [obj])
        self.assertEqual(l1, l2)
        l3 = i18n.Localizer(("en", "gb"), [None])
        self.assertNotEqual(l1, l3)
        self.assertNotEqual(l2, l3)

        l4 = i18n.Localizer(("de", "de"), [object()])
        self.assertNotEqual(l1, l4)
        self.assertNotEqual(l2, l4)

    def test_immutable_attributes(self):
        l = i18n.Localizer(("de", "de"), [None])
        self.assertEqual(
            l.locale,
            ("de", "de"))
        self.assertEqual(
            l.text_sources,
            (None,))

        with self.assertRaises(AttributeError):
            l.locale = l.locale

        with self.assertRaises(AttributeError):
            l.text_sources = l.text_sources

class TextDatabaseTest:
    def setUp(self):
        super().setUp()
        self.example_date = date(2014, 7, 6)
        self.example_time = time(16, 34, 56)
        self.example_datetime = datetime(2014, 7, 6, 12, 34, 56)
        self.example_timedelta = timedelta(days=3, minutes=4)
        textdb = i18n.TextDatabase(
            fallback_locale=("en", "gb"),
            cache_size=32
        )

        textdb["en"] = i18n.DictLookup(
            {
                "key": "english",
            })
        textdb["en", "gb"] = i18n.DictLookup(
            {
                "key": "british english",
                """foo <xml id='strong'>bar</xml> baz""": """FOO <xml id="strong">BAR</xml> BAZ"""
            })
        textdb["en", "us"] = i18n.DictLookup(
            {
                "key": "american english"
            })
        textdb["de"] = i18n.DictLookup(
            {
                "key": "deutsch"
            })
        textdb["de", "de"] = i18n.DictLookup(
            {
                "key": "deutsch (deutschland)"
            })

        self.textdb = textdb

class TestTextDatabase(TextDatabaseTest, unittest.TestCase):
    def test_cache(self):
        textdb = self.textdb
        localizer_base = textdb.get_localizer("de-de")
        keys = [
            "de_de",
            "de_DE",
            ("de", "de"),
            ("de", "DE"),
        ]

        for key in keys:
            self.assertIs(
                textdb.get_localizer(key),
                localizer_base,
                msg="uncached localizer returned for {}".format(key))

    def test_cache_zero(self):
        textdb = i18n.TextDatabase("de", cache_size=0)
        textdb["de"] = i18n.DictLookup({})
        localizer1 = textdb.get_localizer("de-de")
        localizer2 = textdb.get_localizer("de-de")

        self.assertIsNot(
            localizer1,
            localizer2)

        # make sure that no errors occur due to missing lru_cache decoration
        textdb.fallback_locale = "en"

    def test_cache_invalidation___delitem__(self):
        textdb = self.textdb
        localizer1 = textdb.get_localizer("de-de")
        del textdb["de", "de"]
        localizer2 = textdb.get_localizer("de-de")

        self.assertEqual(
            localizer1.gettext("key"),
            "deutsch (deutschland)")

        self.assertEqual(
            localizer2.gettext("key"),
            "deutsch")

    def test_cache_invalidation___setitem__(self):
        textdb = self.textdb
        localizer1 = textdb.get_localizer("de-at")
        textdb["de", "at"] = i18n.DictLookup(
            {
                "key": "deutsch (österreich)"
            })
        localizer2 = textdb.get_localizer("de-at")

        self.assertEqual(
            localizer1.gettext("key"),
            "deutsch")

        self.assertEqual(
            localizer2.gettext("key"),
            "deutsch (österreich)")

    def test_cache_invalidation_set_fallback_locale(self):
        textdb = self.textdb
        localizer1 = textdb.get_localizer("sv")
        textdb.fallback_locale = "de"
        localizer2 = textdb.get_localizer("sv")

        self.assertEqual(
            localizer1.gettext("key"),
            "british english")

        self.assertEqual(
            localizer2.gettext("key"),
            "deutsch")

    def test_cache_invalidation_set_fallback_handler(self):
        textdb = self.textdb
        localizer1 = textdb.get_localizer("sv")
        textdb.fallback_handler = i18n.TextDatabaseFallback("key")
        localizer2 = textdb.get_localizer("sv")

        with self.assertRaises(LookupError):
            localizer1.gettext("fall back")

        self.assertEqual(
            localizer2.gettext("fall back"),
            "fall back")

    def test_get_localizer(self):
        textdb = self.textdb
        localizer = textdb.get_localizer("de-de")
        self.assertEqual(
            localizer.gettext("key"),
            "deutsch (deutschland)")
        self.assertEqual(
            localizer("key"),
            "deutsch (deutschland)")
        self.assertEqual(
            localizer(1234.56),
            "1.234,56")
        self.assertEqual(
            localizer(self.example_date),
            "06.07.2014")
        self.assertEqual(
            localizer(self.example_time),
            "16:34:56")
        self.assertEqual(
            localizer(self.example_datetime),
            "06.07.2014 12:34:56")
        self.assertEqual(
            localizer(self.example_timedelta),
            "3 Tage")

        localizer = textdb.get_localizer("de_at")
        self.assertEqual(
            localizer.gettext("key"),
            "deutsch")

        localizer = textdb.get_localizer("en_AU")
        self.assertEqual(
            localizer.gettext("key"),
            "english")

        localizer = textdb.get_localizer(("en", "gb"))
        self.assertEqual(
            localizer.gettext("key"),
            "british english")

    def test_set_fallback_handler(self):
        textdb = self.textdb
        with self.assertRaises(TypeError):
            textdb.fallback_handler = None

    def test_get_localizer_by_preference(self):
        textdb = self.textdb
        self.assertEqual(
            textdb.get_localizer_by_client_preference(
                simple_preflist("de;q=1.0,en;q=0.9")
            ).locale,
            ("de", None))

        self.assertEqual(
            textdb.get_localizer_by_client_preference(
                simple_preflist("de-at;q=1.0,en;q=0.9")
            ).locale,
            ("en", None))

class TestI18NProcessor(TextDatabaseTest, unittest.TestCase):
    xmlsrc_gettext = """<?xml version="1.0" ?>
<test xmlns:exec="https://xmlns.zombofant.net/xsltea/exec"
      xmlns:i18n="https://xmlns.zombofant.net/xsltea/i18n"
    ><i18n:_>key</i18n:_></test>"""

    xmlsrc_gettext_invalid_key = """<?xml version="1.0" ?>
<test xmlns:exec="https://xmlns.zombofant.net/xsltea/exec"
      xmlns:i18n="https://xmlns.zombofant.net/xsltea/i18n"
    ><i18n:_>wrong key</i18n:_></test>"""

    xmlsrc_magic = """<?xml version="1.0" ?>
<test xmlns:exec="https://xmlns.zombofant.net/xsltea/exec"
      xmlns:i18n="https://xmlns.zombofant.net/xsltea/i18n"
    ><i18n:any>arguments['value']</i18n:any></test>"""

    xmlsrc_with_markup = """<?xml version="1.0" ?>
<test xmlns:exec="https://xmlns.zombofant.net/xsltea/exec"
      xmlns:i18n="https://xmlns.zombofant.net/xsltea/i18n"
    ><i18n:_>foo <strong i18n:id="strong">bar</strong> baz</i18n:_></test>"""

    def setUp(self):
        super().setUp()
        self._loader = template.XMLTemplateLoader()
        self._loader.add_processor(exec.ExecProcessor)
        self._loader.add_processor(i18n.I18NProcessor(
            self.textdb,
            safety_level=safe.SafetyLevel.unsafe))

    def _load_xml(self, xmlstr):
        template = self._loader.load_template(xmlstr, "<string>")
        return template

    def _process_xml(self, xmlstr,
                     accept_language="en-gb;q=1.0",
                     **arguments):
        accept_language_list = teapot.accept.LanguagePreferenceList()
        accept_language_list.append_header(accept_language)
        template = self._load_xml(xmlstr)
        return template.process(
            arguments,
            request=teapot.request.Request(
                accept_info=(
                    teapot.accept.all_content_types(),
                    accept_language_list,
                    teapot.accept.all_charsets()
                )))

    def test_gettext(self):
        tree = self._process_xml(self.xmlsrc_gettext)
        self.assertEqual(
            tree.getroot().text,
            "british english")

    def test_gettext_with_invalid_key(self):
        with self.assertRaises(errors.TemplateEvaluationError) as ctx:
            self._process_xml(self.xmlsrc_gettext_invalid_key)

        self.assertIsInstance(
            ctx.exception.__context__,
            LookupError)

    def test_gettext_with_markup(self):
        tree = self._process_xml(self.xmlsrc_with_markup)
        self.assertEqual(
            tree.getroot().text,
            "FOO ")
        self.assertEqual(
            tree.getroot()[0].text,
            "BAR")
        self.assertEqual(
            tree.getroot()[0].tail,
            " BAZ")

    def test_magic_key(self):
        tree = self._process_xml(
            self.xmlsrc_magic,
            value="key")
        self.assertEqual(
            tree.getroot().text,
            "british english")

    def test_magic_date(self):
        tree = self._process_xml(
            self.xmlsrc_magic,
            value=self.example_date)
        self.assertEqual(
            tree.getroot().text,
            "6 Jul 2014")

    def test_magic_datetime(self):
        tree = self._process_xml(
            self.xmlsrc_magic,
            value=self.example_datetime)
        self.assertEqual(
            tree.getroot().text,
            "6 Jul 2014 12:34:56")

    def test_magic_time(self):
        tree = self._process_xml(
            self.xmlsrc_magic,
            value=self.example_time)
        self.assertEqual(
            tree.getroot().text,
            "16:34:56")

    def test_magic_number(self):
        tree = self._process_xml(
            self.xmlsrc_magic,
            value=12345.67)
        self.assertEqual(
            tree.getroot().text,
            "12,345.67")

    def test_use_localizer_attribute(self):
        accept_language_list = teapot.accept.LanguagePreferenceList()
        accept_language_list.append_header("en-gb;q=1.0")
        template = self._load_xml(self.xmlsrc_gettext)
        request = teapot.request.Request(
            accept_info=(
                teapot.accept.all_content_types(),
                accept_language_list,
                teapot.accept.all_charsets()
            ))
        request.localizer = self.textdb.get_localizer(("de", "de"))

        tree = template.process({}, request=request)
        self.assertEqual(
            tree.getroot().text,
            "deutsch (deutschland)")
