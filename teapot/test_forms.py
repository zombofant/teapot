import unittest

import teapot.forms

class TestWebForm(unittest.TestCase):
    def test_validation(self):
        class Form(teapot.forms.Form):
            @teapot.forms.field
            def test_int(self, value):
                return int(value)

            @teapot.forms.field
            def test_int_with_default(self, value):
                return int(value)

            @test_int_with_default.default
            def test_int_with_default(self):
                return 10

        instance = Form()
        self.assertIsNone(instance.test_int)
        self.assertEqual(10, instance.test_int_with_default)
        instance.test_int = 20
        self.assertEqual(20, instance.test_int)

        with self.assertRaises(AttributeError):
            del instance.test_int

        with self.assertRaises(AttributeError):
            del instance.test_int_with_default

        with self.assertRaises(ValueError):
            instance.test_int = "foo"

        with self.assertRaises(ValueError):
            instance.test_int_with_default = "foo"
