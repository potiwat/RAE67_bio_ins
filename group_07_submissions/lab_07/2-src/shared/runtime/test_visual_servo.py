import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from visual_servo import VisualServo


class CenteringTests(unittest.TestCase):
    def controller(self):
        return VisualServo(0,100,20,40,1,2,100,.5)  # synthetic units, not robot tuning
    def test_persistent_error_keeps_turning_instead_of_settling_at_normal_offset(self):
        c=self.controller();c.reset(50,0)
        first=c.step(50,.1,1)
        for i in range(2,11):last=c.step(50,i/10,i)
        self.assertGreater(last,first+5)
    def test_centred_face_keeps_new_heading_after_deceleration(self):
        c=self.controller();c.reset(70,0)
        for i in range(1,6):c.step(0,i/10,i)
        self.assertEqual(c.position,70)
        self.assertEqual(c.velocity,0)
    def test_acceleration_and_speed_both_limited(self):
        c=self.controller();c.reset(50,0)
        c.step(100,.1,1)
        self.assertAlmostEqual(c.velocity,4)
        self.assertAlmostEqual(c.position,50.2)
        for i in range(2,11):c.step(100,i/10,i)
        self.assertLessEqual(c.velocity,20)
    def test_brief_face_loss_decelerates_instead_of_resetting_heading(self):
        c=self.controller();c.reset(50,0);c.step(100,.1,1)
        c.step(100,.2,2);previous=c.position
        after=c.step(None,.3,3)
        self.assertGreater(after,previous)
        self.assertAlmostEqual(c.velocity,4)
        for i in range(4,7):c.step(None,i/10,i)
        self.assertEqual(c.velocity,0)
    def test_range_limit_does_not_accumulate_velocity_windup(self):
        c=self.controller();c.reset(99,0)
        for i in range(1,11):c.step(100,i/10,i)
        self.assertEqual(c.position,100);self.assertEqual(c.velocity,0)
    def test_duplicate_measurement_does_not_filter_same_frame_repeatedly(self):
        c=VisualServo(0,100,20,400,.25,2,100,.5);c.reset(50,0)
        c.step(100,.1,1);v=c.velocity
        c.step(100,.2,1)
        self.assertEqual(c.velocity,v)
    def test_long_control_gap_is_rejected_not_integrated_as_jump(self):
        c=self.controller();c.reset(50,0)
        with self.assertRaises(ValueError):c.step(100,2,1)

    def test_entering_deadband_does_not_erase_filter_history(self):
        c=VisualServo(0,100,20,40,.25,6,100,.5);c.reset(50,0)
        c.step(30,.05,1)
        old=c.filtered_error
        c.step(5,.10,2)
        self.assertAlmostEqual(c.filtered_error,.25*5+.75*old)

    def test_approaching_range_limit_brakes_without_acceleration_jump(self):
        c=self.controller();c.reset(50,0)
        previous_velocity=0
        for i in range(1,100):
            c.step(100,i*.05,i)
            self.assertLessEqual(abs(c.velocity-previous_velocity),40*.05+1e-8)
            self.assertLessEqual(c.position,100)
            previous_velocity=c.velocity


if __name__=='__main__':unittest.main()
