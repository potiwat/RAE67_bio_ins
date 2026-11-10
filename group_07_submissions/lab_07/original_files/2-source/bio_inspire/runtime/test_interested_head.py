import unittest
from visual_servo import VisualServo

class Tests(unittest.TestCase):
    def rows(self,q2=2837,q3=2746,q5=2696):
        return [dict(id=2,position_raw=q2),dict(id=3,position_raw=q3),dict(id=5,position_raw=q5)]
    def model(self):
        from interested_head import InterestedHead
        v=VisualServo(2355,2764,400.,100.,.25,6.,90.,.5)
        return InterestedHead(v,self.rows(),0.)
    def test_actual_body_motion_is_compensated_without_visual_error(self):
        m=self.model();goals=[]
        for n in range(1,11):goals.append(m.step(self.rows(2837-n,2746+n),None,n*.05,n))
        self.assertLess(goals[-1],2696)
        self.assertEqual(m.reference(self.rows(2803,2780)),2628)
    def test_stationary_body_does_not_move_head_without_visual_error(self):
        m=self.model()
        for n in range(1,11):self.assertEqual(m.step(self.rows(),None,n*.05,n),2696)
    def test_waking_reference_is_awake_heading_not_clipped_sleepy_droop(self):
        from interested_head import InterestedHead
        v=VisualServo(2355,2764,400.,100.,.25,6.,90.,.5)
        m=InterestedHead(v,self.rows(q5=2901),0.,entry_pitch=2696)
        self.assertEqual(m.reference(self.rows(q5=2901)),2696)
        self.assertEqual(m.following_error(self.rows(q5=2901)),-205)
        for n in range(1,6):
            goal=m.step(self.rows(2837-n,2746+n,2696),None,n*.05,n)
        self.assertLess(goal,2696)
    def test_ambiguity_does_not_cancel_body_route_or_disable_posture_compensation(self):
        from test_three_state_behavior import Tests as Fixture
        from button_look import begin_button_look
        from visual_servo import VisualServo
        m,b=Fixture().motor();c=m.controller;c.interest_head_tracking=True;c.set_direction(1)
        begin_button_look(c,look_at_button=False)
        m.interest_body_pitch_compensation=True;m.behavior_trial='button_look';m.follow_enabled=True
        m.visual=VisualServo(*c.yaw_window,400.,100.,.25,6.,160.,.5)
        m.pitch_visual=VisualServo(*c.pitch_window,400.,100.,.25,6.,90.,.5)
        m.pitch_direction=1;c.last_rows=b.snapshot()
        m._apply(dict(state='interested',observation=dict(status='AMBIGUOUS',captured_s=0.,source_id=0),intent=dict(mode='HOLD',error_xy=None)),0.)
        b.calls.clear()
        for n in range(1,11):
            b.pos[2]-=1;b.pos[3]+=1;c.last_rows=b.snapshot()
            m._apply(dict(state='interested',observation=dict(status='AMBIGUOUS',captured_s=n*.05,source_id=n),intent=dict(mode='HOLD',error_xy=None)),n*.05)
        self.assertEqual(c.pose_route.phase,'lean')
        self.assertLess(b.reg[5][42],c.normal[5])
        self.assertFalse(any(i in (2,3,4) and a==42 for i,a,v in b.calls))
    def test_compensation_cannot_exceed_existing_awake_window(self):
        m=self.model()
        for n in range(1,101):
            goal=m.step(self.rows(2837-5*n,2746+5*n),None,n*.05,n)
            self.assertTrue(2355<=goal<=2764)
    def test_feedback_cap_does_not_erase_postural_reference(self):
        m=self.model()
        for n in range(1,11):m.step(self.rows(2837-n,2746+n),None,n*.05,n)
        desired=m.visual.position
        m.limit_feedback(2690)
        self.assertEqual(m.visual.position,desired)
    def test_stop_blocks_postural_head_commands(self):
        from test_three_state_behavior import Tests as Fixture
        from interested_head import apply_gaze
        m,b=Fixture().motor();m.stopping.set();b.calls.clear()
        apply_gaze(m,None,0.)
        self.assertEqual(b.calls,[])

class InterestedBoundaryClockTests(unittest.TestCase):
    def test_limit_hold_keeps_both_motion_clocks_alive(self):
        from camera_motor import CameraMotor
        from types import SimpleNamespace
        from unittest.mock import Mock
        import threading
        m=CameraMotor.__new__(CameraMotor)
        m.pitch_enabled=True;m.pitch_direction=1;m.behavior_trial='interested';m.interest_body_pitch_compensation=True
        m.interested_pitch_lead_ticks=34;m.stopping=threading.Event();m.urgent_stop=threading.Event()
        m.controller=SimpleNamespace(pose_route=SimpleNamespace(phase='lean'),last_rows=Tests().rows(q5=2355),goal_pitch=Mock())
        m.pitch_visual=VisualServo(2355,2764,400.,100.,.25,6.,90.,.5)
        m.pitch_reacquire=False
        m._apply_pitch(dict(error_xy=(0.,-1.)),dict(source_id=0,captured_s=0.),0.,True)
        m.last_tracking_error_xy=(0.,-1.)
        for n in range(1,13):
            now=n*.05;m.pitch_reacquire=now<=.5
            m._apply_pitch(dict(mode='SEARCH'),dict(source_id=n,captured_s=now),now,False)
        self.assertAlmostEqual(m.interested_head_model.model.motion.time,.6)
    def test_disabled_yaw_stays_disabled_with_posture_compensation(self):
        from test_three_state_behavior import Tests as Fixture
        from button_look import begin_button_look
        from visual_servo import VisualServo
        m,b=Fixture().motor();c=m.controller;c.interest_head_tracking=True;c.set_direction(1)
        begin_button_look(c,look_at_button=False)
        m.interest_body_pitch_compensation=True;m.behavior_trial='button_look';m.follow_enabled=True;m.yaw_follow_enabled=False
        m.visual=VisualServo(*c.yaw_window,400.,100.,.25,6.,160.,.5)
        m.pitch_visual=VisualServo(*c.pitch_window,400.,100.,.25,6.,90.,.5);m.pitch_direction=1
        b.calls.clear();c.last_rows=b.snapshot()
        m._apply(dict(state='interested',observation=dict(status='TRACKING',captured_s=0.,source_id=1,error_xy=(.8,0.)),intent=dict(mode='FOLLOW',error_xy=(.8,0.))),0.)
        self.assertFalse(any(i==1 and a==42 for i,a,v in b.calls))
