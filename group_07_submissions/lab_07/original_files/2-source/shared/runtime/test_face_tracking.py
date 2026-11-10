"""Breaks covered: target switching, stale targets, invalid clocks and geometry."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from face_tracking import FaceTracker


class TrackingTests(unittest.TestCase):
    def test_first_selection_is_centre_not_largest(self):
        tracker = FaceTracker(0.5)  # test fixture, not hardware timing
        result = tracker.update([(0, 0, .4, .4), (.45, .45, .1, .1)], 1, 1)
        self.assertEqual(result.box, (.45, .45, .1, .1))
        self.assertEqual(result.error_xy, (0., 0.))

    def test_keeps_existing_player_when_another_is_nearer_centre(self):
        tracker = FaceTracker(.5)
        tracker.update([(.2, .3, .2, .2)], 1, 1)
        result = tracker.update([(.21, .3, .2, .2), (.45, .45, .1, .1)], 2, 2)
        self.assertEqual(result.box, (.21, .3, .2, .2))
        self.assertEqual(result.status, 'TRACKING')

    def test_missing_target_does_not_pick_unrelated_face(self):
        tracker = FaceTracker(.5)
        tracker.update([(.1, .1, .1, .1)], 1, 1)
        lost = tracker.update([(.7, .7, .1, .1)], 2, 2)
        self.assertEqual(lost.status, 'LOST')
        self.assertIsNone(lost.error_xy)
        self.assertIsNone(lost.box)

    def test_overlapping_multiple_candidates_are_ambiguous(self):
        tracker = FaceTracker(.5)
        tracker.update([(.3, .3, .2, .2)], 1, 1)
        result = tracker.update([(.29, .3, .2, .2), (.31, .3, .2, .2)], 2, 2)
        self.assertEqual(result.status, 'AMBIGUOUS')
        self.assertIsNone(result.error_xy)

    def test_stale_frame_cannot_acquire_or_update_target(self):
        tracker = FaceTracker(.5)
        stale = tracker.update([(.2, .2, .1, .1)], 1, 2)
        self.assertEqual(stale.status, 'STALE')
        result = tracker.update([(.45, .45, .1, .1)], 3, 3)
        self.assertEqual(result.status, 'ACQUIRED')

    def test_stale_after_lock_contains_no_old_error(self):
        tracker = FaceTracker(.5)
        tracker.update([(.2, .2, .1, .1)], 1, 1)
        result = tracker.update([(.2, .2, .1, .1)], 2, 3)
        self.assertIsNone(result.error_xy)
        self.assertEqual(result.status, 'STALE')

    def test_bad_boxes_and_clock_fault_without_corrupting_lock(self):
        invalid = [(0, 0, 0, .1), (float('nan'), .1, .1, .1), (.95, .1, .2, .1)]
        for box in invalid:
            with self.subTest(box=box):
                tracker = FaceTracker(.5)
                self.assertEqual(tracker.update([box], 1, 1).status, 'INVALID')
        tracker = FaceTracker(.5)
        tracker.update([(.2, .2, .1, .1)], 2, 2)
        for stamp, now in [(1, 3), (4, 3), (3, float('nan')), (2, 3), (3, 1)]:
            with self.subTest(stamp=stamp, now=now):
                self.assertEqual(tracker.update([], stamp, now).status, 'INVALID')

    def test_reset_allows_centre_selection_again(self):
        tracker = FaceTracker(.5)
        tracker.update([(.1, .1, .1, .1)], 1, 1)
        tracker.reset()
        self.assertEqual(tracker.update([(.7, .7, .1, .1)], 2, 2).status, 'ACQUIRED')

    def test_image_coordinates_right_down_are_positive(self):
        result = FaceTracker(.5).update([(.7, .6, .2, .2)], 1, 1)
        self.assertAlmostEqual(result.error_xy[0], .6)
        self.assertAlmostEqual(result.error_xy[1], .4)

    def test_max_age_must_be_explicit_positive_finite(self):
        for value in [0, -1, float('nan'), float('inf'), True]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                FaceTracker(value)


if __name__ == '__main__':
    unittest.main()
