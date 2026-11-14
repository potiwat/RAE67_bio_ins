import unittest

from plot_annotations import response_markers


class PlotAnnotationTests(unittest.TestCase):
    def test_physical_crossings_pair_with_first_correct_response(self):
        rows = [
            {"time_s": "0.0", "expected_state": "FAR", "state": "FAR"},
            {"time_s": "1.0", "expected_state": "NEAR", "state": "FAR"},
            {"time_s": "1.2", "expected_state": "NEAR", "state": "NEAR"},
            {"time_s": "2.0", "expected_state": "FAR", "state": "NEAR"},
            {"time_s": "2.3", "expected_state": "FAR", "state": "FAR"},
        ]

        self.assertEqual(
            response_markers(rows),
            [
                {"kind": "enter", "physical_time_s": 1.0,
                 "response_time_s": 1.2},
                {"kind": "exit", "physical_time_s": 2.0,
                 "response_time_s": 2.3},
            ],
        )

    def test_missing_response_remains_none(self):
        rows = [
            {"time_s": "0.0", "expected_state": "FAR", "state": "FAR"},
            {"time_s": "1.0", "expected_state": "NEAR", "state": "FAR"},
        ]

        self.assertIsNone(response_markers(rows)[0]["response_time_s"])


if __name__ == "__main__":
    unittest.main()
