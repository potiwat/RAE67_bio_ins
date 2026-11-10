import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'shared'/'runtime'))
from test_normal_gaze_motor import Bus,NORMAL,ORIGIN
from normal_gaze_motor import NormalGaze
from button_look import begin_button_look,POSE

class Tests(unittest.TestCase):
    def test_cached_player_pose_is_not_mixed_with_sleepy_body_centers(self):
        b,c=self.controller();player=dict(NORMAL);player[1]+=30;player[5]-=20
        c.player_view_reference=player
        c.rhythm_base_reference={2:NORMAL[2],3:NORMAL[3]+153}
        begin_button_look(c,include_interest=False)
        self.assertEqual(c.pose_route.return_pose,player)

    def test_button_motion_capture_survives_idle_and_stays_bounded(self):
        from camera_motor import CameraMotor
        from collections import deque
        from types import SimpleNamespace
        m=CameraMotor.__new__(CameraMotor);m.trace=deque(maxlen=40)
        route=SimpleNamespace(button_dynamic=True,phase='look');m.controller=SimpleNamespace(pose_route=route)
        for n in range(200):m._record_trace(dict(time_s=n,rows=[]))
        route.phase='return'
        for n in range(10):m._record_trace(dict(time_s=200+n,rows=[]))
        route.phase='lean'
        for n in range(1000):m._record_trace(dict(time_s=210+n,rows=[]))
        self.assertEqual(len(m.button_look_trace),180);self.assertEqual(m.button_look_trace[0]['time_s'],20)
        self.assertEqual(len(m.button_return_trace),10)
    def test_dynamic_button_profile_is_validated_before_opening_uart(self):
        import json,tempfile
        from pathlib import Path
        from unittest.mock import patch
        from camera_motor import CameraMotor
        with tempfile.TemporaryDirectory() as folder,patch('camera_motor.open_bus') as bus:
            p=Path(folder)/'p.json';p.write_text(json.dumps(dict(button_look_dynamic_trial=True,motion_speed_raw=400)))
            with self.assertRaisesRegex(ValueError,'Dynamic button'):CameraMotor(p)
            bus.assert_not_called()
    def test_dynamic_button_uses_preferred600_recipe_then_restores_before_return(self):
        b,c=self.controller();c.motion_speed=600;c.button_look_dynamic_trial=True
        original=b.snapshot
        b.snapshot=lambda:[{**r,'goal_raw':b.reg[r['id']][42]} for r in original()]
        begin_button_look(c)
        self.assertEqual([b.reg[i][46] for i in NORMAL],[600]*5)
        self.assertEqual([b.reg[i][41] for i in NORMAL],[3,8,8,12,6])
        self.assertFalse(getattr(b,'button_look_dynamic_acceleration_trial',False))
        b.pos=dict(POSE)
        for t in (4,5,6):c.tick(t)
        self.assertEqual(c.pose_route.phase,'return')
        self.assertEqual([b.reg[i][41] for i in NORMAL],[1]*5)
        self.assertTrue(all(b.reg[i][46]==750 for i in NORMAL))
    def test_direct_interest_skips_dynamic_button_recipe(self):
        b,c=self.controller();c.button_look_dynamic_trial=True
        begin_button_look(c,look_at_button=False)
        self.assertFalse(getattr(c.pose_route,'button_dynamic',False))
        self.assertFalse(any(a==41 and q in (8,12,6) for i,a,q in b.calls))
    def test_speed400_reaches_interest_lean_without_slowing_button_glances(self):
        b,c=self.controller();c.motion_speed=400
        begin_button_look(c)
        self.assertTrue(all(b.reg[i][46]==1000 for i in NORMAL))
        b.pos=dict(POSE)
        for t in (4,5,6):c.tick(t)
        self.assertTrue(all(b.reg[i][46]==750 for i in NORMAL))
        b.pos=dict(NORMAL)
        for t in (7,8,9):c.tick(t)
        self.assertEqual(c.pose_route.phase,'lean')
        self.assertTrue(all(b.reg[i][46]==400 for i in NORMAL))

    def test_head_tracking_is_active_during_lean_without_fixed_head_goal(self):
        b,c=self.controller();c.interest_head_tracking=True;c.face_ready_for_interest=True
        begin_button_look(c);b.pos=dict(POSE)
        for t in (4,5,6):c.tick(t)
        b.pos=dict(NORMAL);b.calls.clear()
        for t in (7,8,9):c.tick(t)
        self.assertEqual(c.pose_route.phase,'lean')
        self.assertTrue(c.pose_route.head_tracking_active)
        self.assertFalse(any(i in (1,5) and a==42 for i,a,v in b.calls))
        c.face_ready_for_interest=False;c.tick(10)
        self.assertTrue(c.pose_route.paused_for_face)
        self.assertEqual(b.reg[2][42],c.pose_route.stage_target[2])
        self.assertEqual(b.reg[2][46],1)
        c.face_ready_for_interest=True;c.tick(11)
        self.assertFalse(c.pose_route.paused_for_face)
        self.assertEqual(b.reg[2][46],100)
        self.assertEqual(b.reg[2][42],c.pose_route.stage_target[2])
        # Head goals now belong to gaze and must not block body arrival.
        target=c.pose_route.stage_target
        b.pos={**target,1:NORMAL[1]+60,5:NORMAL[5]-50}
        for t in (12,13,14):c.tick(t)
        self.assertEqual(c.pose_route.phase,'complete');self.assertEqual(c.state,'READY')

    def test_body_does_not_lean_blindly_before_player_reacquired(self):
        b,c=self.controller();c.interest_head_tracking=True;c.face_ready_for_interest=False
        begin_button_look(c);b.pos=dict(POSE)
        for t in (4,5,6):c.tick(t)
        b.pos=dict(NORMAL)
        for t in (7,8,9,10):c.tick(t)
        self.assertEqual(c.pose_route.phase,'return')
        self.assertEqual(b.reg[2][42],NORMAL[2])
        c.face_ready_for_interest=True;c.tick(11)
        self.assertEqual(c.pose_route.phase,'lean')

    def controller(self):
        b=Bus();c=NormalGaze(b,ORIGIN,NORMAL,manual_tuning=True,tracking_speed=100,tracking_acceleration=3,yaw_range_deg=10,pitch_probe=True,pitch_tracking=True,pitch_range_deg=6,motion_speed=100,normal_tolerances={3:34})
        c.start(0);b.pos=dict(NORMAL)
        for t in (1,2,3):c.tick(t)
        return b,c
    def test_recorded_pose_returns_only_after_arrival_and_restores_guards(self):
        b,c=self.controller();b.pos[3]+=26;begin_button_look(c,include_interest=False)
        c.tick(3.5);self.assertEqual(c.state,'READY')
        self.assertEqual({i:b.reg[i][42] for i in NORMAL},POSE)
        self.assertTrue(all(b.reg[i][46]==1000 for i in NORMAL))
        c.tick(4);self.assertEqual(c.pose_route.phase,'look')
        b.pos=dict(POSE)
        for t in (5,6,7):c.tick(t)
        self.assertEqual(c.pose_route.phase,'return')
        self.assertEqual({i:b.reg[i][42] for i in NORMAL},NORMAL)
        self.assertTrue(all(b.reg[i][46]==750 for i in NORMAL))
        c.tick(8);self.assertEqual(c.state,'READY')
        b.pos=dict(NORMAL)
        for t in (9,10,11):c.tick(t)
        self.assertEqual(c.pose_route.phase,'complete');self.assertIsNone(c.pose_route_windows)
    def test_stop_cancels_route_without_later_replay(self):
        b,c=self.controller();begin_button_look(c,include_interest=False);c.hold('stop',all_axes=True)
        self.assertEqual(c.pose_route.phase,'cancelled')
        b.calls.clear();c.tick(4)
        self.assertEqual(b.calls,[])
    def test_sleepy_can_go_directly_to_button_and_return_to_saved_player_pose(self):
        from sleepy_trial import set_sleepy_trial
        b,c=self.controller();player=dict(NORMAL);player[1]+=30
        b.reg[1][42]=player[1];b.pos[1]=player[1]
        set_sleepy_trial(c,True);b.pos[5]=c.normal[5]+100
        c.player_view_reference=player
        begin_button_look(c,include_interest=False)
        self.assertEqual({i:b.reg[i][42] for i in NORMAL},POSE)
        self.assertEqual(c.pose_route.return_pose,player)
        b.pos=dict(POSE)
        for t in (4,5,6):c.tick(t)
        self.assertEqual({i:b.reg[i][42] for i in NORMAL},player)
    def test_interest_body_and_tilt_share_one_stage_preserving_player_pitch(self):
        b,c=self.controller();begin_button_look(c)
        b.pos=dict(POSE)
        for t in (4,5,6):c.tick(t)
        b.pos=dict(NORMAL)
        for t in (7,8,9):c.tick(t)
        self.assertEqual(c.pose_route.phase,'lean')
        lean={i:b.reg[i][42] for i in NORMAL}
        self.assertEqual(lean[2],NORMAL[2]-102);self.assertEqual(lean[3],NORMAL[3]+102)
        self.assertEqual(lean[5],NORMAL[5])
        self.assertEqual(lean[4],NORMAL[4]-137)
        self.assertEqual(c.pose_route.remaining_steps,[])
        self.assertTrue(all(b.reg[i][46]==100 for i in NORMAL))
        b.pos=dict(lean)
        for t in (10,11,12):c.tick(t)
        self.assertEqual(c.pose_route.phase,'complete')
        tilt={i:b.reg[i][42] for i in NORMAL};self.assertEqual(tilt[4],NORMAL[4]-137)
        self.assertEqual(tilt[5],NORMAL[5])
        b.pos=dict(tilt)
        for t in (13,14,15):c.tick(t)
        self.assertEqual(c.pose_route.phase,'complete');self.assertEqual(c.state,'READY')
        c.tick(16);self.assertEqual(b.reg[4][42],NORMAL[4]-137)
        begin_button_look(c)
        self.assertEqual(c.pose_route.post_steps[-1][1][2],NORMAL[2]-102)
        c.pose_route.return_normal(force_normal=True)
        self.assertTrue(all(b.reg[i][46]==c.motion_speed for i in NORMAL))
        b.pos=dict(NORMAL)
        for t in (17,18,19):c.tick(t)
        self.assertEqual(c.pose_route.phase,'complete')
        self.assertEqual(c.behavior_joint_windows,{})

    def test_camera_interested_sleepy_interested_keeps_body_without_normal_reset(self):
        from camera_motor import CameraMotor
        from types import SimpleNamespace
        from unittest.mock import Mock
        b,c=self.controller();begin_button_look(c)
        for pos,times in ((POSE,(4,5,6)),(NORMAL,(7,8,9))):
            b.pos=dict(pos)
            for t in times:c.tick(t)
        interested={i:b.reg[i][42] for i in NORMAL};b.pos=dict(interested)
        for t in (10,11,12):c.tick(t)
        windows=dict(c.behavior_joint_windows)
        m=CameraMotor.__new__(CameraMotor);m.controller=c;m.bus=b
        m.behavior_trial='interested';m.route_completion_seen=c.pose_route
        m.follow_enabled=True;m.visual=SimpleNamespace(position=None);m.pitch_visual=None
        m.led_ring=Mock();m.pending_behavior=None
        b.calls.clear();m._key(ord('s'))
        self.assertEqual(b.reg[5][42],NORMAL[5]+205)
        self.assertEqual(c.behavior_joint_windows,windows)
        for i in (2,3,4):self.assertEqual(b.reg[i][42],interested[i])
        b.pos[5]=NORMAL[5]+205;c.tick(13);self.assertEqual(c.state,'READY')
        m._key(ord('i'))
        self.assertEqual(c.pose_route.return_pose,interested)
        self.assertEqual({i:b.reg[i][42] for i in NORMAL},POSE)

    def test_loaded_final_pose_keeps_approved_tolerance_after_route_completion(self):
        b,c=self.controller();begin_button_look(c)
        b.pos=dict(POSE)
        for t in (4,5,6):c.tick(t)
        b.pos=dict(NORMAL)
        for t in (7,8,9):c.tick(t)
        b.pos={i:b.reg[i][42] for i in NORMAL}
        for t in (10,11,12):c.tick(t)
        target={i:b.reg[i][42] for i in NORMAL}
        b.pos={**target,2:target[2]-7,3:target[3]+26,4:target[4]-4}
        for t in (13,14,15,16):c.tick(t)
        self.assertEqual(c.pose_route.phase,'complete');self.assertEqual(c.state,'READY')
        for i,tolerance in ((2,34),(3,34),(4,22)):
            self.assertEqual(c.feedback_window(i),(target[i]-tolerance,target[i]+tolerance))
        b.pos[2]=target[2]-35;c.tick(17)
        self.assertEqual(c.state,'FAULT')

