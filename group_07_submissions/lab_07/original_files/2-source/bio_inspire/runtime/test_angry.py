import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from angry_fsm import AngryFSM,TouchBurst
from lab_fsm import LabFSM


def event(kind,t):return dict(kind=kind,source_s=t,source_id=str(t))


class PolicyTests(unittest.TestCase):
    def test_hardware_angry_profile_requires_accepted_five_second_motion_aware_clock(self):
        import json,tempfile
        from pathlib import Path
        from unittest.mock import patch
        from camera_motor import CameraMotor
        data=json.loads((Path(__file__).resolve().parents[1]/'hardware'/'afraid_pose_trial.json').read_text())
        for changes in ({'fsm_active_timeout_s':2.},{'fsm_motion_aware':False}):
            with tempfile.TemporaryDirectory() as folder,patch('camera_motor.threading.Thread'),patch('camera_motor.open_bus') as open_bus:
                p=Path(folder)/'profile.json';p.write_text(json.dumps({**data,**changes}))
                with self.assertRaisesRegex(ValueError,'Angry requires5s'):CameraMotor(p)
                open_bus.assert_not_called()
    def test_angry_near_is_deferred_until_timeout_then_afraid_if_still_near(self):
        f=AngryFSM(0,motion_aware=True,active_timeout_s=5.)
        f.step(1,[event('touch_burst',1)]);f.step(2,[],ready=True)
        f.step(3,[event('near',3)]);self.assertEqual(f.state,'angry')
        f.step(6.9,[event('near',6.9)]);self.assertEqual(f.state,'angry')
        f.step(7,[event('near',7)]);self.assertEqual(f.state,'afraid')
    def test_angry_clear_does_not_end_emotion_early_and_fault_still_does(self):
        f=AngryFSM(0,motion_aware=True,active_timeout_s=5.)
        f.step(1,[event('touch_burst',1)]);f.step(2,[],ready=True)
        f.step(3,[event('near',3)]);f.step(4,[event('clear',4)])
        self.assertEqual(f.state,'angry')
        f.step(7,[]);self.assertEqual(f.state,'normal')
        f.step(8,[event('touch_burst',8)]);f.step(8.1,[event('fault',8.1)])
        self.assertEqual(f.state,'normal')
    def test_three_real_presses_in_two_seconds_not_held_or_old_queue(self):
        b=TouchBurst()
        self.assertFalse(b.press(10.,10.));self.assertFalse(b.press(10.,10.1))
        self.assertFalse(b.press(11.,11.));self.assertTrue(b.press(12.,12.))
        self.assertFalse(b.press(12.,12.1))
        self.assertFalse(b.press(13.,20.))
        self.assertFalse(b.press(float('nan'),20.))
        self.assertFalse(b.press(21.,20.))
        b.clear();self.assertFalse(b.press(22.,22.))
    def test_window_expires_but_delayed_poll_uses_press_time(self):
        b=TouchBurst()
        self.assertFalse(b.press(1.,1.1));self.assertFalse(b.press(2.,2.1))
        self.assertFalse(b.press(3.01,3.1));self.assertTrue(b.press(3.5,3.6))
    def test_default_lab_unchanged_and_extended_priority_from_all_eligible_states(self):
        f=LabFSM(0);f.step(1,[event('touch',1)]);self.assertEqual(f.state,'happy')
        for state in ('normal','interested','happy','sleepy'):
            f=AngryFSM(0,motion_aware=True,active_timeout_s=5.,sleep_after_s=10.);f.state=state
            f.step(1,[event('touch',1),event('touch_burst',1)])
            self.assertEqual(f.state,'angry')
        for high,target in (('near','afraid'),('fault','normal'),('clear','normal')):
            f=AngryFSM(0);f.step(1,[event(high,1),event('touch_burst',1)])
            self.assertEqual(f.state,target)
        f.state='afraid';f.step(2,[event('touch_burst',2)]);self.assertEqual(f.state,'afraid')
    def test_five_seconds_after_motion_ready_ignores_more_touch_and_hold(self):
        f=AngryFSM(0,motion_aware=True,active_timeout_s=5.)
        f.step(1,[event('touch_burst',1)],ready=False)
        f.step(9,[],ready=False);self.assertEqual(f.state,'angry')
        f.step(10,[],ready=True)
        for t in (11,12,13,14):
            f.step(t,[event('touch',t),event('button',t)],held=True)
            self.assertEqual(f.state,'angry')
        f.step(15,[event('touch',15)],held=True);self.assertEqual(f.state,'normal')


