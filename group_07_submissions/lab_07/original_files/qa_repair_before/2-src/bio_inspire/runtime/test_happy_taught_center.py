import unittest
import test_small_happy_trial as fixture
from small_happy_trial import SmallHappyTrial
from three_state_behavior import handle_state_key, _small_happy_speed


class Tests(unittest.TestCase):
    def test_taught_transport_groups_roll_without_extra_unicast(self):
        m,b=self.motor();d=SmallHappyTrial(expanded=True,taught_center=True)
        b.sync_position_trial=True;packets=[]
        def sync(goals,cancelled):
            packets.append(dict(goals))
            for i,q in goals.items():b.reg[i][42]=q
            return dict(verified_ids=list(goals))
        b.sync_positions=sync;b.calls.clear()
        for n in range(5):
            now=n*.1;m.latest_result['observation']['captured_s']=now;d.step(m,now)
        self.assertTrue(packets)
        self.assertTrue(all(set(g)=={1,2,3,4} for g in packets))
        self.assertFalse(any(i==4 and a==42 for i,a,q in b.calls))

    def motor(self):
        m,b,_=fixture.Tests().fixture()
        m.automatic_fsm_enabled=True;m.happy_expanded_trial=True
        m.happy_taught_center_trial=True;m.happy_body_acceleration_raw=3
        from visual_servo import VisualServo
        from camera_motor import CameraMotor
        m.pitch_visual=VisualServo(2355,2764,400.,100.,.25,6.,90.,.5)
        m._reset_pitch=CameraMotor._reset_pitch.__get__(m)
        m.behavior_trial='normal';m.controller.last_rows=b.snapshot()
        handle_state_key(m,ord('d'))
        return m,b

    def test_taught_center_full_counterroll_slow_cpg_and_stop(self):
        m,b=self.motor();d=SmallHappyTrial(expanded=True,taught_center=True)
        seen=[];prior=None
        d.rhythm.set_ahm_phi(.13) # fastest approved mapping must still respect roll dynamics
        for n in range(1201):
            now=n*.05;m.latest_result['observation']['captured_s']=now
            b.calls.clear();d.step(m,now)
            self.assertTrue(all(a==42 and i in (1,2,3,4) for i,a,q in b.calls))
            goals=d.rhythm.status()['command_targets_raw']
            for i in (2,3,4):
                lo,hi=d.limiters[i].limits.low,d.limiters[i].limits.high
                self.assertTrue(lo<=goals[i]<=hi)
            if n>300:seen.append(goals)
            if prior is not None:
                self.assertLessEqual(abs(d.limiters[4].velocity-prior),d.limiters[4].limits.acceleration*.05+1e-7)
            prior=d.limiters[4].velocity
            b.pos={i:b.reg[i][42] for i in b.pos};m.controller.last_rows=b.snapshot()
        self.assertLess(min(q[4] for q in seen),1680)
        self.assertGreater(max(q[4] for q in seen),2340)
        for i,center in ((2,2654),(3,3095)):
            self.assertLess(min(q[i] for q in seen),center-40)
            self.assertGreater(max(q[i] for q in seen),center+40)
        self.assertAlmostEqual(d.rhythm.status()['requested_period_s_approx'],22.8)
        m.urgent_stop.set();b.calls.clear();d.step(m,60.1);self.assertEqual(b.calls,[])

    def test_happy_only_pitch_window_restores_without_losing_return_guard(self):
        m,b=self.motor();c=m.controller
        self.assertEqual(c.active_pitch_window(),(2070,2764))
        self.assertLessEqual(c.feedback_window(5)[0],2070)
        _small_happy_speed(m,False)
        self.assertEqual(c.active_pitch_window(),c.pitch_window)
        self.assertLessEqual(c.feedback_window(5)[0],2070)
        self.assertTrue(c.sleepy_return_pending)

    def test_plain_profile_and_constructor_remain_unchanged(self):
        m,b,_=fixture.Tests().fixture();d=SmallHappyTrial(expanded=True,roll_deg=8)
        self.assertEqual(d.roll_ticks,91)
        self.assertFalse(getattr(m,'happy_taught_center_trial',False))

    def test_real_pitch_visual_and_body_plan_can_reach_new_reference(self):
        from interested_head import InterestedHead
        m,b=self.motor()
        self.assertEqual((m.pitch_visual.low,m.pitch_visual.high),(2070,2764))
        h=InterestedHead(m.pitch_visual,m.controller.last_rows,20.,native_posture=True)
        target=h.step(m.controller.last_rows,None,20.05,1,body_target={2:2654,3:3095})
        self.assertEqual(target,2164) # current measured reference, not un-aimed taught ID5

    def test_sleepy_exit_does_not_stack_twelve_degree_fold_on_high_center(self):
        from body_rhythm import BodyRhythmDriver
        m,b=self.motor();c=m.controller
        c.sleepy_deep_rest_enabled=True;c.sleepy_native_fold_enabled=True
        c.sleepy_native_fold_degrees=12;c.sleepy_native_fold_speed_raw=1
        d=SmallHappyTrial(expanded=True,taught_center=True)
        for n in range(401):
            now=n*.05;m.latest_result['observation']['captured_s']=now;d.step(m,now)
            b.pos={i:b.reg[i][42] for i in b.pos};c.last_rows=b.snapshot()
        handle_state_key(m,ord('s'))
        self.assertEqual(b.reg[4][42],c.normal[4])
        self.assertEqual(m.behavior_trial,'sleepy_transition')
        self.assertFalse(b.reg[5][42]>c.normal[5]+200)
        b.pos={i:b.reg[i][42] for i in b.pos};c.last_rows=b.snapshot()
        handle_state_key(m,ord('s'))
        self.assertEqual(m.behavior_trial,'sleepy')
        self.assertEqual(c.behavior_joint_windows[4],(c.normal[4]-c.normal_tolerances[4],c.normal[4]+c.normal_tolerances[4]))
        BodyRhythmDriver(sleepy_amplitude_deg=2.).step(m,21.)
        self.assertEqual(c.sleepy_native_fold['target'],c.normal[3]+137)
        self.assertFalse(getattr(c.pose_route,'force_normal',False) if getattr(c,'pose_route',None) else False)


if __name__=='__main__':unittest.main()
