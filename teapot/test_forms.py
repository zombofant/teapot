import unittest

import teapot.forms

class TestWebForm(unittest.TestCase):
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

    def test_keys(self):
        form = self.Form()
        self.assertEqual("", form.key())
        self.assertEqual("test_int", self.Form.test_int.key(form))

    def test_validation(self):
        instance = self.Form()
        self.assertIsNone(instance.test_int)
        self.assertEqual(10, instance.test_int_with_default)
        instance.test_int = 20
        self.assertEqual(20, instance.test_int)

        del instance.test_int
        self.assertIsNone(instance.test_int)

        del instance.test_int_with_default
        self.assertEqual(10, instance.test_int_with_default)

        with self.assertRaises(ValueError):
            instance.test_int = "foo"

        with self.assertRaises(ValueError):
            instance.test_int_with_default = "foo"

    def test_autovalidation(self):
        post_data = {
            "test_int": ["20"],
            "test_int_with_default": ["30"]
        }
        instance = self.Form(post_data=post_data)

        self.assertFalse(instance.errors)
        self.assertEqual(20, instance.test_int)
        self.assertEqual(30, instance.test_int_with_default)

    def test_inheritance(self):
        class InheritedForm(self.Form):
            @teapot.forms.field
            def foo(self, value):
                return str(value)

        post_data = {
            "test_int": ["20"],
            "test_int_with_default": ["30"],
            "foo": ["40"]
        }
        instance = InheritedForm(post_data=post_data)

        self.assertFalse(instance.errors)
        self.assertEqual(20, instance.test_int)
        self.assertEqual(30, instance.test_int_with_default)
        self.assertEqual("40", instance.foo)

    def test_rows(self):
        class FormWithRows(self.Form):
            class Row(teapot.forms.Row):
                @classmethod
                def with_foo(cls, foo):
                    instance = cls()
                    instance.foo = foo
                    return instance

                @teapot.forms.field
                def foo(self, value):
                    return str(value)

                def __eq__(self, other):
                    return self.foo == other.foo

                def __ne__(self, other):
                    return not (self == other)

                def __repr__(self):
                    return "<Row foo={!r}>".format(self.foo)

                __hash__ = None

            testrows = teapot.forms.rows(Row)

        post_data = {
            "test_int": ["20"],
            "test_int_with_default": ["30"],
            "testrows[0].foo": ["bar"],
            "testrows[1].foo": ["baz"]
        }

        instance = FormWithRows(post_data=post_data)
        self.assertFalse(instance.errors)
        self.assertEqual(20, instance.test_int)
        self.assertEqual(30, instance.test_int_with_default)
        self.assertSequenceEqual(
            instance.testrows,
            [
                FormWithRows.Row.with_foo("bar"),
                FormWithRows.Row.with_foo("baz")
            ])

    def test_row_keys(self):
        class FormWithRows(teapot.forms.Form):
            class Row(teapot.forms.Row):
                @classmethod
                def with_foo(cls, foo):
                    instance = cls()
                    instance.foo = foo
                    return instance

                @teapot.forms.field
                def foo(self, value):
                    return str(value)

                def __eq__(self, other):
                    return self.foo == other.foo

                def __ne__(self, other):
                    return not (self == other)

                def __repr__(self):
                    return "<Row foo={!r}>".format(self.foo)

                __hash__ = None

            testrows = teapot.forms.rows(Row)

        instance = FormWithRows()
        instance.testrows.append(instance.Row())
        instance.testrows.append(instance.Row())
        instance.testrows.append(instance.Row())
        instance.testrows.append(instance.Row())

        self.assertEqual(
            "",
            instance.key())
        self.assertEqual(
            "testrows[0].",
            instance.testrows[0].key())
        self.assertEqual(
            "testrows[0].foo",
            FormWithRows.Row.foo.key(instance.testrows[0]))
