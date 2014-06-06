import unittest

import teapot.forms

class CustomField(teapot.forms.CustomField):
    # install some instrumentations to test the different code paths in
    # CustomField
    def get_default(self, instance):
        return "default"

    def input_validate(self, test_state_value, value):
        if test_state_value >= 1:
            err = ValueError(value)
            yield err
            if test_state_value >= 2:
                raise err

        return value

class CustomFieldTester(teapot.forms.Form):
    field = CustomField()
    field.name = "field"

class TestCustomField(unittest.TestCase):
    def setUp(self):
        self.instance = CustomFieldTester()

    def tearDown(self):
        del self.instance

    def test_access(self):
        self.assertEqual(
            "default",
            self.instance.field)

        self.instance.field = "foo"
        self.assertEqual(
            "foo",
            self.instance.field)

        del self.instance.field

        self.assertEqual(
            "default",
            self.instance.field)

    def test_validation_no_errors(self):
        # no errors if argument is 0, due to instrumentation
        self.assertFalse(
            list(CustomFieldTester.field.from_field_values(
                self.instance,
                0,
                ["bar"])))

        self.assertEqual(
            "bar",
            self.instance.field,
            "no errors, field value must get updated")

    def test_validation_noncritcal(self):
        errs = list(CustomFieldTester.field.from_field_values(
            self.instance,
            1,
            ["bar"]))

        self.assertIsInstance(
            errs[0],
            ValueError)
        self.assertEqual(
            "bar",
            errs[0].err.args[0])

        self.assertEqual(
            "bar",
            self.instance.field,
            "field value must get updated if the error is noncritical")

    def test_validation_critical(self):
        self.instance.field = "foo"

        errs = list(CustomFieldTester.field.from_field_values(
            self.instance,
            2,
            ["bar"]))

        self.assertIsInstance(
            errs[0],
            ValueError)
        self.assertEqual(
            "bar",
            errs[0].err.args[0])

        self.assertEqual(
            "foo",
            self.instance.field,
            "field value must be unchanged")

class FakeRequest:
    def __init__(self, post_data):
        self.post_data = post_data

class TestWebForm(unittest.TestCase):
    class Form(teapot.forms.Form):
        test_int = teapot.forms.IntField(default=None)
        test_int_with_default = teapot.forms.IntField(
            default=10)
        boolfield = teapot.forms.CheckboxField()

    class FormWithRows(Form):
        class Row(teapot.forms.Row):
            @classmethod
            def with_foo(cls, foo):
                instance = cls()
                instance.foo = foo
                return instance

            foo = teapot.forms.TextField(default=None)

            def __eq__(self, other):
                return self.foo == other.foo

            def __ne__(self, other):
                return not (self == other)

            def __repr__(self):
                return "<Row foo={!r}>".format(self.foo)

            def __hash__(self):
                return object.__hash__(self)

        testrows = teapot.forms.rows(Row)

    def test_keys(self):
        form = self.Form()
        self.assertEqual("", form.get_html_field_key())
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

    def test_autovalidation(self):
        request = FakeRequest({
            "test_int": ["20"],
            "test_int_with_default": ["30"]
        })
        instance = self.Form(request=request)

        self.assertFalse(instance.errors)
        self.assertEqual(20, instance.test_int)
        self.assertEqual(30, instance.test_int_with_default)

    def test_boolfields(self):
        request = FakeRequest({
            "test_int": ["20"],
            "test_int_with_default": ["30"]
        })
        instance = self.Form(request=request)

        self.assertFalse(instance.errors)
        self.assertFalse(instance.boolfield)

        request = FakeRequest({
            "test_int": ["20"],
            "test_int_with_default": ["30"],
            "boolfield": [1]
        })
        instance = self.Form(request=request)

        self.assertFalse(instance.errors)
        self.assertTrue(instance.boolfield)

    def test_inheritance(self):
        class InheritedForm(self.Form):
            foo = teapot.forms.TextField(default=None)

        request = FakeRequest({
            "test_int": ["20"],
            "test_int_with_default": ["30"],
            "foo": ["40"]
        })
        instance = InheritedForm(request=request)

        self.assertFalse(instance.errors)
        self.assertEqual(20, instance.test_int)
        self.assertEqual(30, instance.test_int_with_default)
        self.assertEqual("40", instance.foo)

    def test_rows(self):
        request = FakeRequest({
            "test_int": ["20"],
            "test_int_with_default": ["30"],
            "testrows[0].foo": ["bar"],
            "testrows[1].foo": ["baz"]
        })

        instance = self.FormWithRows(request=request)
        self.assertFalse(instance.errors)
        self.assertEqual(20, instance.test_int)
        self.assertEqual(30, instance.test_int_with_default)
        self.assertSequenceEqual(
            instance.testrows,
            [
                self.FormWithRows.Row.with_foo("bar"),
                self.FormWithRows.Row.with_foo("baz")
            ])

    def test_row_keys(self):
        instance = self.FormWithRows()
        instance.testrows.append(instance.Row())
        instance.testrows.append(instance.Row())
        instance.testrows.append(instance.Row())
        instance.testrows.append(instance.Row())

        self.assertEqual(
            "",
            instance.get_html_field_key())
        self.assertEqual(
            "testrows[0].",
            instance.testrows[0].get_html_field_key())
        self.assertEqual(
            "testrows[0].foo",
            self.FormWithRows.Row.foo.key(instance.testrows[0]))

    def test_action_resolution(self):
        instance = self.FormWithRows()
        instance.testrows.append(instance.Row())
        instance.testrows.append(instance.Row())
        instance.testrows.append(instance.Row())
        instance.testrows.append(instance.Row())

        self.assertEqual(
            (instance.testrows[2], "test"),
            instance.find_action_by_key("testrows[2].test"))

        self.assertEqual(
            (instance.testrows[1], "test"),
            instance.find_action({
                "action:testrows[1].test": []}))
