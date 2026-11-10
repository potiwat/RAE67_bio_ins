import unittest
from camera_motor import diagnostic_trace_capacity
class Tests(unittest.TestCase):
    def test_bounded_long_capture(self):
        self.assertEqual(diagnostic_trace_capacity(600),600)
        for n in (40,180):self.assertEqual(diagnostic_trace_capacity(n),n)
        for n in (True,601,100000,-1):
            with self.assertRaises(ValueError):diagnostic_trace_capacity(n)
    def test_short_all_state_pilot_history_is_bounded(self):
        self.assertEqual(diagnostic_trace_capacity(2400),2400)
        with self.assertRaises(ValueError):diagnostic_trace_capacity(2401)
