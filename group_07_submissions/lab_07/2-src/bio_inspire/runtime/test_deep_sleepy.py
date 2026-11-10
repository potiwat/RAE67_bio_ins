import unittest
import test_three_state_behavior
from three_state_behavior import handle_state_key, service_state_outputs, apply_sleepy_yaw
from body_rhythm import BodyRhythmDriver

class DeepSleepyTests(unittest.TestCase):
    def motor(self):
        m,b=test_three_state_behavior.Tests().motor();m.controller.sleepy_deep_rest_enabled=True
        return m,b
    def test_deeper_head_no_gaze_and_guard(self):
        m,b=self.motor();handle_state_key(m,ord('s'))
        self.assertEqual(b.reg[5][42],2969)
        service_state_outputs(m)
        self.assertFalse(m.follow_enabled)
        m.follow_enabled=True;b.calls.clear()
        apply_sleepy_yaw(m,{},20.)
        self.assertEqual(b.calls,[])
    def test_contraction_center_and_breathing_single_owner(self):
        m,b=self.motor();handle_state_key(m,ord('s'))
        start=dict(m.controller.sleepy_body_reference)
        d=BodyRhythmDriver(sleepy_amplitude_deg=2.,time_scale=.5)
        centers=[]
        for n in range(161):
            now=20+n*.05;d.step(m,now)
            b.pos={i:b.reg[i][42] for i in b.pos}
            m.controller.last_rows=b.snapshot()
            if n in (0,80,160):centers.append(dict(d.centers))
        self.assertEqual([x[3] for x in centers],[start[3],start[3]+34,start[3]+68])
        self.assertTrue(all(x[2]==start[2] for x in centers))
        self.assertEqual(d.rhythm.envelope,1.)
        self.assertLessEqual(abs(b.reg[3][42]-d.centers[3]),23)
        m.operator_stopped=True;b.calls.clear();d.step(m,29.)
        self.assertEqual(b.calls,[])
    def test_wake_to_happy_restores_gaze_and_awake_head(self):
        m,b=self.motor();handle_state_key(m,ord('s'))
        b.pos[5]=2969;m.small_happy_trial=True;m.automatic_fsm_enabled=True
        m.happy_speed_raw=750;m.happy_body_acceleration_raw=3
        handle_state_key(m,ord('d'))
        self.assertEqual(m.behavior_trial,'happy')
        self.assertTrue(m.follow_enabled)
        self.assertEqual(m.happy_head_wake_goal,m.controller.normal[5])

    def test_sleepy_after_happy_uses_active_owner_not_old_contracted_center(self):
        m,b=self.motor();m.small_happy_trial=True;m.behavior_trial='happy'
        c=m.controller;c.rhythm_base_reference={2:c.normal[2],3:c.normal[3]+68}
        handle_state_key(m,ord('s'))
        self.assertEqual(c.sleepy_body_reference,{2:c.normal[2],3:c.normal[3]})
        self.assertEqual(c.player_view_reference[3],c.normal[3])
        d=BodyRhythmDriver(sleepy_amplitude_deg=2.,time_scale=.5)
        d.step(m,20.);d.step(m,28.)
        self.assertEqual(d.centers[3],c.normal[3]+68)
