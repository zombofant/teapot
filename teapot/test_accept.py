import unittest

import teapot.accept

class ListTest(unittest.TestCase):
    def _test_list(self, preflist, expected_qualities):
        for pref, q in expected_qualities:
            calculatedq = preflist.get_quality(pref)
            self.assertEqual(
                q,
                calculatedq,
                msg="{0!s} did not get the correct q-value: {1}"
                " expected, {2} calculated".format(
                    pref,
                    q,
                    calculatedq
                ))

class MIMEPreferenceList(ListTest):
    maxDiff = None

    def test_parsing(self):
        P = teapot.accept.MIMEPreference
        header = """text/plain; q=0.5, text/html,
                    text/x-dvi; q=0.8, text/x-c"""
        l = teapot.accept.MIMEPreferenceList()
        l.append_header(header)
        self.assertSequenceEqual(
            list(l),
            [
                P("text", "plain", q=0.5),
                P("text", "html", q=1.0),
                P("text", "x-dvi", q=0.8),
                P("text", "x-c", q=1.0),
            ]
        )

    def test_rfc_compliance(self):
        l = teapot.accept.MIMEPreferenceList()
        l.append_header("""text/*;q=0.3, text/html;q=0.7, text/html;level=1,
               text/html;level=2;q=0.4, */*;q=0.5""")

        P = teapot.accept.MIMEPreference
        expected_qualities = [
            (P.parse("text/html;level=1"),      1.0),
            (P.parse("text/html"),              0.7),
            (P.parse("text/plain"),             0.3),
            (P.parse("image/jpeg"),             0.5),
            (P.parse("text/html;level=2"),      0.4),
            (P.parse("text/html;level=3"),      0.7),
        ]
        self._test_list(l, expected_qualities)

    def test_additional(self):
        l = teapot.accept.MIMEPreferenceList()
        l.append_header("""image/png;q=0.9, text/plain;q=1.0""")

        P = teapot.accept.MIMEPreference
        expected_qualities = [
            (P.parse("text/plain"),             1.0),
            (P.parse("image/png"),              0.9),
        ]
        self._test_list(l, expected_qualities)

        self.assertEqual(
            l.best_match([
                p
                for p, _ in expected_qualities
            ]),
            P.parse("text/plain"))

class CharsetPreferenceList(ListTest):
    def test_parsing(self):
        P = teapot.accept.CharsetPreference
        # diverging from the RFC here, python does not know
        # unicode-1-1
        header = """iso-8859-5, utf-8;q=0.8"""
        l = teapot.accept.CharsetPreferenceList()
        l.append_header(header)
        l.inject_rfc_values()
        self.assertSequenceEqual(list(l),
            [
                P("iso-8859-5", 1.0),
                P("utf-8", 0.8),
                P("iso-8859-1", 1.0)
            ]
        )
    def test_special_case_for_latin1(self):
        P = teapot.accept.CharsetPreference

        header = """iso-8859-1;q=0.8"""
        l = teapot.accept.CharsetPreferenceList()
        l.append_header(header)
        l.inject_rfc_values()
        self.assertSequenceEqual(list(l),
            [
                P("iso-8859-1", 0.8)
            ]
        )

        header = """iso-8859-5;q=0.8"""
        l = teapot.accept.CharsetPreferenceList()
        l.append_header(header)
        l.inject_rfc_values()
        self.assertSequenceEqual(list(l),
            [
                P("iso-8859-5", 0.8),
                P("iso-8859-1", 1.0)
            ]
        )

        header = """iso-8859-5;q=0.8, *;q=0.6"""
        l = teapot.accept.CharsetPreferenceList()
        l.append_header(header)
        l.inject_rfc_values()
        self.assertSequenceEqual(list(l),
            [
                P("iso-8859-5", 0.8),
                P("*", 0.6)
            ]
        )

    def test_empty(self):
        P = teapot.accept.CharsetPreference
        l = teapot.accept.CharsetPreferenceList()
        # identical to No Header Present
        l.append_header("")
        l.inject_rfc_values()

        # according to RFC, this is equivalent to all charaters sets are accepted
        self.assertSequenceEqual(list(l),
            [
                P("*", 1.0)
            ]
        )

class LanguagePreferenceList(ListTest):
    def test_parsing(self):
        P = teapot.accept.LanguagePreference
        header = """da, en-gb;q=0.8, en;q=0.7"""
        l = teapot.accept.LanguagePreferenceList()
        l.append_header(header)
        self.assertSequenceEqual(list(l),
            [
                P("da", None, q=1.0),
                P("en", "gb", q=0.8),
                P("en", None, q=0.7)
            ]
        )

    def test_rfc_compliance(self):
        P = teapot.accept.LanguagePreference
        header = """da, en-gb;q=0.8, en;q=0.7, de-at;q=0.5"""
        l = teapot.accept.LanguagePreferenceList()
        l.append_header(header)

        expected_qualities = [
            (P.parse("da"),                     1.0),
            (P.parse("en-gb"),                  0.8),
            (P.parse("en-us"),                  0.7),
            (P.parse("da-foo"),                 1.0),
            (P.parse("de-de"),                  0.0),
            (P.parse("de"),                     0.0),
        ]
        self._test_list(l, expected_qualities)

    def test_pick_exact_match(self):
        P = teapot.accept.LanguagePreference
        header = """de-at;q=1.0,en;q=0.9"""
        prefs = teapot.accept.LanguagePreferenceList()
        prefs.append_header(header)

        self.assertEqual(
            prefs.best_match([
                P.parse("en;q=1.0"),
                P.parse("de-de;q=1.0"),
                P.parse("en-gb;q=1.0"),
                P.parse("en-us;q=1.0"),
            ]),
            P.parse("en;q=1.0"))
