import unittest

import teapot.forms

from datetime import datetime

from . import fields
from teapot.test_forms import FakeRequest

random_datetime = datetime(2014, 6, 15, 12, 10, 4, 541810)

class TestDateTimeMode(unittest.TestCase):
    def test_truncation(self):
        mode = fields.DateTimeMode.Full
        self.assertEqual(
            random_datetime,
            mode.truncate_datetime(random_datetime))

        mode &= fields.DateTimeMode.Day
        self.assertEqual(
            datetime(2014, 6, 15),
            mode.truncate_datetime(random_datetime))

    def test_validation(self):
        with self.assertRaises(ValueError):
            fields.DateTimeMode(
                fields.SupermodeDate,
                fields.DateTimeMode.LEVEL_HOUR,
                False)

        with self.assertRaises(ValueError):
            fields.DateTimeMode(
                fields.SupermodeTime,
                fields.DateTimeMode.LEVEL_HOUR,
                True)

        with self.assertRaises(ValueError):
            fields.DateTimeMode.Time & fields.DateTimeMode.Week

class Form(teapot.forms.Form):
    dt = fields.DateTimeField(fields.DateTimeMode.Full,
                              "datetime")

class TestDateTimeField(unittest.TestCase):
    def setUp(self):
        self.form = Form()
        self.form.dt = random_datetime

    def test_parse_datetime(self):
        request = FakeRequest({
            "dt": ["2014-06-15T12:10:04.541810Z"]
        })
        form = Form(request=request)
        self.assertEqual(
            random_datetime,
            form.dt)

    def test_parse_date(self):
        request = FakeRequest({
            "dt": ["2014-06-15Z"]
        })
        form = Form(request=request)
        self.assertFalse(
            form.errors)
        self.assertEqual(
            random_datetime.replace(hour=0, minute=0, second=0, microsecond=0),
            form.dt)

    def test_parse_week(self):
        request = FakeRequest({
            "dt": ["2014-W24Z"]
        })
        form = Form(request=request)
        self.assertFalse(
            form.errors)
        self.assertEqual(
            random_datetime.replace(day=9,
                                    hour=0, minute=0, second=0,
                                    microsecond=0),
            form.dt)

    def test_parse_month(self):
        request = FakeRequest({
            "dt": ["2014-06Z"]
        })
        form = Form(request=request)
        self.assertFalse(
            form.errors)
        self.assertEqual(
            random_datetime.replace(day=1,
                                    hour=0, minute=0, second=0,
                                    microsecond=0),
            form.dt)

    def test_parse_time(self):
        request = FakeRequest({
            "dt": ["12:10:04.541810Z"]
        })
        form = Form(request=request)
        self.assertFalse(
            form.errors)
        self.assertEqual(
            random_datetime.replace(year=1900, month=1, day=1),
            form.dt)

    def test_view_type_datetime(self):
        self.assertEqual(
            "2014-06-15T12:10:04.542Z",
            Form.dt.to_field_value(
                self.form,
                "datetime"))

    def test_view_type_date(self):
        self.assertEqual(
            "2014-06-15Z",
            Form.dt.to_field_value(
                self.form,
                "date"))

    def test_view_type_time(self):
        self.assertEqual(
            "12:10:04.542Z",
            Form.dt.to_field_value(
                self.form,
                "time"))

    def test_view_type_month(self):
        self.assertEqual(
            "2014-06Z",
            Form.dt.to_field_value(
                self.form,
                "month"))

    def test_view_type_week(self):
        self.assertEqual(
            "2014-W24Z",
            Form.dt.to_field_value(
                self.form,
                "week"))

    def test_unknown_view_type(self):
        self.assertNotIn(
            "foobar",
            Form.dt.FORMATTERS)
        self.assertEqual(
            "2014-06-15T12:10:04.542Z",
            Form.dt.to_field_value(
                self.form,
                "foobar"))
