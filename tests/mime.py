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

class TestCaseFoldedDict(unittest.TestCase):
    def test_construct_from_dict(self):
        d = {"A": "a", "B": "b"}
        cfd = teapot.mime.CaseFoldedDict(d)
        self.assertEqual(cfd["a"], d["A"])
        self.assertEqual(cfd["A"], d["A"])
        self.assertEqual(cfd["b"], d["B"])
        self.assertEqual(cfd["B"], d["B"])

    def test_construct_from_sequence(self):
        seq = [("A", "1"), ("a", "2"), ("B", "3")]
        cfd = teapot.mime.CaseFoldedDict(seq)
        self.assertEqual(cfd["a"], "2")
        self.assertEqual(cfd["A"], "2")
        self.assertEqual(cfd["B"], "3")

    def test_construct_with_kwargs(self):
        seq = [("A", "1"), ("a", "2"), ("B", "3")]
        cfd = teapot.mime.CaseFoldedDict(seq, B="4")
        self.assertEqual(cfd["a"], "2")
        self.assertEqual(cfd["A"], "2")
        self.assertEqual(cfd["B"], "4")

    def test_item_casefolding(self):
        cfd = teapot.mime.CaseFoldedDict()
        cfd["A"] = "Foo"
        self.assertEqual(cfd["a"], "Foo")
        self.assertEqual(cfd["A"], "Foo")

    def test_update_casefolding(self):
        cfd = teapot.mime.CaseFoldedDict()
        d = {"A": "1"}
        cfd["a"] = "2"
        cfd.update(d)
        self.assertEqual(cfd["a"], "1")

    def test_pop_casefolding(self):
        cfd = teapot.mime.CaseFoldedDict()
        cfd["a"] = "2"
        self.assertEqual(cfd.pop("A"), "2")
        self.assertRaises(KeyError, cfd.pop, "a")

    def test_fromkeys_casefolding(self):
        cfd = teapot.mime.CaseFoldedDict.fromkeys(["A", "B", "C", "a"])
        self.assertEqual(len(cfd), 3)

    def test_get_casefolding(self):
        cfd = teapot.mime.CaseFoldedDict()
        cfd["a"] = "2"
        self.assertEqual(cfd.get("A"), "2")