class MotionTests(unittest.TestCase):
    def motor(self):
        from test_taught_crouch import Tests
        m,b=Tests().motor();c=m.controller
        m.angry_enabled=True;m.state_leds_enabled=True;m.interest_body_pitch_compensation=True;m.interested_pitch_lead_ticks=34
        c.interest_head_tracking=True;c.interest_finish_without_face=True;c.interest_gaze_priority=True
        c.interest_native_neck=True;c.interest_native_body_speed_raw=17;c.interest_body_acceleration_raw=1
        c.lean_command_limits=(100.,100.,.5);c.control_now_s=20.;c.control_clock=lambda:c.control_now_s
        c.face_ready_for_interest=True;c.interest_head_following_error=lambda rows:0.;c.interest_head_following_limit=34
        return m,b
    def test_direct_upright_lean_and_completion_keep_angry_red_and_gaze(self):
        from angry_behavior import enter_angry
        from camera_motor import CameraMotor
        from interested_head import active
        m,b=self.motor();c=m.controller
        self.assertTrue(enter_angry(m));r=c.pose_route
        self.assertEqual(m.behavior_trial,'angry_transition');self.assertEqual(r.phase,'lean')
        self.assertEqual(r.stage_target[4],c.normal[4]);self.assertEqual(r.stage_target[5],c.normal[5])
        self.assertEqual((r.stage_target[2],r.stage_target[3]),(c.normal[2]-102,c.normal[3]+102))
        self.assertTrue(active(m));m.led_ring.angry.assert_called_once()
        c.interest_head_following_error=lambda rows:0.;c.interest_head_following_limit=34
        for n in range(1,6):
            c.control_now_s=20+n*.05;b.pos={i:b.reg[i][42] for i in c.normal};c.tick(c.control_now_s)
        self.assertEqual(r.phase,'complete')
        CameraMotor._finish_button_route(m)
        self.assertEqual(m.behavior_trial,'angry');self.assertIsNone(m.interested_roll_due)
        self.assertTrue(m.follow_enabled);self.assertTrue(active(m))
    def test_angry_does_not_wait_for_face_before_coordinated_lean(self):
        from angry_behavior import enter_angry
        m,b=self.motor();c=m.controller;c.face_ready_for_interest=False;c.interest_face_stamp=20.
        m.behavior_trial='happy';m.rhythm_view_cache=dict(gaze_center_raw=2050.,control_now_s=20.)
        self.assertTrue(enter_angry(m));r=c.pose_route
        self.assertEqual(r.head_entry_yaw,2050)
        c.interest_head_following_error=lambda rows:0.;c.interest_head_following_limit=34
        c.control_now_s=20.05;c.tick(20.05)
        self.assertTrue(r.native_lean_started)
        self.assertEqual(b.reg[2][42],r.stage_target[2])
        self.assertEqual(b.reg[3][42],r.stage_target[3])
        self.assertNotEqual(c.state,'FAULT',c.last_error)

    def test_lost_face_from_high_happy_preserves_aim_and_predicts_head_with_lean(self):
        from angry_behavior import enter_angry
        from camera_motor import CameraMotor
        from visual_servo import VisualServo
        m,b=self.motor();c=m.controller;c.set_direction(1)
        m.native_posture_compensation=True;m.behavior_trial='happy';c.interest_pitch_window=(2070,2764)
        for i,q in {2:2654,3:3095,5:2250}.items():b.pos[i]=q;b.reg[i][42]=q
        c.behavior_joint_windows={2:(2603,2705),3:(3044,3146)};c.behavior_pitch_window=(2070,2764)
        c.last_rows=b.snapshot();m.visual=VisualServo(*c.yaw_window,400.,100.,.25,6.,160.,.5)
        m.pitch_visual=VisualServo(2070,2764,400.,100.,.25,6.,90.,.5);m.pitch_direction=1
        m._reset_pitch=CameraMotor._reset_pitch.__get__(m);m.yaw_follow_enabled=False
        self.assertTrue(enter_angry(m));self.assertEqual(c.pose_route.head_entry_pitch,2250)
        m._service_interested_gaze();c.face_ready_for_interest=False;c.interest_face_stamp=20.05
        m._apply(dict(state='normal',observation=dict(status='LOST',captured_s=20.05,source_id=1),
                      intent=dict(mode='SEARCH',error_xy=None)),20.05)
        self.assertEqual(b.reg[5][42],2578)
        c.control_now_s=20.1;c.tick(20.1)
        self.assertTrue(c.pose_route.native_lean_started)
        self.assertNotEqual(c.state,'FAULT',c.last_error)
        c.pose_route.phase='complete';m._finish_button_route()
        self.assertEqual(c.active_pitch_window(),c.pitch_window)
        self.assertTrue(c.sleepy_return_pending)
        self.assertLessEqual(c.behavior_pitch_window[0],2250)
        m._apply(dict(state='normal',observation=dict(status='LOST',captured_s=20.15,source_id=2),
                      intent=dict(mode='SEARCH',error_xy=None)),20.15)
        self.assertGreaterEqual(b.reg[5][42],c.pitch_window[0])

    def test_normal_level_angry_returns_natively_then_tracks_without_normal_state(self):
        from angry_behavior import enter_angry
        m,b=self.motor();c=m.controller;m.angry_normal_level=True;m.behavior_trial='happy'
        m.rhythm_view_cache=dict(gaze_center_raw=2050.,control_now_s=20.)
        self.assertTrue(enter_angry(m));r=c.pose_route
        self.assertEqual(r.phase,'return');self.assertFalse(r.force_normal)
        self.assertEqual(r.completion_behavior,'angry');self.assertFalse(m.follow_enabled)
        for i in (2,3,4,5):self.assertEqual(b.reg[i][42],c.normal[i])
        self.assertEqual(b.reg[1][42],2050)
        b.pos={i:b.reg[i][42] for i in c.normal};c.last_rows=b.snapshot()
        for n in range(1,4):c.control_now_s=20+n*.05;c.tick(c.control_now_s)
        m._finish_button_route();self.assertEqual(m.behavior_trial,'angry');self.assertTrue(m.follow_enabled)
        self.assertEqual(c.active_pitch_window(),c.pitch_window)
        from body_rhythm import BodyRhythmDriver
        d=BodyRhythmDriver(normal_amplitude_deg=2.,interested_amplitude_deg=1.9)
        for n in range(61):d.step(m,20.2+n*.05)
        self.assertEqual(d.centers,{2:c.normal[2],3:c.normal[3]})

    def test_angry_has_body_cpg_and_stop_prevents_writes(self):
        from state_rhythms import StateRhythms
        m,b=self.motor();m.behavior_trial='angry';d=StateRhythms(Mock(),Mock())
        b.calls.clear()
        for n in range(61):d.step(m,20+n*.05)
        self.assertTrue(any(i in (2,3) and a==42 for i,a,v in b.calls))
        self.assertTrue(all(i in (2,3) for i,a,v in b.calls if a==42))
        m.urgent_stop.set();b.calls.clear();d.step(m,23.1);self.assertEqual(b.calls,[])
    def test_happy_and_sleepy_can_enter_angry_directly_then_normal_or_afraid(self):
        from angry_behavior import enter_angry
        from three_state_behavior import handle_state_key
        from afraid_pose import enter_afraid
        for source in ('happy','sleepy'):
            m,b=self.motor();c=m.controller;m.behavior_trial=source
            if source=='happy':
                for i in (2,3):b.reg[i][41]=3;b.reg[i][46]=750
            else:
                handle_state_key(m,ord('n'));b.pos=dict(c.normal)
                for t in (20.05,20.1,20.15):c.control_now_s=t;c.tick(t)
                m._finish_button_route();handle_state_key(m,ord('s'))
                b.pos={i:b.reg[i][42] for i in c.normal};c.last_rows=b.snapshot()
            self.assertTrue(enter_angry(m));self.assertEqual(c.pose_route.phase,'lean')
            self.assertEqual([b.reg[i][41] for i in (2,3)],[1,1])
            self.assertFalse(c.pose_route.force_normal)
            enter_afraid(m);self.assertEqual(m.behavior_trial,'afraid')
            self.assertEqual(c.pose_route.phase,'retreat')
            handle_state_key(m,ord('n'));self.assertEqual(m.behavior_trial,'normal_transition')
            self.assertEqual([b.reg[i][46] for i in (2,3)],[c.motion_speed]*2)
    def test_urgent_stop_rejects_angry_without_writes(self):
        from angry_behavior import enter_angry
        m,b=self.motor();m.urgent_stop.set();b.calls.clear()
        self.assertFalse(enter_angry(m));self.assertEqual(b.calls,[])
    def test_sleepy_head_target_does_not_fault_body_after_awake_window_contracts(self):
        from angry_behavior import enter_angry
        m,b=self.motor();c=m.controller;m.behavior_trial='sleepy'
        c.behavior_pitch_window=(c.pitch_window[0],2901);b.pos[5]=2901;b.reg[5][42]=2901;c.last_rows=b.snapshot()
        self.assertTrue(enter_angry(m));r=c.pose_route
        c.configure_tracking();b.calls.clear()
        c.interest_head_following_error=lambda rows:0.;c.interest_head_following_limit=34
        c.control_now_s=20.05;c.tick(20.05)
        self.assertNotEqual(c.state,'FAULT',c.last_error)
        self.assertFalse(any(i in (1,5) and a==42 for i,a,v in b.calls))
        self.assertEqual(b.reg[2][42],r.stage_target[2])
        r.stage_target[2]=r.path_windows[2][1]+1;r.native_lean_started=False
        c.control_now_s=20.1;c.tick(20.1)
        self.assertEqual(c.state,'FAULT')
        self.assertIn('ID2',c.last_error)
    def test_angry_preserves_awake_reference_when_interrupting_happy_wake(self):
        from angry_behavior import enter_angry
        m,b=self.motor();c=m.controller;m.behavior_trial='happy';m.happy_head_wake_goal=c.normal[5]
        c.behavior_pitch_window=(c.pitch_window[0],2901);b.pos[5]=2901;b.reg[5][42]=2901;c.last_rows=b.snapshot()
        self.assertTrue(enter_angry(m))
        self.assertEqual(getattr(c.pose_route,'head_entry_pitch',None),c.normal[5])
    def test_real_head_pipeline_wakes_then_compensates_during_body_motion(self):
        from angry_behavior import enter_angry
        from camera_motor import CameraMotor
        from visual_servo import VisualServo
        m,b=self.motor();c=m.controller;c.set_direction(1)
        m.behavior_trial='happy';m.happy_head_wake_goal=c.normal[5]
        c.behavior_pitch_window=(c.pitch_window[0],2901);b.pos[5]=2901;b.reg[5][42]=2901;c.last_rows=b.snapshot()
        m.visual=VisualServo(*c.yaw_window,400.,100.,.25,6.,160.,.5)
        m.pitch_visual=VisualServo(*c.pitch_window,400.,100.,.25,6.,90.,.5);m.pitch_direction=1
        m._reset_pitch=CameraMotor._reset_pitch.__get__(m);m.yaw_follow_enabled=False
        self.assertTrue(enter_angry(m));m._service_interested_gaze()
        def gaze(t):
            m._apply(dict(state='normal',observation=dict(status='TRACKING',captured_s=t,source_id=t),
                          intent=dict(mode='FOLLOW',error_xy=(0.,0.))),t)
        c.control_now_s=20.05;c.tick(20.05);gaze(20.05)
        self.assertEqual(b.reg[5][42],c.normal[5])
        self.assertEqual(b.reg[2][42],c.normal[2])
        b.pos[5]=c.normal[5]
        for n in range(2,12):
            t=20+n*.05;c.control_now_s=t
            b.pos[2]=c.normal[2]-n;b.pos[3]=c.normal[3]+n
            c.tick(t);gaze(t)
            self.assertNotEqual(c.state,'FAULT',c.last_error)
        self.assertEqual(c.pose_route.phase,'lean')
        self.assertLess(b.reg[5][42],c.normal[5])
        self.assertLess(b.reg[2][42],c.normal[2])


