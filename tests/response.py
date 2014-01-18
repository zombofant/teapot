import unittest
import codecs

import teapot.response
import teapot.accept

class TestMIMEType(unittest.TestCase):
    UNKNOWN_CODEC = "foobar_9uHQRO6GY7LhONGAMqTIYiZs"

    def test_stringification(self):
        mt = teapot.response.MIMEType("text", "plain")
        self.assertEqual(str(mt), "text/plain")

        mt = teapot.response.MIMEType("text", "plain", charset="utf-8")
        self.assertEqual(str(mt), "text/plain; charset=utf-8")

    def test_reject_unknown_encoding(self):
        # if that does not raise, we incredibly have to pick another
        # unknown codec.
        self.assertRaises(LookupError, codecs.lookup, self.UNKNOWN_CODEC)

        self.assertRaises(LookupError,
                          teapot.response.MIMEType,
                          "text",
                          "plain",
                          charset=self.UNKNOWN_CODEC)

class TestResponse(unittest.TestCase):
    def test_charset_negotiation(self):
        client_preferences = teapot.accept.CharsetPreferenceList([
            teapot.accept.CharsetPreference("latin1", 0.9),
            teapot.accept.CharsetPreference("ascii", 1.0)
        ])
        client_preferences.inject_rfc_values()

        unicode_text = "☺"
        latin_text = "äüö"
        ascii_text = "abc"

        content_type = teapot.response.MIMEType("text", "plain")

        response = teapot.response.Response(
            content_type, unicode_text)
        response.negotiate_charset(client_preferences)
        self.assertEqual(response.content_type.charset, "utf-8")

        response = teapot.response.Response(
            content_type, latin_text)
        response.negotiate_charset(client_preferences)
        self.assertEqual(response.content_type.charset, "iso8859-1")

        response = teapot.response.Response(
            content_type, ascii_text)
        response.negotiate_charset(client_preferences)
        self.assertEqual(response.content_type.charset, "ascii")

    def test_http_attributes(self):
        response = teapot.response.Response(
            teapot.response.MIMEType.text_plain,
            response_code=404)
        self.assertEqual(response.http_response_message, "Not Found")
