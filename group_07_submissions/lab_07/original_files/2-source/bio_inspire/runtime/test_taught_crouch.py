import unittest
import test_afraid_pose as fixture
from afraid_pose import enter_afraid
from three_state_behavior import handle_state_key

POSE={1:2017,2:3165,3:3224,4:1999,5:2044}


class Tests(unittest.TestCase):
    def motor(self):
        m,b=fixture.Tests().motor();m.afraid_taught_pose=dict(POSE)
        m.afraid_crouch_duration_s=10.
        return m,b

    def test_crouch_progresses_ten_seconds_and_caps_at_taught_pose(self):
        m,b=self.motor();entry={i:b.reg[i][42] for i in (2,3,4)}
        enter_afraid(m);c=m.controller
        self.assertEqual({i:b.reg[i][42] for i in entry},entry)
        c.tick(25.)
        for i in entry:self.assertAlmostEqual(b.reg[i][42],(entry[i]+POSE[i])/2,delta=1)
        c.tick(30.)
        self.assertEqual({i:b.reg[i][42] for i in entry},{i:POSE[i] for i in entry})
        for t in (31.,32.,40.):
            b.pos={i:b.reg[i][42] for i in range(1,6)};c.tick(t)
        self.assertEqual(c.pose_route.phase,'held')
        self.assertEqual(b.reg[3][42],3224)
        self.assertEqual(c.active_pitch_window()[0],2044)

    def test_clear_cancels_mid_crouch_and_restores_normal_pitch_bounds(self):
        m,b=self.motor();enter_afraid(m);c=m.controller;c.tick(25.)
        old=c.pose_route;handle_state_key(m,ord('n'))
        self.assertEqual(old.phase,'cancelled')
        self.assertEqual(c.active_pitch_window(),c.pitch_window)
        self.assertEqual(b.reg[2][42],c.normal[2])
        old.step(c.last_rows);self.assertEqual(b.reg[2][42],c.normal[2])

    def test_stop_prevents_further_body_interpolation(self):
        m,b=self.motor();enter_afraid(m);b.calls.clear();m.urgent_stop.set()
        m.controller.pose_route.step(m.controller.last_rows)
        self.assertEqual(b.calls,[])

    def test_entry_from_moving_return_starts_at_current_pose_not_distant_normal_goal(self):
        m,b=self.motor();c=m.controller
        b.pos[2]=3100;b.pos[3]=3100
        enter_afraid(m)
        self.assertEqual(b.reg[2][42],3100)
        self.assertEqual(b.reg[3][42],3100)
        self.assertEqual(c.pose_route.entry[2],3100)

    def test_old_droop_span_is_return_only_not_new_gaze_authority(self):
        m,b=self.motor();c=m.controller;c.behavior_pitch_window=(2355,2901)
        b.pos[5]=2901;b.reg[5][42]=2901
        enter_afraid(m)
        self.assertEqual(c.active_pitch_window(),(2044,2764))
        with self.assertRaises(ValueError):c.goal_pitch(2900)

    def test_head_template_continues_without_face_but_obeys_final_limits(self):
        from taught_crouch_head import TaughtCrouchHead
        from visual_servo import VisualServo
        v=VisualServo(2044,2764,399.,98.,.25,6.,90.,.5)
        h=TaughtCrouchHead(v,2696,0.);last=None
        for n in range(201):
            t=n*.05;u=min(1.,t/10.);weight=u*u*u*(10+u*(-15+6*u))
            q=h.step(2696+(2044-2696)*weight,None,t,n)
            self.assertTrue(2044<=q<=2764)
            if last is not None:self.assertLessEqual(abs(h.motion.velocity-last)/.05,98.+1e-5)
            last=h.motion.velocity
        self.assertLess(q,2100)

    def test_no_face_full_route_keeps_body_folding_and_head_lifting(self):
        from visual_servo import VisualServo
        m,b=self.motor();c=m.controller;c.set_direction(1)
        m.pitch_direction=1
        m.pitch_visual=VisualServo(2355,2764,399.,98.,.25,6.,90.,.5)
        m.visual=VisualServo(c.yaw_window[0],c.yaw_window[1],399.,296.,.25,6.,160.,.5)
        enter_afraid(m)
        for n in range(241):
            now=20+n*.05;b.pos={i:b.reg[i][42] for i in range(1,6)};c.tick(now)
            m._apply(dict(observation=dict(status='LOST',captured_s=now,source_id=n),intent=dict(mode='SEARCH',error_xy=None)),now)
            self.assertNotEqual(c.state,'FAULT')
        self.assertEqual(b.reg[2][42],3165);self.assertEqual(b.reg[3][42],3224)
        self.assertLess(b.reg[5][42],2100)
        self.assertEqual(c.pose_route.phase,'held')

    def test_inherited_head_droop_returns_and_contracts_without_new_downward_authority(self):
        from visual_servo import VisualServo
        m,b=self.motor();c=m.controller;c.set_direction(1)
        c.behavior_pitch_window=(2355,2901);b.pos[5]=2901;b.reg[5][42]=2901
        m.pitch_direction=1;m.pitch_visual=VisualServo(2355,2764,399.,98.,.25,6.,90.,.5)
        m.visual=VisualServo(c.yaw_window[0],c.yaw_window[1],399.,296.,.25,6.,160.,.5)
        enter_afraid(m);previous=2901
        for n in range(241):
            now=20+n*.05;b.pos={i:b.reg[i][42] for i in range(1,6)};c.tick(now)
            m._apply(dict(observation=dict(status='LOST',captured_s=now,source_id=n),intent=dict(mode='SEARCH',error_xy=None)),now)
            self.assertNotEqual(c.state,'FAULT')
            q=b.reg[5][42]
            if q>2764:self.assertLessEqual(q,previous)
            previous=q
        self.assertEqual(c.pose_route.head_window,(2044,2764))
        self.assertEqual(c.behavior_pitch_window,(2044,2764))

    def test_approved_six_second_crouch_reaches_same_cap(self):
        m,b=self.motor();m.afraid_crouch_duration_s=6.
        enter_afraid(m);c=m.controller
        c.tick(23.);self.assertAlmostEqual(c.pose_route.progress,.5)
        c.tick(26.);self.assertEqual(c.pose_route.progress,1.)
        self.assertEqual(b.reg[2][42],POSE[2]);self.assertEqual(b.reg[3][42],POSE[3])

    def test_long_held_tail_does_not_erase_crouch_motion_evidence(self):
        from collections import deque
        m,b=self.motor();m.trace=deque(maxlen=180)
        moving=dict(behavior='afraid',state='READY',crouch_progress=.5,time_s=20.,rows=[])
        m._record_trace(moving)
        for n in range(300):
            m._record_trace(dict(behavior='afraid',state='READY',crouch_progress=1.,time_s=21.+n,rows=[dict(id=2,speed_raw=0,moving_raw=0),dict(id=3,speed_raw=0,moving_raw=0)]))
        self.assertIn(moving,list(m.afraid_motion_trace))

    def test_return_keeps_previous_head_envelope_until_native_reversal_settles(self):
        m,b=self.motor();enter_afraid(m);c=m.controller
        # Reproduce live reversal: encoder2169, old head goal2077, then
        # encoder coasts to2131 after the Normal2696 command is accepted.
        b.pos[5]=2169;b.reg[5][42]=2077
        old_window=c.feedback_window(5)
        handle_state_key(m,ord('n'))
        self.assertEqual(b.reg[5][42],c.normal[5])
        self.assertLessEqual(c.feedback_window(5)[0],old_window[0])
        b.pos[5]=2131;c.tick(c.last_tick+.1)
        self.assertNotEqual(c.state,'FAULT')
        for n in range(3):
            b.pos={i:c.normal[i] for i in c.normal};c.tick(c.last_tick+.1)
        self.assertEqual(c.pose_route.phase,'complete')
        self.assertIsNone(c.pose_route_windows)
        self.assertGreater(c.feedback_window(5)[0],2131)

    def test_six_second_response_moves_more_in_first_half_second_without_changing_cap(self):
        m,b=self.motor();m.afraid_crouch_duration_s=6.
        enter_afraid(m);c=m.controller;entry=c.pose_route.entry[3]
        c.tick(20.5)
        quintic=(.5/6.)**3*(10-15*(.5/6.)+6*(.5/6.)**2)
        self.assertGreater(c.pose_route.progress,quintic*3.)
        self.assertGreater(b.reg[3][42],entry)
        c.tick(26.);self.assertEqual(b.reg[3][42],POSE[3])
