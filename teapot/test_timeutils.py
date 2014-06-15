import unittest

from datetime import datetime

from . import timeutils

random_datetime = datetime(2014, 6, 15, 12, 43, 58, 710891)

class TestParseDatetime(unittest.TestCase):
    def test_parse_full(self):
        self.assertEqual(
            random_datetime,
            timeutils.parse_datetime("2014-06-15T12:43:58.710891Z"))
        self.assertEqual(
            random_datetime,
            timeutils.parse_datetime("2014-06-15T12:43:58.710891"))
        self.assertEqual(
            random_datetime,
            timeutils.parse_datetime("2014-06-15T14:43:58.710891+0200"))

    def test_parse_date(self):
        self.assertEqual(
            random_datetime.replace(hour=0, minute=0, second=0, microsecond=0),
            timeutils.parse_datetime("2014-06-15Z"))
        self.assertEqual(
            random_datetime.replace(hour=0, minute=0, second=0, microsecond=0),
            timeutils.parse_datetime("2014-06-15"))
        self.assertEqual(
            random_datetime.replace(hour=12, minute=0, second=0, microsecond=0),
            timeutils.parse_datetime("2014-06-16+1200"))

    def test_parse_time(self):
        self.assertEqual(
            random_datetime.replace(year=1900, month=1, day=1),
            timeutils.parse_datetime("12:43:58.710891Z"))
        self.assertEqual(
            random_datetime.replace(year=1900, month=1, day=1),
            timeutils.parse_datetime("12:43:58.710891"))
        self.assertEqual(
            random_datetime.replace(year=1900, month=1, day=1),
            timeutils.parse_datetime("14:43:58.710891+0200"))

    def test_parse_week(self):
        # test with leap year
        self.assertEqual(
            datetime(year=2008, month=6, day=9,
                     hour=0, minute=0, second=0,
                     microsecond=0),
            timeutils.parse_datetime("2008-W24Z"))
        self.assertEqual(
            datetime(year=2008, month=6, day=9,
                     hour=0, minute=0, second=0,
                     microsecond=0),
            timeutils.parse_datetime("2008-W24"))

    def test_parse_month(self):
        self.assertEqual(
            random_datetime.replace(day=1,
                                    hour=0, minute=0, second=0,
                                    microsecond=0),
            timeutils.parse_datetime("2014-06Z"))
        self.assertEqual(
            random_datetime.replace(day=1,
                                    hour=0, minute=0, second=0,
                                    microsecond=0),
            timeutils.parse_datetime("2014-06"))
