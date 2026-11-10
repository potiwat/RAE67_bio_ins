import math
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
import threading
import test_three_state_behavior as behavior_fixture
from three_state_behavior import handle_state_key
from body_rhythm import BodyRhythm

class Tests(unittest.TestCase):
    def test_fresh_face_loss_keeps_cpg_continuous_without_restarting_fade(self):
        m,b,d=self.fixture()
        for n in range(41):
            now=n*.1;m.latest_result['observation']['captured_s']=now;d.step(m,now)
        began=d.began;limiter=d.limiters[2];positions=[]
        for n in range(41,91):
            now=n*.1
            m.latest_result['observation'].update(status='LOST',captured_s=now)
            m.latest_result['intent']=dict(mode='SEARCH',error_xy=None)
            d.step(m,now);positions.append(b.reg[2][42])
            self.assertIs(d.limiters[2],limiter)
            self.assertEqual(d.began,began)
            if now>4.5:self.assertEqual(d.rhythm.status()['gaze_mode'],'face_missing_hold')
        self.assertGreater(max(positions)-min(positions),30)
        m.urgent_stop.set();b.calls.clear();d.step(m,9.1);self.assertEqual(b.calls,[])

    def test_motion_evidence_survives_long_inactive_tail_and_remains_bounded(self):
        from camera_motor import CameraMotor
        from collections import deque
        m=CameraMotor.__new__(CameraMotor);m.trace=deque(maxlen=180);m.small_happy_trial=True
        for n in range(200):m._record_trace(dict(time_s=n,state='READY',happy_output_mode='running'))
        for n in range(1000):m._record_trace(dict(time_s=200+n,state='READY',happy_output_mode='paused_no_recent_face'))
        self.assertEqual(len(m.trace),180)
        self.assertEqual(len(m.happy_motion_trace),180)
        self.assertEqual(m.happy_motion_trace[0]['time_s'],20)
        self.assertEqual(m.happy_motion_trace[-1]['time_s'],199)

    def test_approved_happy750_reaches_all_five_and_normal_restores400(self):
        m,b=behavior_fixture.Tests().motor();m.small_happy_trial=True
        m.state_leds_enabled=False;m.happy_speed_raw=750;m.happy_body_acceleration_raw=3
        b.calls.clear();handle_state_key(m,ord('d'))
        self.assertTrue(all(b.reg[i][46]==750 for i in range(1,6)))
        self.assertTrue(b.happy_speed750_trial)
        self.assertEqual([b.reg[i][41] for i in (2,3)],[3,3])
        handle_state_key(m,ord('n'))
        self.assertTrue(all(b.reg[i][46]==400 for i in range(1,6)))
        self.assertFalse(b.happy_speed750_trial)
        self.assertEqual([b.reg[i][41] for i in (2,3)],[1,1])

    def test_happy_body_limiter_uses_approved_acceleration3_without_expanding_bounds(self):
        m,b,d=self.fixture();m.happy_body_acceleration_raw=3
        for n in range(61):
            now=n*.1;m.latest_result['observation']['captured_s']=now;d.step(m,now)
            for sid in (2,3):
                self.assertEqual(d.limiters[sid].limits.acceleration,m.visual.max_acceleration)
                self.assertLessEqual(abs(b.reg[sid][42]-m.controller.normal[sid]),34)

    def test_faster_happy_uses_retained_cpg_updates_and_approved_time_scale(self):
        from small_happy_trial import SmallHappyTrial
        d=SmallHappyTrial(time_scale=.75)
        d.rhythm.advance(0.,True);d.rhythm.advance(1.,True)
        self.assertEqual(d.rhythm.updates,15)
        self.assertEqual(d.rhythm.phi,.1)
        self.assertEqual(d.rhythm.dt_s,.05)

    def test_stop_prevents_happy_speed_writes(self):
        from three_state_behavior import _small_happy_speed
        m,b=behavior_fixture.Tests().motor();m.happy_speed_raw=750
        m.urgent_stop.set();b.calls.clear()
        with self.assertRaises(RuntimeError):_small_happy_speed(m,True)
        self.assertEqual(b.calls,[])

    def fixture(self):
        from small_happy_trial import SmallHappyTrial
        m,b=behavior_fixture.Tests().motor();m.small_happy_trial=True;m.state_leds_enabled=False
        m.yaw_follow_enabled=False;m.touch_required_for_happy=True;m.touch_dispatch_active=True
        handle_state_key(m,ord('d'));b.calls.clear()
        m.latest_result=dict(state='happy',observation=dict(status='TRACKING',captured_s=0.,error_xy=(0.,0.)),intent=dict(mode='FOLLOW',error_xy=(0.,0.)))
        from visual_servo import VisualServo
        m.controller.yaw_window=(m.controller.normal[1]-341,m.controller.normal[1]+341)
        m.visual=VisualServo(m.controller.yaw_window[0]+13,m.controller.yaw_window[1]-13,8*.732*6*4096/360,3*8.7*4096/360,.25,6.,160.,.5)
        b.hold_actual=lambda sid:b.write(sid,42,b.pos[sid].to_bytes(2,'little'))
        m.controller.set_direction(1)
        return m,b,SmallHappyTrial()
    def test_model_phase_handles_skipped_owner_cycles_without_reset(self):
        r=BodyRhythm(phi=.1,time_scale=.5);r.advance(0.,True)
        a=r.phase_cycles;r.advance(1.,True)
        self.assertGreater(r.phase_cycles,a);self.assertEqual(r.updates,10)
    def test_symmetric_lobes_bounded_coordinated_body_and_no_head_writes(self):
        m,b,d=self.fixture();values=[]
        for n in range(601):
            now=n*.05;m.latest_result['observation']['captured_s']=now
            b.calls.clear();d.step(m,now)
            self.assertTrue(all(i in (1,2,3) and a==42 for i,a,_ in b.calls))
            self.assertEqual(len([i for i,a,_ in b.calls]),len(set(i for i,a,_ in b.calls)))
            q={i:b.reg[i][42]-m.controller.normal[i] for i in (1,2,3)}
            self.assertTrue(all(abs(v)<=34 for v in q.values()))
            self.assertEqual(q[2],q[3])
            if now>4:values.append(q)
        self.assertLess(min(q[1] for q in values),-30);self.assertGreater(max(q[1] for q in values),30)
        self.assertLess(min(q[2] for q in values),-30);self.assertGreater(max(q[2] for q in values),30)
        self.assertEqual(b.reg[4][42],m.controller.normal[4])
    def test_lost_or_stale_pauses_body_and_stop_prevents_all_writes(self):
        m,b,d=self.fixture()
        for n in range(61):
            now=n*.05;m.latest_result['observation']['captured_s']=now;d.step(m,now)
        phase=d.rhythm.phase_cycles
        m.latest_result['observation'].update(status='LOST',captured_s=3.7);b.calls.clear();d.step(m,3.7)
        self.assertEqual(b.calls,[]);self.assertGreater(d.rhythm.phase_cycles,phase)
        m.latest_result['observation'].update(status='TRACKING',captured_s=2.);d.step(m,3.8);self.assertEqual(b.calls,[])
        m.urgent_stop.set();m.latest_result['observation']['captured_s']=4.;d.step(m,4.);self.assertEqual(b.calls,[])
    def test_touch_only_normal_entry_and_led_stays_off(self):
        m,b=behavior_fixture.Tests().motor();m.small_happy_trial=True;m.state_leds_enabled=False
        m.touch_required_for_happy=True;m.touch_dispatch_active=False
        handle_state_key(m,ord('d'));self.assertNotEqual(m.behavior_trial,'happy')
        m.touch_dispatch_active=True;m.behavior_trial='interested';b.calls.clear()
        handle_state_key(m,ord('d'));self.assertEqual(b.calls,[])
        self.assertIn('Normal',m.tune_status)
        m.behavior_trial='normal';handle_state_key(m,ord('d'))
        m.led_ring.happy.assert_not_called()
    def test_stop_mid_frame_cancels_remaining_commands(self):
        m,b,d=self.fixture();d.step(m,0.)
        for stamp in (.2,.4):m.latest_result['observation']['captured_s']=stamp;d.step(m,stamp)
        m.latest_result['observation']['captured_s']=.5
        original=b.write
        def write(i,a,data):
            original(i,a,data)
            if a==42:m.urgent_stop.set()
        b.write=write;b.calls.clear();d.step(m,.5)
        self.assertLessEqual(len(b.calls),1)

    def test_invalid_face_cannot_start_body_motion(self):
        m,b,d=self.fixture();m.latest_result['intent']['error_xy']=(float('nan'),0.)
        b.calls.clear();d.step(m,0.);d.step(m,.2);self.assertEqual(b.calls,[])
    def test_profile_rejects_other_yaw_writer_and_leds(self):
        import json
        from pathlib import Path
        from small_happy_trial import validate_small_happy_profile
        cfg=json.loads((Path(__file__).resolve().parents[1]/'hardware/head4_gaze_probe.json').read_text())
        validate_small_happy_profile(cfg)
        for field in ('yaw_follow_enabled','state_leds_enabled','cpg_trial_enabled','head4_probe_enabled'):
            invalid={**cfg,field:True}
            with self.assertRaises(ValueError):validate_small_happy_profile(invalid)

    def test_entry_blends_from_acknowledged_yaw_hold_goal(self):
        m,b,d=self.fixture();m.happy_yaw_base=m.controller.normal[1]+9
        b.reg[1][42]=m.happy_yaw_base
        d.step(m,0.)
        self.assertEqual(b.reg[1][42],m.happy_yaw_base)
    def test_face_resume_does_not_jump_back_to_normal(self):
        m,b,d=self.fixture()
        for n in range(81):
            now=n*.05;m.latest_result['observation']['captured_s']=now;d.step(m,now)
        before={i:b.reg[i][42] for i in (1,2,3)}
        m.latest_result['observation'].update(status='LOST',captured_s=4.7);d.step(m,4.7)
        m.latest_result['observation'].update(status='TRACKING',captured_s=5.);d.step(m,5.)
        self.assertEqual(before,{i:b.reg[i][42] for i in before})

    def test_report_offsets_match_new_correlated_body_commands(self):
        m,b,d=self.fixture()
        for n in range(81):
            now=n*.05;m.latest_result['observation']['captured_s']=now;d.step(m,now)
        status=d.rhythm.status()
        self.assertEqual(status['active_joint_ids'],[1,2,3])
        for sid in (1,2,3):
            self.assertAlmostEqual(status['command_offsets_deg'][sid],(b.reg[sid][42]-m.controller.normal[sid])*360/4096)

    def test_sync_mode_sends_one_frame_only_and_commits_cache_after_confirmation(self):
        m,b,d=self.fixture();b.sync_position_trial=True;frames=[]
        def sync(goals,cancelled):
            frames.append(dict(goals));self.assertFalse(cancelled())
            for i,q in goals.items():b.reg[i][42]=q
            return dict(status='goal_readback_verified',verified_ids=[1,2,3])
        b.sync_positions=sync;b.calls.clear();d.step(m,0.)
        self.assertEqual(len(frames),1);self.assertEqual(set(frames[0]),{1,2,3})
        self.assertEqual(b.calls,[]);self.assertEqual(d.last_sent,frames[0])
        d.step(m,.01);self.assertEqual(len(frames),1)
    def test_sync_failure_never_marks_new_goals_as_confirmed(self):
        m,b,d=self.fixture();b.sync_position_trial=True
        def fail(goals,cancelled):raise RuntimeError('missing readback')
        b.sync_positions=fail
        with self.assertRaises(RuntimeError):d.step(m,0.)
        self.assertEqual(d.last_sent,{})

    def test_recent_horizontal_exit_owns_yaw_instead_of_dance_within_same_limits(self):
        m,b,d=self.fixture()
        for n in range(5):
            now=n*.1;m.latest_result['observation'].update(captured_s=now,error_xy=(.8,0.))
            m.latest_result['intent']['error_xy']=(.8,0.);d.step(m,now)
        previous_center=d.rhythm.status()['gaze_center_raw']
        m.latest_result['observation'].update(status='LOST',captured_s=.5);m.latest_result['intent']=dict(mode='SEARCH',error_xy=None)
        d.step(m,.5)
        m.latest_result['observation']['captured_s']=.6;d.step(m,.6)
        self.assertGreater(d.rhythm.status()['gaze_center_raw'],previous_center)
        self.assertTrue(m.visual.low<=b.reg[1][42]<=m.visual.high)
        self.assertEqual(d.rhythm.status()['yaw_owner'],'gaze_plus_dance')
        self.assertEqual(d.rhythm.status()['gaze_mode'],'recent_exit')
        b.calls.clear();m.latest_result['observation']['captured_s']=1.;d.step(m,1.)
        self.assertEqual(d.rhythm.status()['gaze_mode'],'face_missing_hold')
        self.assertEqual(d.rhythm.status()['small_happy'],'running')
        self.assertEqual(d.gaze_center.filtered_error,0.)
    def test_reacquisition_does_not_snap_yaw_to_dance_target(self):
        m,b,d=self.fixture()
        for n in range(5):
            now=n*.1;m.latest_result['observation']['captured_s']=now
            m.latest_result['intent']['error_xy']=(-.8,0.);d.step(m,now)
        m.latest_result['observation'].update(status='LOST',captured_s=.5);m.latest_result['intent']=dict(mode='SEARCH',error_xy=None);d.step(m,.5)
        m.latest_result['observation']['captured_s']=.6;d.step(m,.6)
        before=b.reg[1][42]
        m.latest_result['observation'].update(status='TRACKING',captured_s=.7);m.latest_result['intent']=dict(mode='FOLLOW',error_xy=(-.5,0.));d.step(m,.7)
        self.assertLessEqual(abs(b.reg[1][42]-before),math.ceil(m.visual.max_speed*.1))

    def test_horizontal_search_uses_same_sync_frame_and_stop_blocks_it(self):
        m,b,d=self.fixture();b.sync_position_trial=True;frames=[]
        def sync(goals,cancelled):
            frames.append(dict(goals))
            for i,q in goals.items():b.reg[i][42]=q
            return dict(status='goal_readback_verified',verified_ids=[1,2,3])
        b.sync_positions=sync
        m.latest_result['intent']['error_xy']=(.8,0.)
        d.step(m,0.);m.latest_result['observation']['captured_s']=.1;d.step(m,.1)
        m.latest_result['observation'].update(status='LOST',captured_s=.2);m.latest_result['intent']=dict(mode='SEARCH',error_xy=None);d.step(m,.2)
        m.latest_result['observation']['captured_s']=.3;d.step(m,.3)
        self.assertEqual(d.rhythm.status()['yaw_owner'],'gaze_plus_dance')
        self.assertEqual(d.rhythm.status()['gaze_mode'],'recent_exit')
        self.assertTrue(all(set(frame)=={1,2,3} for frame in frames))
        self.assertTrue(all((m.visual.low<=q<=m.visual.high) if i==1 else m.controller.normal[i]-34<=q<=m.controller.normal[i]+34 for frame in frames for i,q in frame.items()))
        count=len(frames);m.urgent_stop.set();m.latest_result['observation']['captured_s']=.4;d.step(m,.4)
        self.assertEqual(len(frames),count)

    def test_brief_face_flicker_does_not_restart_dance_or_motion_state(self):
        m,b,d=self.fixture()
        m.latest_result['intent']['error_xy']=(.2,0.)
        d.step(m,0.);m.latest_result['observation']['captured_s']=.1;d.step(m,.1)
        began=d.began
        for n in range(2,16):
            now=n*.1;lost=n%2==0
            m.latest_result['observation'].update(status='LOST' if lost else 'TRACKING',captured_s=now)
            m.latest_result['intent']=dict(mode='SEARCH' if lost else 'FOLLOW',error_xy=None if lost else (.2,0.))
            d.step(m,now)
            self.assertEqual(d.began,began)
            self.assertEqual(d.rhythm.status()['yaw_owner'],'gaze_plus_dance')
    def test_final_body_float_acceleration_is_limited_before_rounding(self):
        m,b,d=self.fixture();previous=None
        for n in range(201):
            now=n*.05;m.latest_result['observation']['captured_s']=now;d.step(m,now)
            states=d.rhythm.status()['planned_motion']
            if previous:
                for sid in (2,3):self.assertLessEqual(abs(states[sid]['velocity_ticks_s']-previous[sid]['velocity_ticks_s'])/.05,m.visual.max_acceleration/3+1e-5)
            previous=states
    def test_gaze_can_move_past_small_dance_box_but_total_uses_existing_wide_limits(self):
        m,b,d=self.fixture()
        for n in range(201):
            now=n*.05;m.latest_result['observation']['captured_s']=now;m.latest_result['intent']['error_xy']=(.8,0.);d.step(m,now)
            self.assertTrue(m.visual.low<=b.reg[1][42]<=m.visual.high)
        self.assertGreater(b.reg[1][42],m.controller.normal[1]+34)
        self.assertTrue(all(abs(b.reg[i][42]-m.controller.normal[i])<=34 for i in (2,3)))
    def test_small_trial_ambiguous_head_hold_never_calls_legacy_yaw_hold(self):
        m,b,d=self.fixture();m.follow_enabled=True;m.held=False;m._hold=Mock()
        result=dict(state='happy',observation=dict(status='AMBIGUOUS',captured_s=20.,source_id=1),intent=dict(mode='HOLD',error_xy=None))
        b.calls.clear();m._apply(result,20.1)
        m._hold.assert_not_called()
        self.assertTrue(all(i==5 for i,a,q in b.calls))

    def test_ambiguity_grace_keeps_dance_state_but_never_selects_new_face(self):
        m,b,d=self.fixture();m.latest_result['intent']['error_xy']=(.2,0.)
        d.step(m,0.);m.latest_result['observation']['captured_s']=.1;d.step(m,.1)
        ids={i:id(f) for i,f in d.limiters.items()};began=d.began
        m.latest_result['observation'].update(status='AMBIGUOUS',captured_s=.2);m.latest_result['intent']=dict(mode='HOLD',error_xy=None)
        d.step(m,.2)
        self.assertEqual(ids,{i:id(f) for i,f in d.limiters.items()})
        self.assertEqual(d.began,began);self.assertEqual(d.last_error_xy,(.2,0.))
        self.assertEqual(d.rhythm.status()['gaze_mode'],'ambiguity_hold')
        for now in (.4,.6,.8):
            m.latest_result['observation']['captured_s']=now;d.step(m,now)
        self.assertEqual(d.rhythm.status()['gaze_mode'],'face_missing_hold')
        self.assertEqual(d.last_error_xy,(.2,0.))
        self.assertEqual(ids,{i:id(f) for i,f in d.limiters.items()})
        b.calls.clear();m.latest_result['observation']['captured_s']=.1;d.step(m,.9)
        self.assertEqual(b.calls,[]);self.assertIsNone(d.rhythm.status()['planned_motion'])
