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

    def test_invalid_matching_row_is_not_a_correct_response(self):
        rows = [
            {"time_s": "0.0", "expected_state": "FAR", "state": "FAR",
             "valid": "1"},
            {"time_s": "1.0", "expected_state": "NEAR", "state": "FAR",
             "valid": "1"},
            {"time_s": "1.1", "expected_state": "NEAR", "state": "NEAR",
             "valid": "0"},
            {"time_s": "1.3", "expected_state": "NEAR", "state": "NEAR",
             "valid": "1"},
        ]

        self.assertEqual(
            response_markers(rows)[0]["response_time_s"],
            1.3,
        )


if __name__ == "__main__":
    unittest.main()