class FiniteInterestedTests(unittest.TestCase):
    controller=Tests.controller
    def test_approved_route_finishes_without_face_and_uses_new_speeds(self):
        b,c=self.controller();c.interest_head_tracking=True;c.face_ready_for_interest=False
        c.interest_finish_without_face=True;c.button_look_speed_raw=1250;c.button_return_speed_raw=1000;c.motion_speed=600
        begin_button_look(c)
        self.assertTrue(all(b.reg[i][46]==1250 for i in NORMAL))
        b.pos=dict(POSE)
        for t in (4,5,6):c.tick(t)
        self.assertTrue(all(b.reg[i][46]==1000 for i in NORMAL))
        b.pos=dict(NORMAL)
        for t in (7,8,9):c.tick(t)
        self.assertEqual(c.pose_route.phase,'lean')
        b.pos=dict(c.pose_route.stage_target)
        for t in (10,11,12):c.tick(t)
        self.assertEqual(c.pose_route.phase,'complete');self.assertFalse(c.pose_route.paused_for_face)

class GazePriorityLeanTests(unittest.TestCase):
    controller=Tests.controller
    def native_route(self):
        b,c=self.controller();c.interest_head_tracking=True;c.interest_finish_without_face=True
        c.interest_gaze_priority=True;c.interest_native_neck=True;c.interest_native_body_speed_raw=17
        c.interest_head_following_error=lambda rows:0.;c.interest_head_following_limit=34
        c.lean_command_limits=(100.,100.,.5);c.control_now_s=10.;c.face_ready_for_interest=False
        begin_button_look(c,look_at_button=False)
        return b,c,c.pose_route
    def test_native_body_cannot_start_before_head_compensation_is_initialized(self):
        b,c,r=self.native_route();c.face_ready_for_interest=True;c.interest_head_following_error=None
        c.control_now_s=10.1;c.tick(10.1)
        self.assertTrue(r.waiting_for_player)
        self.assertEqual(b.reg[2][42],NORMAL[2])
    def test_native_body_waits_then_sends_one_final_goal_per_joint(self):
        b,c,r=self.native_route();b.calls.clear()
        c.control_now_s=10.1;c.tick(10.1)
        self.assertFalse(any(i in (2,3,4) and a==42 for i,a,v in b.calls))
        c.face_ready_for_interest=True
        for n in range(2,10):c.control_now_s=10+n*.05;c.tick(c.control_now_s)
        for i in (2,3,4):
            self.assertEqual([v for sid,a,v in b.calls if sid==i and a==42],[r.stage_target[i]])
        self.assertEqual([b.reg[i][46] for i in (2,3)],[17,17])
        self.assertEqual([b.reg[i][41] for i in (2,3)],[1,1])
    def test_native_body_lost_face_slows_without_rebasing_and_resumes(self):
        b,c,r=self.native_route();c.face_ready_for_interest=True;c.control_now_s=10.05;c.tick(10.05)
        b.calls.clear();c.face_ready_for_interest=False
        for t in (10.1,10.2):c.control_now_s=t;c.tick(t)
        self.assertTrue(r.waiting_for_player);self.assertGreater(r.gaze_wait_elapsed_s,0)
        self.assertEqual([b.reg[i][46] for i in (2,3)],[1,1])
        self.assertFalse(any(a==42 for i,a,v in b.calls))
        c.face_ready_for_interest=True;c.control_now_s=10.25;c.tick(10.25)
        self.assertEqual([b.reg[i][46] for i in (2,3)],[17,17])
        self.assertFalse(any(a==42 for i,a,v in b.calls))
    def test_native_body_stale_face_and_head_lag_do_not_start_motion(self):
        b,c,r=self.native_route();c.face_ready_for_interest=True;c.interest_face_stamp=9.
        c.control_now_s=10.1;c.tick(10.1)
        self.assertEqual(b.reg[2][42],NORMAL[2])
        c.interest_face_stamp=10.15;c.interest_head_following_error=lambda rows:70.;c.interest_head_following_limit=34
        c.control_now_s=10.15;c.tick(10.15)
        self.assertEqual(b.reg[2][42],NORMAL[2])
    def test_native_body_completion_restores_base_speed_and_stop_never_replays(self):
        b,c,r=self.native_route();c.face_ready_for_interest=True;c.control_now_s=10.05;c.tick(10.05)
        b.pos=dict(r.stage_target)
        for t in (10.1,10.15,10.2):c.control_now_s=t;c.tick(t)
        self.assertEqual(r.phase,'complete')
        self.assertEqual([b.reg[i][46] for i in (2,3)],[c.motion_speed]*2)
        b,c,r=self.native_route();c.hold('stop',all_axes=True);b.calls.clear()
        c.face_ready_for_interest=True;c.control_now_s=10.1;c.tick(10.1)
        self.assertFalse(b.calls)
    def test_native_body_normal_and_sleepy_restore_speed_without_pid_writes(self):
        from sleepy_trial import set_sleepy_trial
        for destination in ('normal','sleepy'):
            b,c,r=self.native_route();c.face_ready_for_interest=True;c.control_now_s=10.05;c.tick(10.05)
            b.calls.clear()
            if destination=='normal':r.return_normal(force_normal=True)
            else:r.cancel();set_sleepy_trial(c,True)
            self.assertEqual([b.reg[i][46] for i in (2,3)],[c.motion_speed]*2)
            self.assertEqual([b.reg[i][41] for i in (2,3)],[1,1])
            self.assertFalse(any(a==21 for i,a,v in b.calls))
    def test_body_waits_for_head_then_moves_in_bounded_steps(self):
        b,c=self.controller();c.interest_head_tracking=True;c.interest_finish_without_face=True
        c.interest_gaze_priority=True;c.lean_command_limits=(100.,100.,.5);c.control_now_s=10.
        c.interest_face_centered=False
        begin_button_look(c,look_at_button=False)
        route=c.pose_route
        self.assertEqual(b.reg[2][42],NORMAL[2]);self.assertEqual(b.reg[4][42],NORMAL[4])
        for n in range(1,11):c.control_now_s=10+n*.05;c.tick(c.control_now_s)
        self.assertEqual(b.reg[2][42],NORMAL[2]);self.assertTrue(route.waiting_for_player)
        c.interest_face_centered=True;c.face_ready_for_interest=True
        c.control_now_s=10.55;c.tick(c.control_now_s)
        self.assertLessEqual(abs(b.reg[2][42]-NORMAL[2]),1)
        for n in range(12,201):
            c.control_now_s=10+n*.05;b.pos={i:b.reg[i][42] for i in NORMAL};c.tick(c.control_now_s)
        self.assertEqual(route.phase,'complete')
    def test_route_initializes_clock_after_blocking_reads(self):
        b,c=self.controller();c.interest_head_tracking=True;c.interest_finish_without_face=True
        c.interest_gaze_priority=True;c.lean_command_limits=(100.,100.,.5);c.control_now_s=10.
        clock=[10.8];c.control_clock=lambda:clock[0];c.interest_face_centered=True
        begin_button_look(c,look_at_button=False)
        clock[0]=10.85;c.control_now_s=10.85;c.tick(10.85)
        self.assertNotEqual(c.state,'FAULT',c.last_error)
    def test_once_started_small_center_error_does_not_stop_lean(self):
        b,c=self.controller();c.interest_head_tracking=True;c.interest_finish_without_face=True
        c.interest_gaze_priority=True;c.lean_command_limits=(100.,100.,.5);c.control_now_s=10.
        c.interest_face_centered=True;c.face_ready_for_interest=True
        begin_button_look(c,look_at_button=False)
        c.control_now_s=10.05;c.tick(10.05)
        c.interest_face_centered=False;c.control_now_s=10.1;c.tick(10.1)
        self.assertFalse(c.pose_route.waiting_for_player)
    def test_post_health_clock_rejects_face_that_became_stale(self):
        b,c=self.controller();c.interest_head_tracking=True;c.interest_finish_without_face=True
        c.interest_gaze_priority=True;c.lean_command_limits=(100.,100.,.5);c.control_now_s=10.
        clock=[10.];c.control_clock=lambda:clock[0];c.interest_face_centered=True;c.face_ready_for_interest=True
        c.interest_face_stamp=9.8
        begin_button_look(c,look_at_button=False)
        clock[0]=10.35;c.tick(10.35)
        self.assertTrue(c.pose_route.waiting_for_player)
        self.assertEqual(b.reg[2][42],NORMAL[2])
    def test_body_tapers_when_face_drifts_up_even_while_tracking(self):
        ends=[]
        for error in (0.,36.):
            b,c=self.controller();c.interest_head_tracking=True;c.interest_finish_without_face=True
            c.interest_gaze_priority=True;c.lean_command_limits=(100.,100.,.5);c.control_now_s=10.
            c.interest_face_centered=True;c.face_ready_for_interest=True;c.interest_deadband_px=6.;c.interest_vertical_error_px=error
            begin_button_look(c,look_at_button=False)
            for n in range(1,21):
                c.control_now_s=10+n*.05;c.tick(c.control_now_s)
            ends.append(abs(b.reg[2][42]-NORMAL[2]))
        self.assertLess(ends[1],ends[0])
    def test_native_neck_starts_on_fresh_face_without_center_wait_and_has_one_target(self):
        b,c=self.controller();c.interest_head_tracking=True;c.interest_finish_without_face=True
        c.interest_gaze_priority=True;c.interest_native_neck=True;c.lean_command_limits=(100.,100.,.5)
        c.control_now_s=10.;c.face_ready_for_interest=True;c.interest_face_centered=False
        begin_button_look(c,look_at_button=False);b.calls.clear()
        for n in range(1,11):
            c.control_now_s=10+n*.05;c.tick(c.control_now_s)
        neck=[v for i,a,v in b.calls if i==4 and a==42]
        self.assertEqual(neck,[NORMAL[4]-137])
        self.assertFalse(c.pose_route.waiting_for_player)
    def test_native_neck_keeps_current_goal_until_a_fresh_face_exists(self):
        b,c=self.controller();c.interest_head_tracking=True;c.interest_finish_without_face=True
        c.interest_gaze_priority=True;c.interest_native_neck=True;c.lean_command_limits=(100.,100.,.5)
        c.control_now_s=10.;c.face_ready_for_interest=False
        begin_button_look(c,look_at_button=False);b.calls.clear()
        for n in range(1,6):c.control_now_s=10+n*.05;c.tick(c.control_now_s)
        self.assertFalse(any(i==4 and a==42 for i,a,v in b.calls))
        c.face_ready_for_interest=True;c.interest_face_stamp=9.
        c.control_now_s=10.3;c.tick(c.control_now_s)
        self.assertFalse(any(i==4 and a==42 for i,a,v in b.calls))
    def test_return_restores_gaze_owned_head_even_if_route_cache_matches_normal(self):
        b,c=self.controller();c.interest_head_tracking=True;c.interest_finish_without_face=True
        c.interest_gaze_priority=True;c.interest_native_neck=True;c.lean_command_limits=(100.,100.,.5);c.control_now_s=10.
        begin_button_look(c,look_at_button=False)
        b.reg[1][42]=NORMAL[1]+30;b.reg[5][42]=NORMAL[5]+20
        c.last_goal=NORMAL[1]+30;c.last_pitch_goal=NORMAL[5]+20
        c.pose_route.return_normal(force_normal=True)
        self.assertEqual(b.reg[1][42],NORMAL[1]);self.assertEqual(b.reg[5][42],NORMAL[5])
    def test_interested_body_acceleration_trial_and_force_normal_restore(self):
        b,c=self.controller();c.interest_head_tracking=True;c.interest_finish_without_face=True
        c.interest_gaze_priority=True;c.interest_native_neck=True;c.interest_body_acceleration_raw=3
        c.lean_command_limits=(100.,100.,.5);c.control_now_s=10.
        begin_button_look(c,look_at_button=False)
        self.assertEqual([b.reg[i][41] for i in (2,3,4,5)],[3,3,1,1])
        c.pose_route.return_normal(force_normal=True)
        self.assertTrue(all(b.reg[i][41]==1 for i in NORMAL))
    def test_sleepy_does_not_inherit_interested_body_acceleration(self):
        from sleepy_trial import set_sleepy_trial
        b,c=self.controller();c.interest_head_tracking=True;c.interest_finish_without_face=True
        c.interest_gaze_priority=True;c.interest_body_acceleration_raw=3;c.lean_command_limits=(100.,100.,.5);c.control_now_s=10.
        begin_button_look(c,look_at_button=False);c.pose_route.cancel()
        set_sleepy_trial(c,True)
        self.assertEqual([b.reg[i][41] for i in (2,3)],[1,1])
    def test_body_waits_if_measured_head_cannot_follow_posture(self):
        b,c=self.controller();c.interest_head_tracking=True;c.interest_finish_without_face=True
        c.interest_gaze_priority=True;c.interest_native_neck=True;c.lean_command_limits=(100.,100.,.5)
        c.control_now_s=10.;c.face_ready_for_interest=True
        c.interest_head_following_error=lambda rows:70.;c.interest_head_following_limit=34
        begin_button_look(c,look_at_button=False)
        for n in range(1,6):c.control_now_s=10+n*.05;c.tick(c.control_now_s)
        self.assertTrue(c.pose_route.waiting_for_player)
        self.assertEqual(b.reg[2][42],NORMAL[2])
    def test_approved_lean_rate_runs_continuously_with_fresh_face(self):
        b,c=self.controller();c.interest_head_tracking=True;c.interest_finish_without_face=True
        c.interest_gaze_priority=True;c.interest_native_neck=True;c.interest_lean_speed_deg_s=1.5
        c.lean_command_limits=(400.,100.,.5);c.control_now_s=10.;c.face_ready_for_interest=True
        begin_button_look(c,look_at_button=False)
        velocities=[]
        for n in range(1,81):
            c.control_now_s=10+n*.05;b.pos={i:b.reg[i][42] for i in NORMAL};c.tick(c.control_now_s)
            velocities.append(abs(c.pose_route.lean_models[2].velocity))
        self.assertLessEqual(max(velocities),1.5*4096/360+1e-9)
        self.assertTrue(all(v>0 for v in velocities[10:60]))
