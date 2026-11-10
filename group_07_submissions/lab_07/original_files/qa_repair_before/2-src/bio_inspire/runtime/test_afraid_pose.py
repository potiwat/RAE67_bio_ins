import unittest
import test_three_state_behavior as fixture
from three_state_behavior import handle_state_key


class Tests(unittest.TestCase):
    def motor(self):
        m,b=fixture.Tests().motor();m.afraid_pose_trial_enabled=True
        m.small_happy_trial=True;m.yaw_follow_enabled=False
        m.state_leds_enabled=False;m.happy_speed_raw=750
        m.happy_body_acceleration_raw=3
        b.hold_actual=lambda sid:b.write(sid,42,b.pos[sid].to_bytes(2,'little'))
        return m,b

    def test_afraid_retargets_body_directly_and_gaze_remains_enabled(self):
        from afraid_pose import enter_afraid
        m,b=self.motor();m.behavior_trial='happy';b.calls.clear()
        enter_afraid(m)
        self.assertEqual(m.behavior_trial,'afraid')
        self.assertEqual(b.reg[2][42],m.controller.normal[2]+68)
        self.assertEqual(b.reg[3][42],m.controller.normal[3]-68)
        self.assertTrue(m.follow_enabled and m.yaw_follow_enabled)
        self.assertTrue(all(b.reg[i][46]==400 for i in range(1,6)))
        self.assertEqual([b.reg[i][41] for i in (2,3)],[1,1])
        self.assertFalse(any(a==42 and i in (1,5) for i,a,q in b.calls))
        m.led_ring.afraid.assert_called_once()

    def test_stop_and_bad_feedback_prevent_position_writes(self):
        from afraid_pose import enter_afraid
        m,b=self.motor();m.urgent_stop.set();b.calls.clear()
        enter_afraid(m);self.assertEqual(b.calls,[])
        m.urgent_stop.clear();b.reg[2][65]=4
        with self.assertRaises(RuntimeError):enter_afraid(m)
        self.assertFalse(any(a==42 for i,a,q in b.calls))

    def test_manual_entry_requires_opt_in_and_normal_exits(self):
        m,b=self.motor();m.afraid_pose_trial_enabled=False;b.calls.clear()
        m._key(ord('f'));self.assertEqual(b.calls,[])
        m.afraid_pose_trial_enabled=True;m._key(ord('f'))
        self.assertEqual(m.behavior_trial,'afraid')
        handle_state_key(m,ord('d'));self.assertEqual(m.behavior_trial,'afraid')
        handle_state_key(m,ord('n'));self.assertFalse(m.yaw_follow_enabled)

    def test_route_settles_without_becoming_interested(self):
        from afraid_pose import enter_afraid
        m,b=self.motor();enter_afraid(m)
        b.pos={i:b.reg[i][42] for i in range(1,6)}
        for _ in range(3):m.controller.tick(m.controller.last_tick+.1);m._finish_button_route()
        self.assertEqual(m.behavior_trial,'afraid')
        self.assertEqual(m.controller.pose_route.phase,'held')
        self.assertIsNone(m.controller.pose_route_windows)

    def test_face_loss_does_not_cancel_retreat_monitor(self):
        from afraid_pose import enter_afraid
        m,b=self.motor();enter_afraid(m)
        m._apply(None,20.)
        self.assertEqual(m.controller.pose_route.phase,'retreat')
        b.pos={i:b.reg[i][42] for i in range(1,6)}
        for _ in range(3):m.controller.tick(m.controller.last_tick+.1)
        self.assertIsNone(m.controller.pose_route_windows)

    def test_visible_face_controls_yaw_and_pitch_during_retreat(self):
        from afraid_pose import enter_afraid
        from visual_servo import VisualServo
        from unittest.mock import Mock
        m,b=self.motor();c=m.controller;c.set_direction(1)
        m.visual=VisualServo(c.yaw_window[0],c.yaw_window[1],399.,296.,.25,6.,160.,.5)
        m._apply_pitch=Mock();enter_afraid(m);b.calls.clear()
        for now in (20.,20.1):
            m._apply(dict(observation=dict(status='TRACKING',captured_s=now,source_id=now),intent=dict(mode='FOLLOW',error_xy=(.5,.2))),now)
        self.assertTrue(any(i==1 and a==42 for i,a,q in b.calls))
        self.assertEqual(m._apply_pitch.call_count,2)
        self.assertEqual(c.pose_route.phase,'retreat')

    def test_head_feedback_allowance_survives_entry(self):
        from afraid_pose import enter_afraid
        m,b=self.motor();c=m.controller;c.yaw_window=(1678,2360)
        b.pos[1]=2363;b.reg[1][42]=2360
        enter_afraid(m);c.tick(c.last_tick+.1)
        self.assertNotEqual(c.state,'FAULT')
        self.assertEqual(c.bus.windows[1],c.yaw_window)

    def test_temporary_pitch_extension_contracts_after_head_return(self):
        from afraid_pose import enter_afraid
        m,b=self.motor();c=m.controller;c.behavior_pitch_window=(2355,2901)
        b.pos[5]=2901;b.reg[5][42]=2901
        enter_afraid(m)
        b.pos={i:b.reg[i][42] for i in range(1,6)};b.pos[5]=c.normal[5]
        for _ in range(4):c.tick(c.last_tick+.1)
        self.assertIsNone(c.behavior_pitch_window)
        self.assertEqual(c.feedback_window(5),(c.pitch_window[0]-6,c.pitch_window[1]+6))
