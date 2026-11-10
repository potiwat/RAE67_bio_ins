import unittest
import test_button_look as fixture

class Tests(unittest.TestCase):
    def route(self):
        b,c,r=fixture.GazePriorityLeanTests().native_route()
        c.interested_gentle_entry=True;c.motion_speed=600;c.interest_native_body_speed_raw=600
        c.face_ready_for_interest=True
        return b,c,r
    def test_interested_uses_slower_body_and_neck_without_resending_targets(self):
        b,c,r=self.route();b.calls.clear()
        for t in (10.05,10.1,10.15):c.control_now_s=t;c.tick(t)
        self.assertEqual([b.reg[i][46] for i in (2,3,4)],[150,150,100])
        for i in (2,3,4):self.assertEqual([v for sid,a,v in b.calls if sid==i and a==42],[r.stage_target[i]])
        self.assertFalse(getattr(b,'interested_gentle_entry_trial',False))
    def test_angry_shared_route_keeps_original_native_speed(self):
        b,c,r=self.route();r.completion_behavior='angry';before=b.reg[4][46]
        c.control_now_s=10.05;c.tick(10.05)
        self.assertEqual([b.reg[i][46] for i in (2,3)],[600,600])
        self.assertEqual(b.reg[4][46],before)
    def test_complete_restores_all_three_speeds(self):
        b,c,r=self.route();c.control_now_s=10.05;c.tick(10.05)
        b.pos=dict(r.stage_target)
        for t in (10.1,10.15,10.2):c.control_now_s=t;c.tick(t)
        self.assertEqual(r.phase,'complete')
        self.assertEqual([b.reg[i][46] for i in (2,3,4)],[600]*3)
    def test_gentle_profile_must_use_existing_fast_native_compensation(self):
        from awake_motion import validate
        good=dict(fast_awake_trial=True,motion_speed_raw=600,automatic_fsm_enabled=True,
                  native_posture_compensation=True,interested_gentle_entry=True,
                  interest_native_neck=True,interest_native_body_speed_raw=600,interest_gaze_priority=True)
        self.assertTrue(validate(good))
        for change in ({'interested_gentle_entry':1},{'interest_native_body_speed_raw':17},{'interest_native_neck':False}):
            with self.assertRaises(ValueError):validate({**good,**change})

    def test_button_glance_and_return_keep_original_fast_speeds(self):
        from button_look import begin_button_look,POSE
        b,c=fixture.Tests().controller()
        c.motion_speed=600;c.interested_gentle_entry=True
        c.button_look_speed_raw=1250;c.button_return_speed_raw=1000
        begin_button_look(c)
        self.assertEqual([b.reg[i][46] for i in range(1,6)],[1250]*5)
        b.pos=dict(POSE)
        for t in (4,5,6):c.tick(t)
        self.assertEqual(c.pose_route.phase,'return')
        self.assertEqual([b.reg[i][46] for i in range(1,6)],[1000]*5)
    def test_missing_face_does_not_skip_or_pause_recorded_gentle_pose(self):
        b,c,r=self.route();c.face_ready_for_interest=False;b.calls.clear()
        c.control_now_s=10.05;c.tick(10.05)
        self.assertTrue(r.native_lean_started)
        self.assertFalse(r.waiting_for_player)
        for i in (2,3,4):self.assertEqual(b.reg[i][42],r.stage_target[i])
        c.face_ready_for_interest=True;c.control_now_s=10.1;c.tick(10.1)
        self.assertEqual([b.reg[i][46] for i in (2,3,4)],[150,150,100])
        c.face_ready_for_interest=False;c.control_now_s=10.15;c.tick(10.15)
        self.assertEqual([b.reg[i][46] for i in (2,3)],[150,150])
        self.assertEqual(r.gaze_wait_elapsed_s,0.)
        c.face_ready_for_interest=True;c.control_now_s=10.2;c.tick(10.2)
        self.assertEqual([b.reg[i][46] for i in (2,3,4)],[150,150,100])
        b.pos=dict(r.stage_target)
        for t in (10.25,10.3,10.35):c.control_now_s=t;c.tick(t)
        self.assertEqual(r.phase,'complete')
