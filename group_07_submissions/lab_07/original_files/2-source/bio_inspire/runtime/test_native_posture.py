import unittest
from visual_servo import VisualServo
from taught_crouch_head import TaughtCrouchHead
from interested_head import InterestedHead,active,apply_gaze


def rows(q2=2837,q3=2746,q5=2696):
    return [dict(id=2,position_raw=q2),dict(id=3,position_raw=q3),dict(id=5,position_raw=q5)]


class Tests(unittest.TestCase):
    def test_gentle_interested_head_tracks_measured_arms_instead_of_jumping_to_endpoint(self):
        from button_look import begin_button_look
        m,b=self.motor();c=m.controller
        c.interested_gentle_entry=True;c.interest_finish_without_face=True
        begin_button_look(c,look_at_button=False)
        m.behavior_trial='interested_transition';m.follow_enabled=True
        def lost(t):
            m._apply(dict(observation=dict(status='LOST',captured_s=t,source_id=t),
                          intent=dict(mode='HOLD',error_xy=None)),t)
        lost(20.05);c.control_now_s=20.1;c.tick(20.1);lost(20.1)
        self.assertTrue(c.pose_route.native_lean_started)
        self.assertGreaterEqual(b.reg[5][42],c.normal[5]-34)
        last=b.reg[5][42]
        for n in range(1,11):
            b.pos[2]=c.normal[2]-10*n;b.pos[3]=c.normal[3]+10*n
            c.last_rows=b.snapshot();lost(20.1+n*.05)
            self.assertLessEqual(b.reg[5][42],last)
            measured=c.normal[5]-20*n
            self.assertGreaterEqual(b.reg[5][42],measured-34)
            last=b.reg[5][42]
        self.assertEqual(b.reg[5][42],c.normal[5]-204)
    def test_happy_fresh_face_loss_keeps_body_compensation_without_extra_search(self):
        m,b=self.motor();c=m.controller
        m.small_happy_trial=True;m.behavior_trial='happy';m.happy_head_wake_goal=None
        m.follow_enabled=True
        def frame(t,status,mode):
            return dict(observation=dict(status=status,captured_s=t,source_id=t),
                        intent=dict(mode=mode,error_xy=(0.,0.)))
        m._apply(frame(20.,'TRACKING','FOLLOW'),20.)
        model=m.interested_head_model
        for t in (20.2,20.4,20.6,20.8):
            m.posture_body_plan=dict(mode='happy',time_s=t,goals={2:c.normal[2]-40,3:c.normal[3]+40})
            m._apply(frame(t,'LOST','SEARCH'),t)
        self.assertIs(m.interested_head_model,model)
        self.assertFalse(m.pitch_reacquire) # .5s search budget remains expired
        self.assertEqual(b.reg[5][42],c.normal[5]-80)

    def visual(self):return VisualServo(2355,2764,400.,100.,.25,6.,90.,.5)
    def test_native_posture_is_immediate_but_visual_correction_is_still_acceleration_limited(self):
        v=self.visual();m=TaughtCrouchHead(v,2696,0.,native_posture=True)
        self.assertEqual(m.step(2496,None,.05,1),2496)
        self.assertAlmostEqual(m.step(2496,90.,.1,2),2496,delta=1)
        self.assertLessEqual(abs(v.velocity),5.+1e-9)
        self.assertTrue(2355<=m.step(2000,None,.15,3)<=2764)
    def test_native_plan_compensates_before_measured_body_moves_and_does_not_count_anticipation_as_lag(self):
        m=InterestedHead(self.visual(),rows(),0.,native_posture=True)
        goal=m.step(rows(),None,.05,1,body_target={2:2735,3:2848})
        self.assertEqual(goal,2492)
        self.assertEqual(m.following_error(rows()),0.)
        self.assertEqual(m.following_error(rows(q5=2600)),0.)
        self.assertLess(m.following_error(rows(2787,2796,2696)),-34)
    def test_awake_body_gaze_modes_use_shared_model_but_sleepy_and_happy_wake_do_not(self):
        from types import SimpleNamespace
        m=SimpleNamespace(native_posture_compensation=True,controller=SimpleNamespace(pose_route=None))
        for mode in ('normal','happy'):
            m.behavior_trial=mode;self.assertTrue(active(m))
        m.happy_head_wake_goal=2696;self.assertFalse(active(m))
        m.happy_head_wake_goal=None;m.behavior_trial='sleepy';self.assertFalse(active(m))
    def motor(self):
        from test_angry import MotionTests
        from camera_motor import CameraMotor
        m,b=MotionTests().motor();c=m.controller;c.set_direction(1)
        m.native_posture_compensation=True;m.pitch_direction=1
        m.pitch_visual=self.visual();m.visual=VisualServo(*c.yaw_window,400.,100.,.25,6.,160.,.5)
        m._reset_pitch=CameraMotor._reset_pitch.__get__(m)
        return m,b
    def gaze(self,m,t,xy=(0.,0.)):
        m._apply(dict(state='normal',observation=dict(status='TRACKING',captured_s=t,source_id=t),
            intent=dict(mode='FOLLOW',error_xy=xy)),t)
    def test_full_head_compensation_is_sent_in_body_release_cycle_before_body_feedback_moves(self):
        from angry_behavior import enter_angry
        m,b=self.motor();c=m.controller
        enter_angry(m);m._service_interested_gaze()
        c.control_now_s=20.05;c.tick(20.05);self.gaze(m,20.05)
        b.calls.clear();c.control_now_s=20.1;c.tick(20.1);self.gaze(m,20.1)
        self.assertTrue(c.pose_route.native_lean_started)
        self.assertEqual(b.reg[2][42],c.normal[2]-102)
        self.assertEqual(b.reg[3][42],c.normal[3]+102)
        self.assertEqual(b.reg[5][42],c.normal[5]-204)
        self.assertFalse(m.interested_pitch_feedback_limited)
        self.assertNotEqual(c.state,'FAULT',c.last_error)
        m.urgent_stop.set();b.calls.clear();self.gaze(m,20.15);self.assertEqual(b.calls,[])
    def test_normal_cpg_plan_compensates_head_but_happy_never_double_writes_yaw(self):
        for mode in ('normal','happy'):
            m,b=self.motor();c=m.controller;m.behavior_trial=mode;m.follow_enabled=True
            m.posture_body_plan=dict(mode=mode,time_s=20.05,goals={2:c.normal[2]-10,3:c.normal[3]+10})
            b.calls.clear();self.gaze(m,20.05,xy=(.8,0.))
            self.assertEqual(b.reg[5][42],c.normal[5]-20)
            self.assertTrue(m.interested_head_model.model.native_posture)
            if mode=='happy':self.assertFalse(any(i==1 and a==42 for i,a,q in b.calls))
    def test_afraid_uses_same_native_posture_model_with_existing_taught_bounds(self):
        from afraid_pose import enter_afraid,apply_afraid_gaze
        m,b=self.motor();c=m.controller;enter_afraid(m);c.tick(25.)
        apply_afraid_gaze(m,dict(observation=dict(status='TRACKING',captured_s=25.,source_id=1),
            intent=dict(mode='FOLLOW',error_xy=(0.,0.))),25.)
        self.assertTrue(m.afraid_head_model.native_posture)
        self.assertAlmostEqual(b.reg[5][42],c.pose_route.head_reference(),delta=1)
        self.assertTrue(c.active_pitch_window()[0]<=b.reg[5][42]<=c.active_pitch_window()[1])
    def test_reset_and_stale_plan_cannot_replay_old_body_compensation(self):
        m,b=self.motor();c=m.controller;m.follow_enabled=True;m.behavior_trial='normal'
        m.posture_body_plan=dict(mode='normal',time_s=10.,goals={2:c.normal[2]-100,3:c.normal[3]+100})
        self.gaze(m,20.05)
        self.assertEqual(b.reg[5][42],c.normal[5])
        m._reset_pitch();self.assertIsNone(m.posture_body_plan)
    def test_full_cpg_then_head_cycle_uses_exact_current_body_goals(self):
        from state_rhythms import StateRhythms
        from unittest.mock import Mock
        m,b=self.motor();c=m.controller;m.behavior_trial='normal';m.follow_enabled=True
        m.rhythm_driver=StateRhythms(Mock(),Mock());m.rhythm_normal_gaze_started=False
        for n in range(21):
            now=20+n*.05;m.now=lambda t=now:t
            c.last_rows=b.snapshot();m._service_body_rhythm();self.gaze(m,now)
            plan=m.posture_body_plan;h=m.interested_head_model
            self.assertEqual(plan['time_s'],now)
            expected=h.entry_pitch+(plan['goals'][2]-h.entry[2])-(plan['goals'][3]-h.entry[3])
            self.assertEqual(b.reg[5][42],round(max(h.visual.low,min(h.visual.high,expected))))
            b.pos={i:b.reg[i][42] for i in c.normal}
