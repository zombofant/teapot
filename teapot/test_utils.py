import unittest

import teapot.utils

# testing our own implementation here -- we assume that the blist one is fine :)
from teapot.utils import _sortedlist as sortedlist

class Test_sortedlist(unittest.TestCase):
    def test_add(self):
        l = sortedlist()
        l.add(3)
        l.add(2)
        self.assertSequenceEqual([2, 3], l)
        l.add(1)
        self.assertSequenceEqual([1, 2, 3], l)
        l.add(1.5)
        self.assertSequenceEqual([1, 1.5, 2, 3], l)

    def test_contains(self):
        l = sortedlist([1, 2, 3])
        self.assertIn(1, l)
        self.assertNotIn(4, l)

    def test_discard(self):
        l = sortedlist([1, 2, 3])
        l.discard(2)
        self.assertSequenceEqual([1, 3], l)
        l.discard(1)
        self.assertSequenceEqual([3], l)
        l.discard(1)
        self.assertSequenceEqual([3], l)

    def test_len(self):
        l = sortedlist([1, 2, 3])
        self.assertEqual(len(l), 3)

    def test_getitem(self):
        l = sortedlist([3, 1, 2])
        self.assertEqual(1, l[0])
        self.assertEqual(2, l[1])
        self.assertEqual(3, l[2])

    def test_remove(self):
        l = sortedlist([3, 1, 2])
        l.remove(3)
        self.assertSequenceEqual([1, 2], l)

        with self.assertRaises(ValueError) as ctx:
            l.remove(4)

    def test_keyed(self):
        l = sortedlist([1, 2, 3], key=lambda x: -x)
        self.assertSequenceEqual([3, 2, 1], l)

class TestInstrumentedList(unittest.TestCase):
    class Item:
        foo = None

    class List(teapot.utils.InstrumentedList):
        def _acquire_item(self, item):
            item.foo = "bar"

        def _release_item(self, item):
            item.foo = None

    def setUp(self):
        self.list = self.List()
        self.item1, self.item2, self.item3 = self.Item(), self.Item(), self.Item()

    def test___delitem__(self):
        self.list.extend([self.item1, self.item2])

        self.assertIsNotNone(self.item1.foo)
        self.assertIsNotNone(self.item2.foo)

        del self.list[0]

        self.assertIsNone(self.item1.foo)


    def test___setitem__(self):
        self.list.extend([self.item1, self.item2])

        self.assertIsNotNone(self.item1.foo)
        self.assertIsNotNone(self.item2.foo)

        self.list[1] = self.item3

        self.assertIsNotNone(self.item3.foo)

        self.list[:] = [self.item2]

        self.assertIsNotNone(self.item2.foo)
        self.assertIsNone(self.item1.foo)
        self.assertIsNone(self.item3.foo)

    def test___init__(self):
        self.list = self.List([self.item1, self.item2])
        self.assertSequenceEqual(
            [self.item1, self.item2],
            self.list)

        self.assertIsNotNone(self.item1.foo)
        self.assertIsNotNone(self.item2.foo)

    def test_append(self):
        self.list.append(self.item1)
        self.list.append(self.item2)

        self.assertIsNone(self.item3.foo)
        self.list.append(self.item3)

        self.assertSequenceEqual(
            [self.item1, self.item2, self.item3],
            self.list)

        self.assertIsNotNone(self.item1.foo)
        self.assertIsNotNone(self.item2.foo)
        self.assertIsNotNone(self.item3.foo)

    def test_extend(self):
        l = [self.item1, self.item3, self.item2]
        self.list.extend(l)

        self.assertSequenceEqual(l, self.list)

        self.assertIsNotNone(self.item1.foo)
        self.assertIsNotNone(self.item2.foo)
        self.assertIsNotNone(self.item3.foo)

    def test_insert(self):
        self.list.extend([self.item1, self.item3])
        self.list.insert(1, self.item2)

        self.assertSequenceEqual(
            [self.item1, self.item2, self.item3],
            self.list)

        self.assertIsNotNone(self.item1.foo)
        self.assertIsNotNone(self.item2.foo)
        self.assertIsNotNone(self.item3.foo)

    def test_pop(self):
        self.list.extend([self.item1, self.item3])

        self.assertIsNotNone(self.item1.foo)
        self.assertIsNotNone(self.item3.foo)

        self.assertIsNone(self.list.pop().foo)
        self.assertIsNone(self.item3.foo)

    def test_remove(self):
        self.list.extend([self.item1, self.item3])

        self.assertIsNotNone(self.item1.foo)
        self.assertIsNotNone(self.item3.foo)

        self.list.remove(self.item1)

        self.assertIsNone(self.item1.foo)
