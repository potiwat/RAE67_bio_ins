"""Supervised Happy-only geometry observation, not metric-Z control."""
import unittest
from types import SimpleNamespace
import test_happy_taught_center as fixture
from small_happy_trial import SmallHappyTrial
from camera_motor import CameraMotor
from automatic_fsm import AutomaticFSM


class Tests(unittest.TestCase):
    def test_six_degree_candidate_only_expands_positive_probe2_command_bound(self):
        m,b=fixture.Tests().motor();m.happy_height_probe_trial=True
        m.happy_height_probe_step_deg=6;m.happy_height_probe_offset_ticks=0
        d=SmallHappyTrial(expanded=True,taught_center=True,fast_trial=True,height_probe=True,probe_step_deg=6)
        for n in range(241):
            now=n*.05;m.latest_result['observation']['captured_s']=now
            if n==120:CameraMotor._key(m,ord('p'))
            d.step(m,now);b.pos={i:b.reg[i][42] for i in b.pos};m.controller.last_rows=b.snapshot()
        self.assertEqual(b.reg[2][42],2722)
        self.assertEqual(d.limiters[2].limits.low,2603)
        self.assertEqual(d.limiters[2].limits.high,2722)
        self.assertEqual((d.limiters[3].limits.low,d.limiters[3].limits.high),(3044,3146))
        self.assertEqual(b.reg[3][42],3095);self.assertEqual(b.reg[4][42],1997)
        with self.assertRaises(ValueError):SmallHappyTrial(expanded=True,taught_center=True,fast_trial=True,probe_step_deg=6)

    def test_actual_apply_compensates_same_body_target_instead_of_fighting_it(self):
        m,b=fixture.Tests().motor();c=m.controller
        m.happy_height_probe_trial=True;m.happy_height_probe_offset_ticks=0
        m.native_posture_compensation=True;m.pitch_direction=1
        m.interested_pitch_lead_ticks=34;m.interest_body_pitch_compensation=True
        d=SmallHappyTrial(expanded=True,taught_center=True,fast_trial=True,height_probe=True)
        baseline=None
        for n in range(241):
            now=n*.05;m.latest_result['observation']['captured_s']=now
            if n==130:CameraMotor._key(m,ord('p'))
            d.step(m,now);m._apply(m.latest_result,now)
            if n==120:baseline=b.reg[5][42]-b.reg[2][42]+b.reg[3][42]
            if n>=130:self.assertAlmostEqual(b.reg[5][42]-b.reg[2][42]+b.reg[3][42],baseline,delta=1)
            b.pos={i:b.reg[i][42] for i in b.pos};c.last_rows=b.snapshot()
        self.assertEqual(b.reg[2][42],2688)

    def test_probe_pauses_dance_and_moves_only_small_body2_offset(self):
        m,b=fixture.Tests().motor();m.happy_height_probe_trial=True
        m.happy_height_probe_offset_ticks=0
        d=SmallHappyTrial(expanded=True,taught_center=True,fast_trial=True,height_probe=True)
        def step(now):
            m.latest_result['observation']['captured_s']=now;d.step(m,now)
            b.pos={i:b.reg[i][42] for i in b.pos};m.controller.last_rows=b.snapshot()
        for n in range(121):step(n*.05)
        baseline={i:b.reg[i][42] for i in (2,3,4)}
        self.assertEqual(baseline,{2:2654,3:3095,4:1997})
        phase=d.rhythm.decoder_phase_cycles
        CameraMotor._key(m,ord('p'))
        for n in range(121,241):step(n*.05)
        self.assertEqual(b.reg[2][42],2688)
        self.assertEqual({i:b.reg[i][42] for i in (3,4)},{3:3095,4:1997})
        self.assertGreater(d.rhythm.decoder_phase_cycles,phase)
        self.assertEqual(m.posture_body_plan['goals'][2],2688)
        CameraMotor._key(m,ord('o'))
        for n in range(241,361):step(n*.05)
        self.assertEqual(b.reg[2][42],2654)
        m.operator_stopped=True;b.calls.clear();CameraMotor._key(m,ord('p'));step(18.1)
        self.assertEqual(m.happy_height_probe_offset_ticks,0)
        self.assertEqual(b.calls,[])

    def test_only_probe_happy_suspends_timeout_other_states_unchanged(self):
        m,b=fixture.Tests().motor();m.happy_height_probe_trial=True
        f=AutomaticFSM(motion_aware=True);f.fsm=SimpleNamespace(state='happy');f.applied='happy'
        m.rhythm_view_cache=dict(small_happy='running',envelope=1.)
        self.assertFalse(f.timer_ready(m))
        m.happy_height_probe_trial=False;self.assertTrue(f.timer_ready(m))

    def test_probe_key_cannot_move_normal_or_faulted_owner(self):
        m,b=fixture.Tests().motor();m.happy_height_probe_trial=True
        m.happy_height_probe_offset_ticks=0;m.behavior_trial='normal';b.calls.clear()
        CameraMotor._key(m,ord('p'));self.assertEqual(m.happy_height_probe_offset_ticks,0)
        m.behavior_trial='happy';m.controller.state='FAULT'
        CameraMotor._key(m,ord('p'));self.assertEqual(m.happy_height_probe_offset_ticks,0)
        self.assertEqual(b.calls,[])
