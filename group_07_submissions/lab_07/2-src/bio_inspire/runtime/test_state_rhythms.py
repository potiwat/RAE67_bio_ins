import unittest
from collections import deque
from types import SimpleNamespace
from unittest.mock import Mock
import test_taught_crouch as fixture
from afraid_pose import enter_afraid
from three_state_behavior import handle_state_key

class Tests(unittest.TestCase):
    def test_approved_loaded_normal_offsets_survive_route_completion(self):
        m,b=fixture.Tests().motor();c=m.controller
        c.normal_tolerances.update({2:34,3:34,5:34})
        enter_afraid(m);handle_state_key(m,ord('n'))
        b.pos=dict(c.normal);b.pos[2]+=23;b.pos[3]+=25
        for _ in range(5):c.tick(c.last_tick+.1)
        self.assertEqual(c.pose_route.phase,'complete')
        self.assertNotEqual(c.state,'FAULT')

    def test_base_feedback_uses_approved_tolerance_without_changing_command_window(self):
        from normal_gaze_motor import NormalGaze
        from test_normal_gaze_motor import Bus,NORMAL
        b=Bus();c=NormalGaze(b,NORMAL,NORMAL,normal_tolerances={2:34,3:34,5:34})
        c.state='READY'
        self.assertEqual(c.feedback_window(2),(NORMAL[2]-34,NORMAL[2]+34))
        self.assertEqual(c.windows[2],(NORMAL[2]-22,NORMAL[2]+22))

    def test_router_runs_breathing_in_three_states_and_preserves_special_drivers(self):
        from state_rhythms import StateRhythms
        m,b=fixture.Tests().motor()
        happy=Mock();afraid=Mock();d=StateRhythms(happy,afraid)
        for mode in ('normal','interested','sleepy'):
            m.behavior_trial=mode;b.calls.clear()
            for n in range(61):d.step(m,20.+n*.05+{'normal':0,'interested':4,'sleepy':8}[mode])
            self.assertTrue(any(i in (2,3) and a==42 for i,a,q in b.calls))
            self.assertEqual(d.mode,mode)
            self.assertIs(d.rhythm,d.breathing.rhythm)
        m.behavior_trial='happy';b.calls.clear();d.step(m,33.)
        self.assertEqual(b.calls,[]);self.assertIs(d.rhythm,happy.rhythm)
        m.behavior_trial='afraid';d.step(m,33.05)
        self.assertIs(d.rhythm,afraid.rhythm)

    def test_router_blocks_base_outputs_on_transition_stop_and_fault(self):
        from state_rhythms import StateRhythms
        m,b=fixture.Tests().motor();d=StateRhythms(Mock(),Mock())
        m.behavior_trial='normal';d.step(m,20.);d.step(m,20.1)
        m.behavior_trial='normal_transition';b.calls.clear();d.step(m,20.2)
        self.assertEqual(b.calls,[])
        for state in ('FAULT','WAIT_TOF','NORMAL_STARTUP'):
            m.behavior_trial='normal';m.controller.state=state;b.calls.clear();d.step(m,20.3)
            self.assertEqual(b.calls,[])

    def test_urgent_stop_prevents_base_cpg_writes(self):
        from state_rhythms import StateRhythms
        m,b=fixture.Tests().motor();d=StateRhythms(Mock(),Mock())
        m.behavior_trial='normal';d.step(m,20.);d.step(m,21.)
        m.urgent_stop.set();b.calls.clear();d.step(m,22.)
        self.assertEqual(b.calls,[])

    def test_normal_return_keeps_yaw_enabled_in_combined_profile(self):
        m,b=fixture.Tests().motor();m.all_states_cpg_enabled=True;m.yaw_follow_enabled=True
        handle_state_key(m,ord('n'))
        self.assertTrue(m.yaw_follow_enabled)

    def test_real_decoders_emit_cpg_commands_in_all_five_states(self):
        from state_rhythms import StateRhythms
        from small_happy_trial import SmallHappyTrial
        from afraid_rhythm import AfraidRhythm
        from visual_servo import VisualServo
        for mode in ('normal','interested','sleepy','happy','afraid'):
            with self.subTest(mode=mode):
                m,b=fixture.Tests().motor();c=m.controller;c.set_direction(1)
                m.visual=VisualServo(c.yaw_window[0],c.yaw_window[1],399.,296.,.25,6.,160.,.5)
                m.happy_yaw_base=c.normal[1];m.happy_body_acceleration_raw=3
                if mode=='afraid':
                    enter_afraid(m);c.tick(30.)
                    for _ in range(3):
                        b.pos={i:b.reg[i][42] for i in range(1,6)};c.tick(c.last_tick+.1)
                    self.assertEqual(c.pose_route.phase,'held')
                else:m.behavior_trial=mode
                d=StateRhythms(SmallHappyTrial(time_scale=.75),AfraidRhythm())
                seen=[];b.calls.clear()
                for n in range(201):
                    now=31.+n*.05
                    m.latest_result=dict(observation=dict(status='TRACKING',captured_s=now,source_id=n),intent=dict(mode='FOLLOW',error_xy=(0.,0.)))
                    d.step(m,now);seen.append(b.reg[2][42])
                self.assertGreater(max(seen)-min(seen),3)
                allowed=(1,2,3) if mode=='happy' else (2,3)
                self.assertTrue(all(i in allowed and a==42 for i,a,q in b.calls))
