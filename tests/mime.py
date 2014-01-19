import unittest
import codecs

import teapot.mime

class TestType(unittest.TestCase):
    UNKNOWN_CODEC = "foobar_9uHQRO6GY7LhONGAMqTIYiZs"

    def test_stringification(self):
        mt = teapot.mime.Type("text", "plain")
        self.assertEqual(str(mt), "text/plain")

        mt = teapot.mime.Type("text", "plain", charset="utf-8")
        self.assertEqual(str(mt), "text/plain; charset=utf-8")

    def test_reject_unknown_encoding(self):
        # if that does not raise, we incredibly have to pick another
        # unknown codec.
        self.assertRaises(LookupError, codecs.lookup, self.UNKNOWN_CODEC)

        self.assertRaises(LookupError,
                          teapot.mime.Type,
                          "text",
                          "plain",
                          charset=self.UNKNOWN_CODEC)
