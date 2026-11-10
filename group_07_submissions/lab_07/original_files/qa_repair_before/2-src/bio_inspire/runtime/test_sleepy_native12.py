import unittest
import test_deep_sleepy as fixture
from three_state_behavior import handle_state_key
from body_rhythm import BodyRhythmDriver
class Tests(unittest.TestCase):
    def test_twelve_degrees_from_actual_entry_and_speed1(self):
        m,b=fixture.DeepSleepyTests().motor();c=m.controller;c.sleepy_native_fold_enabled=True
        c.sleepy_native_fold_degrees=12;c.sleepy_native_fold_speed_raw=1
        b.pos[3]=2764;c.last_rows=b.snapshot()
        handle_state_key(m,ord('s'));d=BodyRhythmDriver(sleepy_amplitude_deg=2.);b.calls.clear();d.step(m,20.)
        self.assertEqual(b.reg[3][46],1)
        self.assertEqual(b.reg[3][42],2764+137)
        self.assertGreaterEqual(c.behavior_joint_windows[3][1],2764+137+23)
        self.assertLessEqual(c.behavior_joint_windows[3][0],2764)
        b.calls.clear();d.step(m,21.)
        self.assertFalse(any(i==3 and a==42 for i,a,q in b.calls))

    def test_exact_approved_parameter_pairs_only(self):
        from sleepy_trial import sleepy_fold_values
        self.assertEqual(sleepy_fold_values(6,9),(68,9))
        self.assertEqual(sleepy_fold_values(12,1),(137,1))
        for pair in ((12,9),(6,1),(True,9),(13,1)):
            with self.assertRaises(ValueError):sleepy_fold_values(*pair)
