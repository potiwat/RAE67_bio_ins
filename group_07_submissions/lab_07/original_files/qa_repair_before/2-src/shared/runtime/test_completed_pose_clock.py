import math,unittest
from types import SimpleNamespace
from unittest.mock import Mock
from pose_route import PoseRoute

class Tests(unittest.TestCase):
    def route(self,progress):
        r=PoseRoute.__new__(PoseRoute)
        r.c=SimpleNamespace(control_now_s=21.37)
        r.return_last_time=20.;r.return_started=19.5;r.return_duration=.5
        r.return_progress=progress;r.send=Mock()
        return r
    def test_completed_target_waiting_for_feedback_does_not_recheck_active_motion_gap(self):
        r=self.route(1.)
        self.assertTrue(r._step_coordinated_return())
        r.send.assert_not_called()
    def test_active_motion_still_rejects_long_gap(self):
        r=self.route(.9)
        with self.assertRaises(ValueError):r._step_coordinated_return()
    def test_completed_motion_still_rejects_invalid_clock(self):
        for now in (19.,float('nan')):
            r=self.route(1.);r.c.control_now_s=now
            with self.assertRaises(ValueError):r._step_coordinated_return()
