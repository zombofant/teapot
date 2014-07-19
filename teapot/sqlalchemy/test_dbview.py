import unittest

import teapot.request

from . import dbview

from .testing_model import *

class TestView(DBTestCase):
    def _through_query(self, Form, query_data):
        request = teapot.request.Request(
            query_data=query_data)
        f = Form(self.db,
                 request=request,
                 post_data=request.query_data)
        return f

    def _make_form_and_query(self,
                             *args,
                             query_data={},
                             **kwargs):
        Form = dbview.make_form(*args, **kwargs)
        f = self._through_query(Form, query_data)

        return f

    def _full_test(self,
                   *args,
                   expected_sequence=[],
                   **kwargs):
        f = self._make_form_and_query(
            *args,
            **kwargs)

        self.assertSequenceEqual(
            list(f),
            expected_sequence)

    def test_simple_view(self):
        all_as, all_bs = self.insert_test_data()

        self._full_test(
            A,
            [
                ("id", A.a_id, int),
                ("value1", A.value1, str),
            ],
            query_data={
                "p": ["1"],
                "d": ["desc"],
                "ob": ["id"],
            },
            expected_sequence=[
                (a.a_id, a.value1)
                for a in sorted(all_as,
                                key=lambda a: a.a_id,
                                reverse=True)
            ]
        )

    def test_filtered_view(self):
        all_as, all_bs = self.insert_test_data()

        self._full_test(
            A,
            [
                ("id", A.a_id, int),
                ("value1", A.value1, str),
            ],
            query_data={
                "p": ["1"],
                "d": ["desc"],
                "ob": ["id"],
                "f[0].f": ["value1"],
                "f[0].o": ["__ne__"],
                "f[0].v": ["fnord"],
            },
            expected_sequence=[
                (a.a_id, a.value1)
                for a in sorted(all_as,
                                key=lambda a: a.a_id,
                                reverse=True)
                if a.value1 != "fnord"
            ]
        )

    def test_type_detection(self):
        all_as, all_bs = self.insert_test_data()

        self._full_test(
            A,
            [
                ("id", A.a_id, None),
                ("value1", A.value1, None),
            ],
            query_data={
                "p": ["1"],
                "d": ["desc"],
                "ob": ["id"],
            },
            expected_sequence=[
                (a.a_id, a.value1)
                for a in sorted(all_as,
                                key=lambda a: a.a_id,
                                reverse=True)
            ]
        )

    def test_joined_view(self):
        all_as, all_bs = self.insert_test_data()

        all_as = list(filter(
            lambda a: a.value2 != "fnord",
            all_as))

        self._full_test(
            A,
            [
                ("id", A.a_id, None),
                ("value1", A.value1, None),
                ("valueb", B.valueb, None),
            ],
            supplemental_objects=[
                B
            ],
            query_data={
                "p": ["1"],
                "d": ["desc"],
                "ob": ["id"],
            },
            expected_sequence=[
                (a.a_id, a.value1, b.valueb)
                for a, b in sorted(zip(all_as, all_bs),
                                   key=lambda x: x[0].a_id,
                                   reverse=True)
            ]
        )

    def test_outerjoined_view(self):
        all_as, all_bs = self.insert_test_data()

        self._full_test(
            A,
            [
                ("id", A.a_id, None),
                ("value1", A.value1, None),
                ("valueb", B.valueb, None),
            ],
            supplemental_objects=[
                ("outerjoin", B)
            ],
            query_data={
                "p": ["1"],
                "d": ["desc"],
                "ob": ["id"],
            },
            expected_sequence=[
                (3, "fnord", None),
                (2, "bar", "for A2"),
                (1, "foo", "for A1")
            ]
        )

    def test_autojoined_view(self):
        all_as, all_bs = self.insert_test_data()

        all_as = list(filter(
            lambda a: a.value2 != "fnord",
            all_as))

        self._full_test(
            A,
            [
                ("id", A.a_id, None),
                ("value1", A.value1, None),
                ("valueb", B.valueb, None),
            ],
            query_data={
                "p": ["1"],
                "d": ["desc"],
                "ob": ["id"],
            },
            expected_sequence=[
                (a.a_id, a.value1, b.valueb)
                for a, b in sorted(zip(all_as, all_bs),
                                   key=lambda x: x[0].a_id,
                                   reverse=True)
            ]
        )

    def test_pagination(self):
        all_as, all_bs = self.insert_test_data()

        self._full_test(
            A,
            [
                ("id", A.a_id, None),
                ("value1", A.value1, None),
            ],
            itemsperpage=2,
            query_data={
                "p": ["1"],
                "d": ["desc"],
                "ob": ["id"],
            },
            expected_sequence=[
                (3, "fnord"),
                (2, "bar"),
            ]
        )

        self._full_test(
            A,
            [
                ("id", A.a_id, None),
                ("value1", A.value1, None),
            ],
            itemsperpage=2,
            query_data={
                "p": ["2"],
                "d": ["desc"],
                "ob": ["id"],
            },
            expected_sequence=[
                (1, "foo"),
            ]
        )

    def test_method_mutation(self):
        all_as, all_bs = self.insert_test_data()

        data = [
            (a.a_id, a.value1)
            for a in sorted(all_as,
                            key=lambda x: x.a_id,
                            reverse=True)
        ]

        f = self._make_form_and_query(
            A,
            [
                ("id", A.a_id, None),
                ("value1", A.value1, None),
            ],
            itemsperpage=2,
            query_data={
                "p": ["1"],
                "d": ["desc"],
                "ob": ["id"],
            })

        self.assertSequenceEqual(
            list(f),
            data[:2])

        self.assertSequenceEqual(
            list(f.at_page(2)),
            data[2:4])
