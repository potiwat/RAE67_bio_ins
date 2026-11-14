import math
import unittest

from student_hormone import receptor


class ReceptorValidationTests(unittest.TestCase):
    def test_nonfinite_h_is_rejected(self):
        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    receptor(value)

    def test_nonfinite_h_min_is_rejected(self):
        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    receptor(0.2, value, 1.0)

    def test_nonfinite_h_max_is_rejected(self):
        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    receptor(0.2, 0.0, value)

    def test_equal_or_reversed_range_is_rejected(self):
        for h_min, h_max in ((0.5, 0.5), (0.6, 0.5)):
            with self.subTest(h_min=h_min, h_max=h_max):
                with self.assertRaises(ValueError):
                    receptor(0.2, h_min, h_max)


if __name__ == "__main__":
    unittest.main()
