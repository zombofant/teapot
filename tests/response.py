import unittest
import codecs

import teapot.response
import teapot.accept
import teapot.mime

class Test_lookup_response_message(unittest.TestCase):
    def test_default(self):
        self.assertEqual(teapot.response.lookup_response_message(0),
                         "Unknown Status")
        self.assertEqual(teapot.response.lookup_response_message(0, "foobar"),
                         "foobar")

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

        content_type = teapot.mime.Type("text", "plain")

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
            teapot.mime.Type.text_plain,
            response_code=404)
        self.assertEqual(response.http_response_message, "Not Found")

    def test_can_negotiate_with_wildcard(self):
        client_preferences = teapot.accept.CharsetPreferenceList([
            teapot.accept.CharsetPreference("*", 1.0),
        ])
        client_preferences.inject_rfc_values()

        content_type = teapot.mime.Type("text", "plain")

        response = teapot.response.Response(
            content_type, "foobar")
        response.negotiate_charset(client_preferences)
        self.assertEqual(response.content_type.charset, "utf-8")
