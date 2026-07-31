import sys
import unittest
sys.path.insert(0, "src")
from app import add

class AppTest(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(2, 3), 5)
