import unittest
from unittest.mock import Mock
import test_three_state_behavior as fixture
from head_roll_probe import handle_probe_key

class Tests(unittest.TestCase):
    def motor(self):
        m,b=fixture.Tests().motor();m.head4_probe_enabled=True
        m.latest_result={'observation':{'status':'TRACKING','captured_s':20.,'source_id':1,'error_xy':(.2,.1)}}
        return m,b
    def test_probe_then_return_changes_only_roll_target_and_masks_follow(self):
        m,b=self.motor();base=b.reg[4][42]
        handle_probe_key(m,ord('p'))
        self.assertTrue(m.head_probe_active);self.assertFalse(m.follow_enabled)
        self.assertEqual(b.reg[4][42],base+34)
        for sid in (1,2,3,5):self.assertEqual(b.reg[sid][42],m.controller.normal[sid])
        handle_probe_key(m,ord('o'));self.assertEqual(b.reg[4][42],base)
    def test_no_probe_without_fresh_face_or_after_operator_stop(self):
        m,b=self.motor();m.latest_result['observation']['captured_s']=18.
        handle_probe_key(m,ord('p'));self.assertEqual(b.calls,[])
        m.latest_result['observation']['captured_s']=20.;m.operator_stopped=True
        handle_probe_key(m,ord('p'));self.assertEqual(b.calls,[])
    def test_observer_uses_owner_rows_without_extra_bus_reads_or_writes(self):
        m,b=self.motor();handle_probe_key(m,ord('p'))
        b.pos[4]=b.reg[4][42];m.controller.last_rows=b.snapshot();b.calls.clear()
        for now in (22.,22.1,22.2,22.3,22.4):
            m.now=lambda:now
            m.latest_result['observation']['captured_s']=now-.1
            m._observe_head_probe()
        self.assertEqual(b.calls,[])
        sample=m.head_probe_recorder.samples[-1]
        self.assertTrue(sample['valid_observation'])
        self.assertEqual(sample['actual_raw'],b.reg[4][42])
        self.assertEqual(m.controller.state,'READY')
    def test_stop_or_normal_invalidates_pending_probe_observation(self):
        for key in ('h','n'):
            with self.subTest(key=key):
                m,b=self.motor();handle_probe_key(m,ord('p'))
                b.pos[4]=b.reg[4][42];m.controller.last_rows=b.snapshot()
                m._key(ord(key))
                for now in (22.,22.1,22.2,22.3,22.4):
                    m.now=lambda:now
                    m.latest_result['observation']['captured_s']=now-.1
                    m._observe_head_probe()
                self.assertFalse(m.head_probe_recorder.samples[-1]['valid_observation'])
    def test_id5_profile_positive_and_return_leave_roll_and_body_fixed(self):
        m,b=self.motor();m.head_probe_joint_id=5;base=b.reg[5][42]
        handle_probe_key(m,ord('p'))
        self.assertEqual(b.reg[5][42],base+34)
        self.assertEqual(b.reg[4][42],m.controller.normal[4])
        self.assertEqual(m.head_probe_recorder.pending['joint_id'],5)
        handle_probe_key(m,ord('o'))
        self.assertEqual(b.reg[5][42],base)
    def test_id5_relative_probe_never_expands_awake_pitch_window(self):
        m,b=self.motor();m.head_probe_joint_id=5
        b.reg[5][42]=m.controller.pitch_window[1]-10
        m.head_probe_active=True;m.head_probe_base=b.reg[5][42];b.calls.clear()
        handle_probe_key(m,ord('p'))
        self.assertEqual(b.calls,[])
        self.assertIn('range',m.tune_status.lower())
    def test_queued_probe_return_cannot_run_after_stop_or_close_signal(self):
        for flag in ('urgent_stop','stopping'):
            m,b=self.motor();m.head_probe_joint_id=5;handle_probe_key(m,ord('p'));b.calls.clear()
            getattr(m,flag).set();m.latest_result=None
            handle_probe_key(m,ord('o'))
            self.assertEqual(b.calls,[])
    def test_stop_during_speed_write_prevents_probe_position_write(self):
        m,b=self.motor();m.head_probe_joint_id=5;handle_probe_key(m,ord('o'));b.calls.clear()
        original=b.write
        def write(sid,address,data):
            original(sid,address,data)
            if address==46:m.urgent_stop.set()
        b.write=write
        handle_probe_key(m,ord('p'))
        self.assertFalse(any(address==42 for _,address,_ in b.calls))
    def test_body_probe_uses_approved_command3_and_feedback6_without_head_motion(self):
        for sid in (2,3):
            with self.subTest(joint=sid):
                m,b=self.motor();m.head_probe_joint_id=sid;m.body_probe_selection_enabled=True
                m.controller.normal_tolerances.update({2:34,3:34})
                base=m.controller.normal[sid]
                handle_probe_key(m,ord('p'))
                self.assertEqual(b.reg[sid][42],base+34)
                self.assertEqual(b.windows[sid],(base-34,base+34))
                self.assertEqual(m.controller.feedback_window(sid),(base-68,base+68))
                for other in (1,4,5):self.assertEqual(b.reg[other][42],m.controller.normal[other])
                handle_probe_key(m,ord('o'));self.assertEqual(b.reg[sid][42],base)
    def test_body_probe_requires_explicit_profile_and_normal_context(self):
        m,b=self.motor();m.head_probe_joint_id=2
        handle_probe_key(m,ord('p'));self.assertEqual(b.calls,[])
        m.body_probe_selection_enabled=True;b.reg[2][42]=m.controller.normal[2]+100
        handle_probe_key(m,ord('p'));self.assertEqual(b.calls,[])
    def test_selecting_next_joint_does_not_move_and_requires_return_first(self):
        m,b=self.motor();m.body_probe_selection_enabled=True;m.head_probe_joint_id=2
        m.controller.normal_tolerances.update({2:34,3:34})
        handle_probe_key(m,ord('p'));b.calls.clear();handle_probe_key(m,ord('3'))
        self.assertEqual(m.head_probe_joint_id,2);self.assertEqual(b.calls,[])
        handle_probe_key(m,ord('o'));b.calls.clear();handle_probe_key(m,ord('3'))
        self.assertEqual(m.head_probe_joint_id,3);self.assertEqual(b.calls,[])
    def pitch_trial(self):
        from visual_servo import VisualServo
        m,b=self.motor();m.head_probe_joint_id=2;m.body_probe_selection_enabled=True
        m.body_probe_pitch_follow_enabled=True;m.head_probe_active=True
        m.gaze_enabled=False;m.pitch_enabled=True;m.pitch_direction=1
        m.pitch_visual=VisualServo(*m.controller.pitch_window,100.,100.,.25,6.,90.,.5)
        m.controller.last_rows=b.snapshot();b.calls.clear()
        return m,b
    def result(self,now,error=.8):
        return dict(state='normal',observation=dict(status='TRACKING',captured_s=now-.05,source_id=now),
                    intent=dict(mode='FOLLOW',error_xy=(0.,error)))
    def test_body_pitch_follow_only_writes_id5_and_keeps_body_goal(self):
        m,b=self.pitch_trial();before=b.reg[2][42]
        for now in (20.,20.2,20.4):m._apply(self.result(now),now)
        self.assertTrue(any(sid==5 and address==42 for sid,address,_ in b.calls))
        self.assertTrue(all(sid==5 for sid,address,_ in b.calls))
        self.assertEqual(b.reg[2][42],before)
    def test_body_pitch_follow_stale_and_stop_do_not_send_goals(self):
        m,b=self.pitch_trial()
        m._apply(self.result(20.),20.);b.calls.clear()
        m._apply(self.result(19.),21.)
        self.assertEqual(b.calls,[])
        m.urgent_stop.set();m._apply(self.result(21.1),21.1)
        self.assertEqual(b.calls,[])
    def test_head_probe_id5_does_not_run_body_pitch_feedback(self):
        m,b=self.pitch_trial();m.head_probe_joint_id=5
        for now in (20.,20.2,20.4):m._apply(self.result(now),now)
        self.assertEqual(b.calls,[])
    def test_body_initial_context_rejection_never_writes_hold_outside_command(self):
        m,b=self.motor();m.body_probe_selection_enabled=True;m.head_probe_joint_id=2
        m.controller.normal_tolerances.update({2:34,3:34})
        b.pos[2]=m.controller.normal[2]+50;m.controller.last_rows=b.snapshot();b.calls.clear()
        handle_probe_key(m,ord('p'))
        self.assertEqual(b.calls,[])
        self.assertFalse(getattr(m,'head_probe_active',False))
    def test_rejected_first_body_goal_cannot_activate_pitch_follow(self):
        m,b=self.pitch_trial();m.head_probe_active=False
        m.controller.normal_tolerances.update({2:34,3:34})
        b.reg[2][42]=m.controller.normal[2]+20;b.calls.clear()
        handle_probe_key(m,ord('p'))
        self.assertFalse(m.head_probe_active)
        for now in (20.,20.2,20.4):m._apply(self.result(now),now)
        self.assertEqual(b.calls,[])
    def test_fresh_worker_default_normal_state_runs_body_pitch_follow(self):
        m,b=self.pitch_trial()
        # Real CameraMotor initially has no behavior_trial attribute; legacy
        # worker/reporting paths consistently interpret that as Normal.
        del m.behavior_trial
        for now in (20.,20.2,20.4):m._apply(self.result(now),now)
        self.assertTrue(any(sid==5 and address==42 for sid,address,_ in b.calls))

    def test_body_lost_face_continues_recent_exit_then_expires(self):
        m,b=self.pitch_trial()
        for now in (20.,20.1,20.2):m._apply(self.result(now,-.8),now)
        before=b.reg[5][42];b.calls.clear()
        lost=dict(state='normal',observation=dict(status='LOST',captured_s=20.3,source_id=99),intent=dict(mode='SEARCH',error_xy=None))
        m._apply(lost,20.3)
        self.assertLess(b.reg[5][42],before)
        self.assertTrue(all(sid==5 for sid,_,_ in b.calls))
        b.calls.clear();lost['observation']['captured_s']=21.
        m._apply(lost,21.)
        self.assertEqual(b.calls,[])
    def test_body_search_does_not_use_stale_camera_or_sleepy(self):
        for kind in ('stale','sleepy','stop'):
            m,b=self.pitch_trial();m._apply(self.result(20.,-.8),20.);b.calls.clear()
            lost=dict(state='normal',observation=dict(status='LOST',captured_s=20.1,source_id=99),intent=dict(mode='SEARCH',error_xy=None))
            now=20.2
            if kind=='stale':lost['observation']['captured_s']=19.
            if kind=='sleepy':m.behavior_trial='sleepy'
            if kind=='stop':m.urgent_stop.set()
            m._apply(lost,now);self.assertEqual(b.calls,[])
