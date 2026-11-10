"""Keep commanded, servo-internal target and encoder distinct in diagnostics."""
import unittest
from normal_gaze_motor import decode_state


class ExtendedFeedbackTests(unittest.TestCase):
    def test_extended_feedback_preserves_health_and_distinguishes_targets(self):
        block = bytearray(38)
        for offset, value in ((9, 2800), (23, 2830), (34, 2815), (36, 37)):
            block[offset:offset+2] = value.to_bytes(2, 'little')
        block[7] = 1
        block[32] = 4
        row = decode_state(2, block)
        self.assertEqual(row['goal_raw'], 2800)
        self.assertEqual(row['position_raw'], 2830)
        self.assertEqual(row['internal_target_raw'], 2815)
        self.assertEqual(row['current_raw'], 37)
        self.assertEqual(row['status_raw'], 4)
        self.assertEqual(row['torque_raw'], 1)

    def test_legacy_feedback_does_not_invent_internal_target(self):
        row = decode_state(2, bytes(34))
        self.assertIsNone(row.get('internal_target_raw'))
        self.assertIsNone(row.get('current_raw'))
        with self.assertRaises(ValueError):
            decode_state(2, bytes(37))
