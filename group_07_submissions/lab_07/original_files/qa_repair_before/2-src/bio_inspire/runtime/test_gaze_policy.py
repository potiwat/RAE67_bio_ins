"""Reject stale motion, awake searching in sleepy, and invented activity."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'shared' / 'runtime'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from face_tracking import FaceTracker
from gaze_policy import gaze_intent


class GazeTests(unittest.TestCase):
    def test_fresh_face_follows_without_creating_activity(self):
        observation = FaceTracker(.5).update([(.7, .3, .1, .1)], 1, 1)
        for state in ('normal', 'interested', 'happy', 'afraid'):
            intent = gaze_intent(observation, state)
            self.assertEqual(intent.mode, 'FOLLOW')
            self.assertEqual(intent.error_xy, (.5, -.30000000000000004))
            self.assertFalse(intent.counts_as_activity)
            self.assertFalse(intent.motor_output_enabled)

    def test_missing_face_searches_only_while_awake(self):
        observation = FaceTracker(.5).update([], 1, 1)
        self.assertEqual(gaze_intent(observation, 'normal').mode, 'SEARCH')
        self.assertEqual(gaze_intent(observation, 'sleepy').mode, 'DOZE')

    def test_sleepy_keeps_follow_and_droop_separate_from_joint_angles(self):
        observation = FaceTracker(.5).update([(.45, .45, .1, .1)], 1, 1)
        intent = gaze_intent(observation, 'sleepy')
        self.assertEqual(intent.mode, 'FOLLOW_DROOP')
        self.assertEqual(intent.error_xy, (0, 0))

    def test_stale_ambiguous_fault_or_bad_state_holds_with_no_error(self):
        tracker = FaceTracker(.5)
        stale = tracker.update([], 1, 2)
        face = tracker.update([(.4, .4, .2, .2)], 3, 3)
        ambiguous = tracker.update([(.39, .4, .2, .2), (.41, .4, .2, .2)], 4, 4)
        for observation, state, fault in [(stale, 'normal', False),
                (ambiguous, 'normal', False), (face, 'normal', True),
                (face, 'invalid-state', False)]:
            intent = gaze_intent(observation, state, fault)
            self.assertEqual(intent.mode, 'HOLD')
            self.assertIsNone(intent.error_xy)


if __name__ == '__main__':
    unittest.main()
