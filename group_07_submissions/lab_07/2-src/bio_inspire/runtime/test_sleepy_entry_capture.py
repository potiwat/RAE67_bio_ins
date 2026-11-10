import unittest
from collections import deque
from camera_motor import CameraMotor
class Tests(unittest.TestCase):
    def test_sleepy_entry_kept_even_after_long_idle_tail(self):
        m=CameraMotor.__new__(CameraMotor);m.trace=deque(maxlen=600)
        for n in range(2000):m._record_trace(dict(time_s=100.+n*.05,behavior='sleepy',sleepy_contraction_start_s=100.,rows=[]))
        self.assertLessEqual(len(m.sleepy_entry_trace),300)
        self.assertEqual(m.sleepy_entry_trace[0]['time_s'],100.)
        self.assertLessEqual(m.sleepy_entry_trace[-1]['time_s'],112.)
        self.assertGreater(m.trace[0]['time_s'],112.)
