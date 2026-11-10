import unittest
from types import SimpleNamespace
import test_angry as fixture
from angry_approach import AngryApproachRoute

class Tests(unittest.TestCase):
    def test_extension_validation_rejects_unapproved_values(self):
        from angry_approach import validate
        config=dict(angry_face_approach=True,angry_normal_level=True,physical_tof_enabled=True,native_posture_compensation=True)
        self.assertTrue(validate({**config,'angry_approach_degrees':12}))
        for value in (13,12.,True,0):
            with self.assertRaises(ValueError):validate({**config,'angry_approach_degrees':value})
    def make(self,degrees=9,head_up=0):
        m,b=fixture.MotionTests().motor();c=m.controller
        m.angry_approach_degrees=degrees
        m.angry_head_up_deg=head_up
        m.behavior_trial='angry_transition';m.latest_result={};m.distance_view={}
        m.physical_distance=SimpleNamespace(latest=lambda:dict(m.distance_view))
        r=AngryApproachRoute(m,dict(c.normal));c.pose_route=r
        b.pos=dict(c.normal);c.last_rows=b.snapshot()
        for t in (20.02,20.05,20.10,20.15):self.at(m,b,r,t,30.,False)
        self.assertEqual(r.phase,'lean')
        return m,b,r
    def at(self,m,b,r,t,cm,face=True):
        m.now=lambda:t;m.controller.control_now_s=t
        m.distance_view=dict(distance_cm=cm,received_s=t,measurement_state='range' if cm is not None else 'no_target',error=None)
        m.latest_result=dict(observation=dict(status='TRACKING' if face else 'LOST',captured_s=t),intent=dict(mode='FOLLOW' if face else 'SEARCH',error_xy=(0.,0.) if face else None))
        r.step(b.snapshot())
    def launch(self,m,b,r):
        for t in (20.16,20.18,20.2):self.at(m,b,r,t,30.)
    def test_missing_face_never_launches_forward(self):
        m,b,r=self.make();b.calls.clear();self.at(m,b,r,20.2,30.,False)
        self.assertFalse(r.native_lean_started)
        self.assertFalse(any(sid in (2,3) and address==42 for sid,address,value in b.calls))
    def test_recent_centered_aim_avoids_waiting_for_face_again_at_same_pose(self):
        m,b,r=self.make(18,head_up=3)
        self.at(m,b,r,20.16,30.,True)
        self.at(m,b,r,20.26,30.,False)
        self.at(m,b,r,20.36,30.,False)
        self.assertTrue(r.native_lean_started)
        self.assertEqual(r.status()['acquisition_source'],'recent_pose_memory')
        self.assertEqual(b.reg[2][46],17)
    def test_recent_aim_never_launches_if_expired_or_head_has_turned(self):
        for expired,turned in ((True,False),(False,True)):
            m,b,r=self.make(18);self.at(m,b,r,20.16,30.,True)
            if turned:b.pos[1]+=40
            base=21.3 if expired else 20.26
            for dt in (0.,.1,.2):self.at(m,b,r,base+dt,30.,False)
            self.assertFalse(r.native_lean_started)
    def test_approved12_extends_only_angry_endpoints(self):
        m,b,r=self.make(12);self.launch(m,b,r)
        self.assertEqual(r.endpoints,{2:2700,3:2883})
        self.assertEqual((b.reg[2][46],b.reg[3][46]),(17,17))
        self.at(m,b,r,20.3,15.)
        self.assertTrue(r.safety_hold)
    def test_approved15_uses_new_distance_guards_and_keeps_slow_body(self):
        from angry_approach import validate
        self.assertTrue(validate(dict(angry_face_approach=True,angry_normal_level=True,
            physical_tof_enabled=True,native_posture_compensation=True,angry_approach_degrees=15)))
        m,b,r=self.make(15);self.launch(m,b,r)
        self.assertEqual(r.endpoints,{2:2666,3:2917})
        self.assertEqual((b.reg[2][46],b.reg[3][46]),(17,17))
        self.at(m,b,r,20.3,20.)
        self.assertEqual(r.range_phase,'advance')
        self.at(m,b,r,20.4,19.8)
        self.assertEqual(r.range_reason,'range_brake_guard');self.assertFalse(r.safety_hold)
        self.assertEqual(r.status()['minimum_tof_cm'],10.)
        self.assertEqual(r.status()['stop_guard_cm'],19.8)
    def test_approved18_has_angry_only_head_window_and_preserves_return_clearance(self):
        m,b,r=self.make(18);c=m.controller;self.launch(m,b,r)
        self.assertEqual(r.endpoints,{2:2632,3:2951})
        self.assertEqual(c.active_pitch_window(),(2241,c.pitch_window[1]))
        self.assertEqual(r.status()['minimum_tof_cm'],10.)
        self.assertEqual(r.status()['stop_guard_cm'],19.8)
        b.pos[5]=2260;c.last_rows=b.snapshot()
        r.cancel()
        self.assertEqual(c.active_pitch_window(),c.pitch_window)
        low,high=c.feedback_window(5)
        self.assertTrue(low<=2260<=high)
        self.assertTrue(c.sleepy_return_pending)
    def test_approved18_window_stays_during_angry_hold_and_minimum_stops(self):
        m,b,r=self.make(18);c=m.controller;self.launch(m,b,r)
        self.at(m,b,r,20.3,19.8);b.pos[4]=c.normal[4]-68
        for t in (20.4,20.5,20.6):self.at(m,b,r,t,19.8)
        m._finish_button_route()
        self.assertEqual(c.active_pitch_window(),(2241,c.pitch_window[1]))
        self.at(m,b,r,20.7,10.)
        self.assertTrue(r.safety_hold);self.assertEqual(r.range_reason,'minimum_tof_10')
    def test_approved15_minimum10_all_axis_hold_before_or_after_motion(self):
        for cm in (10.,9.,0.):
            m,b,r=self.make(15);self.launch(m,b,r)
            self.at(m,b,r,20.3,cm,False)
            self.assertTrue(r.safety_hold);self.assertEqual(r.range_reason,'minimum_tof_10')
            self.assertEqual(b.reg[4][42],m.controller.normal[4])
            m._finish_button_route();self.assertFalse(m.follow_enabled)
        m,b,r=self.make(15);self.launch(m,b,r);self.at(m,b,r,20.3,19.8)
        b.pos[4]=m.controller.normal[4]-68
        for t in (20.4,20.5,20.6):self.at(m,b,r,t,19.8)
        self.assertEqual(r.phase,'complete')
        self.at(m,b,r,20.7,10.)
        self.assertTrue(r.safety_hold)
    def test_head_prediction_starts_with_body_and_is_bounded_to_three_degrees(self):
        from visual_servo import VisualServo
        m,b,r=self.make(12);c=m.controller
        m.native_posture_compensation=True;m.pitch_direction=1
        m.pitch_visual=VisualServo(*c.pitch_window,400.,100.,.25,6.,90.,.5)
        c.last_rows=b.snapshot()
        m._apply_pitch(dict(error_xy=(0.,0.)),dict(source_id=1,captured_s=20.15),20.15,True)
        start=b.reg[5][42]
        self.launch(m,b,r);c.last_rows=b.snapshot()
        m._apply_pitch(dict(mode='HOLD',error_xy=None),dict(source_id=2,captured_s=20.2),20.2,False)
        self.assertEqual(b.reg[5][42],start-34)
        # Prediction follows actual arm motion and disappears at a range pause.
        b.pos[2]-=20;b.pos[3]+=20
        target=r.head_compensation_target(b.snapshot())
        measured=b.pos[2]-c.normal[2]-(b.pos[3]-c.normal[3])
        predicted=target[2]-c.normal[2]-(target[3]-c.normal[3])
        self.assertEqual(predicted,measured-34)
        self.at(m,b,r,20.3,None,False)
        self.assertIsNone(r.head_compensation_target(b.snapshot()))
    def test_angry_head_up3_applies_with_posture_and_remains_when_body_stops(self):
        from visual_servo import VisualServo
        m,b,r=self.make(18,head_up=3);c=m.controller
        m.native_posture_compensation=True;m.pitch_direction=1
        m.pitch_visual=VisualServo(*c.active_pitch_window(),400.,100.,.25,6.,90.,.5)
        c.last_rows=b.snapshot()
        m._apply_pitch(dict(error_xy=(0.,0.)),dict(source_id=1,captured_s=20.15),20.15,True)
        start=b.reg[5][42]
        self.launch(m,b,r);c.last_rows=b.snapshot()
        m._apply_pitch(dict(mode='HOLD',error_xy=None),dict(source_id=2,captured_s=20.2),20.2,False)
        self.assertEqual(b.reg[5][42],start-68) #34 posture lead +34 requested upward offset
        self.at(m,b,r,20.3,19.8);c.last_rows=b.snapshot()
        m._apply_pitch(dict(mode='HOLD',error_xy=None),dict(source_id=3,captured_s=20.3),20.3,False)
        self.assertEqual(b.reg[5][42],start-34)
        self.assertGreaterEqual(b.reg[5][42],c.active_pitch_window()[0])
    def test_fresh_face_starts_bounded_native_motion_then_range_stops_once(self):
        m,b,r=self.make();self.launch(m,b,r)
        self.assertTrue(r.native_lean_started)
        self.assertEqual((b.reg[2][42],b.reg[3][42]),(2735,2848))
        self.assertEqual((b.reg[2][46],b.reg[3][46]),(17,17))
        b.pos[2]=2790;b.pos[3]=2793
        self.at(m,b,r,20.3,24.7)
        self.assertEqual((b.reg[2][42],b.reg[3][42]),(2790,2793))
        self.assertEqual(b.reg[4][42],m.controller.normal[4]-68)
        self.assertEqual(r.range_reason,'range_brake_guard')
        b.calls.clear();self.at(m,b,r,20.4,30.)
        self.assertFalse(any(sid in (2,3) and address==42 for sid,address,value in b.calls))
    def test_invalid_range_pauses_without_tilt(self):
        m,b,r=self.make();self.launch(m,b,r);b.pos[2]=2800;b.pos[3]=2780
        self.at(m,b,r,20.3,None)
        self.assertEqual((b.reg[2][42],b.reg[3][42]),(2800,2780))
        self.assertEqual(b.reg[4][42],m.controller.normal[4]);self.assertEqual(r.range_phase,'paused')
    def test_stop_never_writes_and_deadline_is_bounded(self):
        m,b,r=self.make();m.urgent_stop.set();b.calls.clear();self.launch(m,b,r)
        self.assertEqual(b.calls,[])
        m.urgent_stop.clear();self.at(m,b,r,33.,30.,False)
        self.assertEqual(r.phase,'complete');self.assertEqual(r.range_reason,'entry_budget')

    def test_retreat_only_cpg_does_not_advance_past_stop_even_when_tilted(self):
        from body_rhythm import BodyRhythmDriver
        m,b,r=self.make();m.angry_face_approach=True;m.angry_normal_level=True
        self.launch(m,b,r);b.pos[2]=2790;b.pos[3]=2793
        self.at(m,b,r,20.3,24.7);b.pos[4]=m.controller.normal[4]-68
        for t in (20.4,20.5,20.6):self.at(m,b,r,t,24.7)
        self.assertEqual(r.phase,'complete');m.behavior_trial='angry'
        d=BodyRhythmDriver(normal_amplitude_deg=2.,interested_amplitude_deg=1.9)
        b.calls.clear()
        for n in range(121):
            d.step(m,20.7+n*.05)
            self.assertGreaterEqual(b.reg[2][42],2790)
            self.assertLessEqual(b.reg[3][42],2793)
        self.assertTrue(any(i in (2,3) and a==42 for i,a,q in b.calls))
        self.assertEqual(d.centers,{2:2790,3:2793})

    def test_timeout_during_normal_return_keeps_actual_pose_in_feedback_guard(self):
        m,b=fixture.MotionTests().motor();c=m.controller
        b.pos[2]=2654;b.pos[3]=3095;c.behavior_joint_windows={2:(2603,2880),3:(2700,3150)}
        c.last_rows=b.snapshot();m.distance_view={};m.latest_result={}
        r=AngryApproachRoute(m,dict(c.normal));c.pose_route=r
        m.now=lambda:33.;c.control_now_s=33.;r.step(b.snapshot())
        self.assertEqual((b.reg[2][42],b.reg[3][42]),(2654,3095))
        self.assertEqual(r.phase,'complete')
        for sid in (2,3):
            lo,hi=c.behavior_joint_windows[sid];self.assertTrue(lo<=b.pos[sid]<=hi)

    def test_stop_does_not_clamp_loaded_offset_into_new_forward_goal(self):
        m,b,r=self.make();self.launch(m,b,r)
        b.pos[2]=2857;b.pos[3]=2726
        self.at(m,b,r,20.3,24.7)
        self.assertEqual((b.reg[2][42],b.reg[3][42]),(2857,2726))
    def test_live_worker_cache_wins_over_old_fsm_distance(self):
        m,b,r=self.make();m.physical_distance=SimpleNamespace(latest=lambda:dict(distance_cm=None,received_s=20.2,measurement_state='no_target'))
        self.launch(m,b,r)
        self.assertFalse(r.native_lean_started)
        m.physical_distance=SimpleNamespace(latest=lambda:dict(distance_cm=30.,received_s=20.1,measurement_state='range'))
        self.at(m,b,r,20.3,30.)
        self.assertFalse(r.native_lean_started)
    def test_return_timeout_keeps_outlying_roll_and_head_clearance(self):
        m,b=fixture.MotionTests().motor();c=m.controller
        b.pos[2]=2654;b.pos[3]=3095;b.pos[4]=2300;b.pos[5]=2250
        c.behavior_joint_windows={2:(2603,2880),3:(2700,3150),4:(1614,2405)}
        c.behavior_pitch_window=(2070,2764);c.last_rows=b.snapshot()
        m.distance_view={};m.latest_result={};r=AngryApproachRoute(m,dict(c.normal));c.pose_route=r
        m.now=lambda:33.;r.step(b.snapshot())
        self.assertEqual(b.reg[4][42],2300);self.assertEqual(b.reg[5][42],2250)
        lo,hi=c.feedback_window(4);self.assertTrue(lo<=2300<=hi)
        m._finish_button_route();lo,hi=c.feedback_window(5);self.assertTrue(lo<=2250<=hi)

    def test_out_of_range_sensor_value_never_launches_forward(self):
        m,b,r=self.make();self.at(m,b,r,20.2,500.)
        self.assertFalse(r.native_lean_started)
        self.assertEqual((b.reg[2][42],b.reg[3][42]),(m.controller.normal[2],m.controller.normal[3]))

    def test_tracked_off_center_face_does_not_count_as_lost_after_launch(self):
        m,b,r=self.make();self.launch(m,b,r)
        t=20.3;m.now=lambda:t;m.distance_view.update(received_s=t)
        m.latest_result['observation']['captured_s']=t;m.latest_result['intent']['error_xy']=(0.,-.322)
        r.step(b.snapshot())
        self.assertEqual(r.range_phase,'advance');self.assertIsNone(r.range_reason)
    def test_off_center_face_still_requires_centering_before_launch(self):
        m,b,r=self.make();t=20.2;m.now=lambda:t
        m.distance_view=dict(distance_cm=30.,received_s=t,measurement_state='range')
        m.latest_result=dict(observation=dict(status='TRACKING',captured_s=t),intent=dict(mode='FOLLOW',error_xy=(0.,-.322)))
        r.step(b.snapshot());self.assertFalse(r.native_lean_started)

    def test_remembered_heading_continues_without_green_frame_or_live_head_lag_gate(self):
        m,b,r=self.make();self.launch(m,b,r)
        self.assertTrue(r.heading_saved);memory=dict(r.heading)
        m.controller.interest_head_following_error=lambda rows:80.
        self.at(m,b,r,20.3,30.,False)
        self.assertEqual(r.range_phase,'advance');self.assertIsNone(r.range_reason)
        self.assertEqual(r.heading,memory)
    def test_transient_range_pause_resumes_without_requiring_face(self):
        m,b,r=self.make();self.launch(m,b,r);b.pos[2]=2810;b.pos[3]=2780
        self.at(m,b,r,20.3,None,False)
        self.assertEqual(r.range_phase,'paused');self.assertEqual(r.pause_reason,'range_unreliable')
        self.assertEqual((b.reg[2][42],b.reg[3][42]),(2810,2780))
        for t in (20.4,20.5):self.at(m,b,r,t,30.,False)
        self.assertEqual(r.range_phase,'paused')
        self.at(m,b,r,20.6,30.,False)
        self.assertEqual(r.range_phase,'advance');self.assertEqual(r.resume_count,1)
        self.assertEqual((b.reg[2][42],b.reg[3][42]),(2735,2848))
    def test_minimum15_holds_without_tilt_and_does_not_reenable_gaze(self):
        for cm in (15.,14.,0.):
            m,b,r=self.make();self.launch(m,b,r);b.pos[2]=2800;b.pos[3]=2780
            self.at(m,b,r,20.3,cm,False)
            self.assertTrue(r.safety_hold);self.assertEqual(r.range_reason,'minimum_tof_15')
            self.assertEqual((b.reg[2][42],b.reg[3][42]),(2800,2780))
            self.assertEqual(b.reg[4][42],m.controller.normal[4])
            m._finish_button_route();self.assertFalse(m.follow_enabled)
            b.calls.clear();self.at(m,b,r,20.4,30.,False)
            self.assertEqual(b.calls,[])
    def test_minimum15_remains_monitored_after_pose_complete(self):
        m,b,r=self.make();self.launch(m,b,r);self.at(m,b,r,20.3,24.7)
        b.pos[4]=m.controller.normal[4]-68
        for t in (20.4,20.5,20.6):self.at(m,b,r,t,24.7)
        self.assertEqual(r.phase,'complete')
        self.at(m,b,r,20.7,14.)
        self.assertTrue(r.safety_hold)
    def test_heading_lock_suppresses_visual_input_but_keeps_body_head_model(self):
        from interested_head import apply_gaze
        from unittest.mock import Mock
        m,b,r=self.make();self.launch(m,b,r);m._apply_pitch=Mock();m._face_exit_memory=Mock()
        apply_gaze(m,dict(observation=dict(status='LOST',captured_s=20.3),intent=dict(mode='SEARCH',error_xy=None)),20.3)
        self.assertEqual(m._apply_pitch.call_count,1)
        self.assertIsNone(m._apply_pitch.call_args.args[0]['error_xy']);self.assertFalse(m._apply_pitch.call_args.args[3])
        m._face_exit_memory.assert_not_called()

    def test_initial_level_return_waits_for_minimum_check_before_any_goals(self):
        m,b=fixture.MotionTests().motor();c=m.controller
        m.physical_distance=SimpleNamespace(latest=lambda:dict(distance_cm=15.,received_s=20.,measurement_state='range'))
        m.latest_result={};b.calls.clear();r=AngryApproachRoute(m,dict(c.normal));c.pose_route=r
        self.assertFalse(any(a==42 for i,a,q in b.calls))
        r.step(b.snapshot());self.assertTrue(r.safety_hold)
    def test_yaw_resumes_from_measured_heading_after_long_memory_lock(self):
        from interested_head import apply_gaze
        from visual_servo import VisualServo
        from unittest.mock import Mock
        m,b,r=self.make();self.launch(m,b,r)
        m.visual=VisualServo(1700,2350,100.,100.,.25,5.,160.,.5)
        m.visual.reset(2016,20.2);m._apply_pitch=Mock();m._face_exit_memory=Mock(return_value=False)
        m.controller.state='READY';m.controller.last_rows=b.snapshot();m.yaw_follow_enabled=True;m.controller.direction=1
        obs=dict(status='TRACKING',captured_s=23.9,source_id=90)
        result=dict(observation=obs,intent=dict(mode='FOLLOW',error_xy=(.1,0.)))
        apply_gaze(m,result,23.9)  # Deliberately suspended yaw, body compensation still runs.
        r.phase='complete'
        apply_gaze(m,result,23.95)
        self.assertEqual(m.visual.time,23.95)
        self.assertEqual(m.visual.position,b.pos[1])
        self.assertEqual(m.visual.velocity,0.)
        # A genuine subsequent missed control interval must still raise.
        with self.assertRaisesRegex(ValueError,'Control interval'):
            apply_gaze(m,result,24.6)
    def test_resume_requires_new_tof_frames_not_only_new_camera_frames(self):
        m,b,r=self.make();self.launch(m,b,r);self.at(m,b,r,20.3,None,False)
        m.physical_distance=SimpleNamespace(latest=lambda:dict(distance_cm=30.,received_s=20.4,sequence=7,measurement_state='range'))
        for t in (20.4,20.41,20.42):self.at(m,b,r,t,30.,False)
        self.assertEqual(r.range_phase,'paused')
        for t,seq in ((20.5,8),(20.6,9)):
            m.physical_distance=SimpleNamespace(latest=lambda t=t,seq=seq:dict(distance_cm=30.,received_s=t,sequence=seq,measurement_state='range'))
            self.at(m,b,r,t,30.,False)
        self.assertEqual(r.range_phase,'advance')

    def test_completed_level_return_survives_publish_gap_before_arrival_confirmation(self):
        m,b=fixture.MotionTests().motor();c=m.controller
        c.motion_speed=600;c.coordinated_pose_transitions=True
        c.control_now_s=20.;c.control_clock=lambda:m.now()
        m.now=lambda:20.;m.behavior_trial='angry_transition';m.latest_result={};m.distance_view={}
        m.physical_distance=SimpleNamespace(latest=lambda:dict(m.distance_view))
        r=AngryApproachRoute(m,dict(c.normal));c.pose_route=r
        for t in (20.02,20.12,20.22,20.32,20.42,20.52):self.at(m,b,r,t,42.,False)
        self.assertEqual(r.return_progress,1.)
        self.assertEqual(r.phase,'return')
        b.calls.clear()
        self.at(m,b,r,21.89,42.,False)
        self.assertFalse(any(a==42 for i,a,v in b.calls))
        self.at(m,b,r,21.94,42.,False)
        self.assertEqual(r.phase,'lean')
        self.assertNotEqual(c.state,'FAULT')
