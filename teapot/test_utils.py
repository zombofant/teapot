import unittest

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
