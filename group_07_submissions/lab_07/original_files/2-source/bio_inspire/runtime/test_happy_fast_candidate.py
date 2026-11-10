"""PC-only verification of a candidate awaiting operator confirmation."""
import unittest
from small_happy_trial import SmallHappyTrial
from three_state_behavior import _small_happy_speed
from normal_gaze_motor import happy_extra_acceleration_allowed
import test_happy_taught_center as fixture


class Tests(unittest.TestCase):
    def test_head_bias_fades_with_body_and_stays_in_existing_gaze_window(self):
        from interested_head import InterestedHead
        from visual_servo import VisualServo
        d=SmallHappyTrial(expanded=True,taught_center=True,fast_trial=True,head_up_deg=5)
        m,b=fixture.Tests().motor()
        for n in range(81):
            now=n*.05;m.latest_result['observation']['captured_s']=now;d.step(m,now)
            bias=m.posture_body_plan['head_bias_ticks']
            self.assertTrue(-57<=bias<=0)
            if n==0:self.assertEqual(bias,0)
        self.assertEqual(bias,-57)
        rows=[dict(id=i,position_raw=m.controller.normal[i]) for i in (2,3,5)]
        h=InterestedHead(VisualServo(2070,2764,400.,100.,.25,6.,90.,.5),rows,0.,native_posture=True)
        q=h.step(rows,None,.05,1,body_target={2:2654,3:3095},reference_bias_ticks=-57)
        self.assertEqual(q,2107)
        h.step(rows,None,.1,2,body_target={2:2603,3:3146},reference_bias_ticks=-57)
        self.assertGreaterEqual(h.visual.position,2070)

    def test_six_second_candidate_changes_only_phase_rate(self):
        d=SmallHappyTrial(expanded=True,taught_center=True,fast_trial=True,fast_period_s=6.)
        self.assertAlmostEqual(3.8*d.phase_divisor,6.)
        self.assertEqual(d.entry_seconds,4.)
        self.assertEqual(d.body_ticks,51)
        for value in (True,0.,4.,9.):
            with self.assertRaises(ValueError):SmallHappyTrial(expanded=True,taught_center=True,fast_trial=True,fast_period_s=value)
        with self.assertRaises(ValueError):SmallHappyTrial(expanded=True,taught_center=True,fast_period_s=6.)

    def test_five_second_profile_preserves_transport_geometry_and_limits(self):
        from taught_happy import validate
        validate(dict(happy_taught_center_trial=True,happy_taught_fast_trial=True,
                      happy_taught_fast_period_s=5.,small_happy_expanded_trial=True,
                      automatic_fsm_enabled=True,native_posture_compensation=True))
        d=SmallHappyTrial(expanded=True,taught_center=True,fast_trial=True,fast_period_s=5.)
        self.assertAlmostEqual(3.8*d.phase_divisor,5.)
        m,b=fixture.Tests().motor();b.sync_position_trial=True;packets=[]
        def sync(goals,cancelled):
            packets.append(dict(goals))
            for i,q in goals.items():b.reg[i][42]=q
            return dict(verified_ids=list(goals))
        b.sync_positions=sync;d.rhythm.set_ahm_phi(.13)
        for n in range(801):
            now=n*.05;m.latest_result['observation']['captured_s']=now;d.step(m,now)
            report=d.rhythm.status()
            requested=report['requested_targets_float']
            # Both body joints use the same shared phase and normalized displacement.
            if now>=4.:self.assertAlmostEqual(requested[2]-2654,requested[3]-3095)
            for i,f in d.limiters.items():
                self.assertTrue(f.limits.low<=f.position<=f.limits.high)
                self.assertLessEqual(abs(f.velocity),f.limits.speed+1e-7)
            b.pos={i:b.reg[i][42] for i in b.pos};m.controller.last_rows=b.snapshot()
        self.assertTrue(packets)
        self.assertTrue(all(set(p)=={1,2,3,4} for p in packets))
        self.assertEqual(d.entry_seconds,4.)

    def test_new_acceleration_is_explicit_ram_only_and_restores(self):
        m,b=fixture.Tests().motor();m.happy_taught_fast_trial=True
        _small_happy_speed(m,True)
        self.assertEqual([b.reg[i][41] for i in (2,3,4,5)],[3,3,6,3])
        self.assertTrue(b.happy_fast_acceleration_trial)
        _small_happy_speed(m,False)
        self.assertEqual([b.reg[i][41] for i in (2,3,4,5)],[1,1,1,1])
        self.assertFalse(b.happy_fast_acceleration_trial)

    def test_guard_never_authorizes_other_ids_values_or_disabled_profile(self):
        for sid in range(1,6):
            for address in (18,21,40,41,42,46):
                for value in (1,3,6,254):
                    expected=address==41 and (sid,value) in ((4,6),(5,3))
                    self.assertEqual(happy_extra_acceleration_allowed(sid,address,value,True),expected)
                    self.assertFalse(happy_extra_acceleration_allowed(sid,address,value,False))

    def test_fast_decoder_keeps_geometry_and_bounded_roll_at_high_hormone(self):
        m,b=fixture.Tests().motor();m.happy_taught_fast_trial=True
        d=SmallHappyTrial(expanded=True,taught_center=True,fast_trial=True)
        d.rhythm.set_ahm_phi(.13)
        seen=[]
        for n in range(601):
            now=n*.05;m.latest_result['observation']['captured_s']=now;d.step(m,now)
            goals=d.rhythm.status()['command_targets_raw']
            self.assertLessEqual(abs(d.limiters[4].velocity),d.limiters[4].limits.speed)
            self.assertAlmostEqual(d.limiters[4].limits.acceleration,m.visual.max_acceleration*2)
            if now>8.:seen.append(goals)
            b.pos={i:b.reg[i][42] for i in b.pos};m.controller.last_rows=b.snapshot()
        self.assertEqual(d.entry_seconds,4.)
        self.assertAlmostEqual(d.rhythm.status()['requested_period_s_approx'],8.)
        self.assertLess(min(q[4] for q in seen),1680);self.assertGreater(max(q[4] for q in seen),2340)
        self.assertTrue(all(1636<=q[4]<=2383 and 2603<=q[2]<=2705 and 3044<=q[3]<=3146 for q in seen))