class AdapterTests(unittest.TestCase):
    def test_three_real_buffered_presses_in_one_service_enter_angry(self):
        from physical_button import BufferedInput
        from test_automatic_fsm import Tests
        m,b,s=self.fixture();source=BufferedInput(.06);m.physical_touch=source
        source.pending.extend((20.1,20.35,20.6))
        Tests().at(m,s,20.8)
        self.assertEqual(m.automatic_fsm.fsm.state,'angry')
        self.assertEqual(m.touch_sequence,3)
        self.assertEqual(list(source.pending),[])
    def fixture(self):
        from test_automatic_fsm import Tests
        from automatic_fsm import AutomaticFSM
        m,b,s=Tests().motor();m.automatic_fsm=AutomaticFSM(angry_enabled=True,motion_aware=True,active_timeout_s=5.)
        m.angry_enabled=True;m.automatic_fsm.dispatch=Mock(return_value=True)
        m.automatic_fsm.service(m,20.)
        return m,b,s
    def press(self,m,s,stamp,now):
        from test_automatic_fsm import Tests
        m.physical_touch.poll.return_value=True;m.physical_touch.last_event_s=stamp
        Tests().at(m,s,now)
        m.physical_touch.poll.return_value=False
    def test_adapter_uses_queued_source_times_and_first_touch_remains_happy(self):
        m,b,s=self.fixture()
        self.press(m,s,20.1,21.1);self.assertEqual(m.automatic_fsm.fsm.state,'happy')
        self.press(m,s,20.5,21.2);self.press(m,s,21.,21.3)
        self.assertEqual(m.automatic_fsm.fsm.state,'angry')
        self.assertEqual(m.automatic_fsm.fsm.last_winner['kind'],'touch_burst')
        m.automatic_fsm.dispatch.assert_called_with(m,'angry','touch_burst')
    def test_stop_and_near_clear_partial_burst(self):
        from test_automatic_fsm import Tests
        for interrupted in ('stop','near'):
            m,b,s=self.fixture();self.press(m,s,20.1,20.1);self.press(m,s,20.3,20.3)
            if interrupted=='stop':
                m.operator_stopped=True;Tests().at(m,s,20.4);m.operator_stopped=False
            else:
                Tests().at(m,s,20.4,distance_cm=10.);Tests().at(m,s,20.5,distance_cm=120.)
            self.press(m,s,20.6,20.6)
            self.assertNotEqual(m.automatic_fsm.fsm.state,'angry')
    def test_sparse_old_presses_do_not_become_burst_when_polled_together(self):
        m,b,s=self.fixture()
        for stamp,now in ((18.,21.1),(20.,21.2),(21.,21.3)):self.press(m,s,stamp,now)
        self.assertNotEqual(m.automatic_fsm.fsm.state,'angry')
    def test_real_adapter_dispatches_angry_on_third_touch(self):
        from automatic_fsm import AutomaticFSM
        from distance_behavior import DistanceGate
        m,b=MotionTests().motor();m.automatic_fsm_enabled=True;m.all_states_cpg_enabled=True
        m.distance_gate=DistanceGate();s=dict(distance_cm=120.,received_s=20.,error=None,sequence=1)
        m.physical_distance=SimpleNamespace(latest=lambda:dict(s))
        m.physical_touch=SimpleNamespace(poll=lambda now:False,edge=SimpleNamespace(stable=False))
        m.physical_button=SimpleNamespace(poll=lambda now:False,edge=SimpleNamespace(stable=False))
        m.automatic_fsm=AutomaticFSM(angry_enabled=True,motion_aware=True,active_timeout_s=5.)
        m.automatic_fsm.service(m,20.)
        for t in (20.1,20.5,21.):
            m.now=lambda stamp=t:stamp;c=m.controller;c.control_now_s=t;s['received_s']=t
            m.physical_touch.poll=lambda now:True;m.physical_touch.last_event_s=t
            m.automatic_fsm.service(m,t)
        self.assertEqual(m.automatic_fsm.fsm.state,'angry')
        self.assertEqual(m.behavior_trial,'angry_transition');self.assertEqual(m.controller.pose_route.phase,'lean')
        m.led_ring.angry.assert_called_once()
    def test_buffered_touches_during_afraid_do_not_replay_after_clear(self):
        from physical_button import BufferedInput
        from test_automatic_fsm import Tests
        m,b,s=self.fixture();source=BufferedInput(.06);m.physical_touch=source
        Tests().at(m,s,20.1,distance_cm=10.)
        source.pending.extend((20.11,20.15,20.2,20.25))
        Tests().at(m,s,20.3,distance_cm=120.)
        for t in (20.35,20.4,20.45):Tests().at(m,s,t)
        self.assertEqual(m.automatic_fsm.fsm.state,'normal')
        self.assertEqual(list(source.pending),[])
