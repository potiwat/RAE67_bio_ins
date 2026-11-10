import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
import test_button_look
from test_normal_gaze_motor import NORMAL
from camera_motor import CameraMotor
from three_state_behavior import handle_state_key,service_state_outputs,apply_sleepy_yaw


class Tests(unittest.TestCase):
    def motor(self):
        b,c=test_button_look.Tests().controller();c.motion_speed=400
        c.pitch_window=(2355,2764);c.interest_head_tracking=True
        c.interest_pitch_window_request=c.pitch_window;c.face_ready_for_interest=True
        m=CameraMotor.__new__(CameraMotor);m.bus=b;m.controller=c;m.lock=threading.Lock()
        m.behavior_trial='normal';m.pending_behavior=None;m.operator_stopped=False
        m.gaze_enabled=True;m.pitch_enabled=True;m.yaw_follow_enabled=True
        m.state_leds_enabled=True
        m.pitch_clearance_confirmed=True;m.yaw_clearance_confirmed=True
        m.follow_enabled=False;m.held=False;m.joint_mode=False;m.sleepy_trial_active=False
        m.visual=SimpleNamespace(position=None);m._reset_pitch=Mock();m.now=lambda:20.
        m.interested_roll_due=None;m.led_ring=Mock();m.route_completion_seen=None
        m.stopping=threading.Event();m.urgent_stop=threading.Event()
        m._hold=lambda why,all_axes=False:c.hold(why,all_axes)
        b.calls.clear();return m,b
    def settle(self,m,b):
        for n in range(1,16):
            b.pos={i:b.reg[i][42] for i in NORMAL}
            m.controller.tick(m.controller.last_tick+.1)
            m._finish_button_route()
            route=getattr(m.controller,'pose_route',None)
            if route is None or route.phase in ('complete','cancelled'):return
        self.fail('route did not finish')
    def test_all_six_directed_pairs_have_no_forced_normal_except_normal_target(self):
        for source,target in (('normal','interested'),('normal','sleepy'),('interested','normal'),('interested','sleepy'),('sleepy','normal'),('sleepy','interested')):
            with self.subTest(source=source,target=target):
                m,b=self.motor()
                if source=='interested':handle_state_key(m,ord('i'));self.settle(m,b)
                elif source=='sleepy':handle_state_key(m,ord('s'));self.settle(m,b)
                b.calls.clear();handle_state_key(m,ord(target[0]));self.settle(m,b)
                self.assertEqual(m.behavior_trial,target)
                route=getattr(m.controller,'pose_route',None)
                if target=='normal':
                    self.assertTrue(route.force_normal)
                    self.assertTrue(all(b.reg[i][42]==NORMAL[i] for i in NORMAL))
                elif target=='interested':self.assertFalse(route.force_normal)
                else:
                    self.assertEqual(b.reg[5][42],2901)
                    self.assertFalse(any(i in (2,3) and a==42 and v==NORMAL[i] for i,a,v in b.calls))
    def test_sleepy_interrupts_face_waiting_lean_without_normal_detour(self):
        m,b=self.motor();handle_state_key(m,ord('i'))
        route=m.controller.pose_route;route.phase='lean';route.head_tracking_active=True
        b.pos={**NORMAL,2:2780,3:2800,4:1800,5:3000}
        for i in NORMAL:b.reg[i][42]=b.pos[i]
        m.controller.face_ready_for_interest=False;b.calls.clear()
        handle_state_key(m,ord('s'))
        self.assertEqual(m.behavior_trial,'sleepy')
        self.assertEqual(b.reg[2][42],2780);self.assertEqual(b.reg[3][42],2800)
        self.assertEqual(b.reg[5][42],2901)
        m.controller.tick(m.controller.last_tick+.1)
        self.assertNotEqual(m.controller.state,'FAULT')
        from body_rhythm import BodyRhythmDriver
        d=BodyRhythmDriver(sleepy_amplitude_deg=2.);d.step(m,0.);d.step(m,2.)
        self.assertEqual(m.controller.current_roll_goal,1800)
        self.assertEqual(b.reg[4][42],1800)
    def test_stop_and_fault_block_emotion_motion_until_explicit_resume(self):
        m,b=self.motor();m.operator_stopped=True
        for key in ('i','s'):handle_state_key(m,ord(key))
        self.assertEqual(b.calls,[])
        m.controller.state='FAULT'
        for key in ('n','i','s'):handle_state_key(m,ord(key))
        self.assertEqual(b.calls,[])
    def test_startup_queues_latest_behavior_without_motion(self):
        m,b=self.motor();m.controller.state='NORMAL_STARTUP'
        handle_state_key(m,ord('i'));handle_state_key(m,ord('s'))
        self.assertEqual(m.pending_behavior,ord('s'));self.assertEqual(b.calls,[])
    def test_sleepy_yaw_follow_does_not_overwrite_droop(self):
        from visual_servo import VisualServo
        m,b=self.motor();handle_state_key(m,ord('s'));m.follow_enabled=True
        m.visual=VisualServo(1900,2140,100,100,.25,6,160,.5)
        m.controller.last_rows=b.snapshot();m.controller.set_direction(1);b.calls.clear()
        result=dict(observation=dict(status='TRACKING',captured_s=1.,source_id=1),intent=dict(mode='FOLLOW_DROOP',error_xy=(.5,0.)))
        apply_sleepy_yaw(m,result,1.)
        result['observation']['captured_s']=1.2;apply_sleepy_yaw(m,result,1.2)
        self.assertTrue(any(i==1 and a==42 for i,a,v in b.calls))
        self.assertFalse(any(i==5 for i,a,v in b.calls))
        self.assertEqual(b.reg[5][42],2901)
    def test_normal_output_is_white_and_stop_closes_it(self):
        m,b=self.motor();service_state_outputs(m)
        m.led_ring.normal.assert_called_once()
        m.operator_stopped=True;service_state_outputs(m)
        self.assertIsNone(m.led_ring)


    def test_happy_enters_from_each_state_without_body_reset_and_stop_blocks(self):
        for source in ('normal','interested','sleepy'):
            with self.subTest(source=source):
                m,b=self.motor()
                if source!='normal':handle_state_key(m,ord(source[0]));self.settle(m,b)
                centers={2:b.reg[2][42],3:b.reg[3][42]}
                m.controller.rhythm_base_reference=centers
                b.calls.clear();self.assertTrue(handle_state_key(m,ord('d')))
                self.assertEqual(m.behavior_trial,'happy');self.assertTrue(m.follow_enabled)
                self.assertEqual(m.controller.happy_body_reference,centers)
                self.assertFalse(any(i in (2,3) and a==42 for i,a,v in b.calls))
                m.controller.tick(m.controller.last_tick+.1)
                self.assertNotEqual(m.controller.state,'FAULT')
                handle_state_key(m,ord('s'));self.assertEqual(m.behavior_trial,'sleepy')
                m.operator_stopped=True;b.calls.clear();handle_state_key(m,ord('d'))
                self.assertEqual(b.calls,[])

    def test_happy_queued_during_lean_uses_new_body_center_not_stale_normal(self):
        from body_rhythm import BodyRhythmDriver
        m,b=self.motor();d=BodyRhythmDriver(normal_amplitude_deg=2.,happy_amplitude_deg=2.,time_scale=.5,phi=.1)
        d.step(m,0.);handle_state_key(m,ord('i'))
        handle_state_key(m,ord('d'));self.assertEqual(m.pending_behavior,ord('d'))
        self.settle(m,b);m._service_behavior_request()
        self.assertEqual(m.controller.happy_body_reference,{2:2735,3:2848})
        d.step(m,2.);m.controller.tick(m.controller.last_tick+.1)
        self.assertNotEqual(m.controller.state,'FAULT')

    def test_happy_gui_key_reaches_worker_and_can_exit_to_normal_or_interested(self):
        for target in ('n','i'):
            m,b=self.motor();m.keys=[];m.latest_result=None
            m.key(ord('d'));self.assertEqual(m.keys,[ord('d')])
            handle_state_key(m,m.keys.pop());handle_state_key(m,ord(target));self.settle(m,b)
            self.assertEqual(m.behavior_trial,'normal' if target=='n' else 'interested')

    def test_queued_happy_after_sleepy_history_respects_worker_completion_order(self):
        from body_rhythm import BodyRhythmDriver
        m,b=self.motor();d=BodyRhythmDriver(normal_amplitude_deg=2.,happy_amplitude_deg=2.,time_scale=.5,phi=.1)
        d.step(m,0.);handle_state_key(m,ord('s'));handle_state_key(m,ord('i'));handle_state_key(m,ord('d'))
        for _ in range(20):
            b.pos={i:b.reg[i][42] for i in NORMAL}
            m.controller.tick(m.controller.last_tick+.1)
            m._service_behavior_request();m._service_interested_gaze();m._finish_button_route()
            if m.behavior_trial=='happy':break
        self.assertEqual(m.behavior_trial,'happy')
        self.assertEqual(m.controller.happy_body_reference,{2:2735,3:2848})
        d.step(m,2.);m.controller.tick(m.controller.last_tick+.1)
        self.assertNotEqual(m.controller.state,'FAULT')

    def test_touch_required_blocks_gui_happy_but_accepts_real_edge(self):
        from unittest.mock import Mock
        m,b=self.motor();m.touch_required_for_happy=True;m.physical_touch=Mock();m.physical_touch.poll.return_value=True
        m.touch_sequence=0;m.last_touch_event=None
        b.calls.clear();handle_state_key(m,ord('d'))
        self.assertEqual(m.behavior_trial,'normal');self.assertEqual(b.calls,[])
        self.assertTrue(m._poll_physical_touch(1.))
        self.assertEqual(m.behavior_trial,'happy')
        m.behavior_trial='afraid';b.calls.clear();m._poll_physical_touch(2.)
        self.assertEqual(m.behavior_trial,'afraid');self.assertEqual(b.calls,[])
    def test_happy_yaw_composition_clips_at_existing_command_margin_and_stops(self):
        from body_rhythm import BodyRhythmDriver
        m,b=self.motor();m.happy_yaw_enabled=True
        handle_state_key(m,ord('d'));m.happy_yaw_base=m.controller.normal[1]
        d=BodyRhythmDriver(phi=.1,time_scale=.5,happy_amplitude_deg=4.)
        d.step(m,0.);b.calls.clear();d.step(m,2.)
        self.assertTrue(any(i==1 and a==42 for i,a,v in b.calls))
        m.happy_yaw_base=m.controller.yaw_window[1];d.step(m,2.1)
        self.assertLessEqual(b.reg[1][42],m.controller.yaw_window[1]-m.controller.command_margin_ticks)
        self.assertGreaterEqual(b.reg[1][42],m.controller.yaw_window[0]+m.controller.command_margin_ticks)
        b.calls.clear();m.operator_stopped=True;d.step(m,3.);self.assertEqual(b.calls,[])

    def test_touch_priority_suppresses_button_and_gui_cannot_reuse_touch_authorization(self):
        from unittest.mock import Mock
        m,b=self.motor();m.touch_required_for_happy=True;m.physical_touch=Mock();m.physical_touch.poll.return_value=True
        m.touch_sequence=0;m.physical_button=Mock();m.physical_button.poll.return_value=True;m.button_sequence=0
        m._poll_physical_touch(1.);m._poll_physical_button(1.,suppress=True)
        self.assertEqual(m.behavior_trial,'happy');self.assertEqual(m.last_button_event['status'],'ignored_touch_priority')
        handle_state_key(m,ord('n'));self.settle(m,b);handle_state_key(m,ord('d'))
        self.assertEqual(m.behavior_trial,'normal')

    def test_happy_visual_update_sets_base_without_competing_yaw_write(self):
        from visual_servo import VisualServo
        from body_rhythm import BodyRhythmDriver
        m,b=self.motor();m.happy_yaw_enabled=True
        handle_state_key(m,ord('d'));m.controller.set_direction(1)
        m.visual=VisualServo(*m.controller.yaw_window,100,100,.25,6,160,.5)
        m.controller.last_rows=b.snapshot();m._apply_pitch=Mock()
        result=dict(state='happy',observation=dict(status='TRACKING',captured_s=1.,source_id=1),intent=dict(mode='FOLLOW',error_xy=(.5,0.)))
        b.calls.clear();m._apply(result,1.)
        self.assertFalse(any(i==1 and a==42 for i,a,v in b.calls))
        self.assertIsNotNone(m.happy_yaw_base)
        d=BodyRhythmDriver(phi=.1,time_scale=.5,happy_amplitude_deg=4.)
        d.step(m,1.);d.step(m,2.)
        self.assertTrue(any(i==1 and a==42 for i,a,v in b.calls))

    def test_happy_yaw_has_room_for_both_directions_even_at_gaze_limit(self):
        from body_rhythm import BodyRhythmDriver
        m,b=self.motor();m.happy_yaw_enabled=True;handle_state_key(m,ord('d'))
        m.happy_yaw_base=m.controller.yaw_window[0]
        d=BodyRhythmDriver(phi=.1,time_scale=.5,happy_amplitude_deg=4.)
        d.step(m,0.);values=[]
        for n in range(1,201):
            d.step(m,n*.05)
            if n>40:values.append(b.reg[1][42])
        self.assertGreater(min(values),m.controller.yaw_window[0]+m.controller.command_margin_ticks)
        self.assertGreater(max(values)-min(values),35)
    def test_happy_lost_face_uses_same_bounded_pitch_reacquisition_as_interest(self):
        from visual_servo import VisualServo
        m,b=self.motor();handle_state_key(m,ord('d'));m.controller.set_direction(1)
        m.visual=VisualServo(*m.controller.yaw_window,100,100,.25,6,160,.5)
        m._apply_pitch=Mock();m.last_tracking_error_xy=(0.,.8);m.last_tracking_seen_s=.9
        result=dict(state='happy',observation=dict(status='LOST',captured_s=1.,source_id=1),intent=dict(mode='SEARCH',error_xy=None))
        m._apply(result,1.)
        self.assertTrue(m.pitch_reacquire);m._apply_pitch.assert_called_once()

    def test_happy_six_extreme_to_sleepy_keeps_transition_guard_until_body_returns(self):
        from body_rhythm import BodyRhythmDriver
        m,b=self.motor();handle_state_key(m,ord('d'))
        d=BodyRhythmDriver(phi=.1,time_scale=.5,happy_amplitude_deg=4.,happy_body_excursion_deg=6.,sleepy_amplitude_deg=2.)
        d.step(m,0.);d.step(m,2.)
        b.pos={**NORMAL,2:NORMAL[2]-68,3:NORMAL[3]+68};m.controller.last_rows=b.snapshot()
        handle_state_key(m,ord('s'));d.step(m,2.05)
        m.controller.tick(m.controller.last_tick+.1)
        self.assertNotEqual(m.controller.state,'FAULT')
        for n in range(4):
            b.pos={i:b.reg[i][42] for i in NORMAL};m.controller.last_rows=b.snapshot();d.step(m,2.1+n*.05)
        low,high=m.controller.behavior_joint_windows[2]
        self.assertGreater(low,NORMAL[2]-68)

class Speed600RestoreTests(unittest.TestCase):
    def test_happy_returns_to_new_base_speed_on_all_five_axes(self):
        from test_small_happy_trial import Tests as HappyTests
        from three_state_behavior import _small_happy_speed
        m,b,_=HappyTests().fixture();m.controller.motion_speed=600;m.happy_speed_raw=750
        _small_happy_speed(m,True)
        self.assertTrue(all(b.reg[i][46]==750 for i in range(1,6)))
        _small_happy_speed(m,False)
        self.assertTrue(all(b.reg[i][46]==600 for i in range(1,6)))

class HappyWakeHeadTests(unittest.TestCase):
    def test_sleepy_to_happy_targets_normal_head_and_does_not_cancel_on_missing_face(self):
        from test_three_state_behavior import Tests as Fixture
        from three_state_behavior import handle_state_key
        m,b=Fixture().motor();m.automatic_fsm_enabled=True;m.small_happy_trial=True
        handle_state_key(m,ord('s'));b.pos[5]=NORMAL[5]+205
        m.controller.last_rows=b.snapshot()
        handle_state_key(m,ord('d'))
        self.assertEqual(b.reg[5][42],NORMAL[5])
        self.assertEqual(m.happy_head_wake_goal,NORMAL[5])
        m.controller.last_rows=b.snapshot();b.calls.clear()
        m._apply_small_happy_head(dict(observation=dict(status='LOST',captured_s=20.),intent=dict(mode='SEARCH')),20.)
        self.assertEqual(b.reg[5][42],NORMAL[5])
        self.assertEqual(m.happy_head_wake_goal,NORMAL[5])
    def test_wake_completes_at_normal_without_a_face(self):
        from test_three_state_behavior import Tests as Fixture
        from three_state_behavior import handle_state_key
        m,b=Fixture().motor();m.automatic_fsm_enabled=True;m.small_happy_trial=True
        handle_state_key(m,ord('s'));b.pos[5]=NORMAL[5]+205
        handle_state_key(m,ord('d'))
        b.pos[5]=NORMAL[5];m.controller.last_rows=b.snapshot()
        b.hold_actual=lambda sid:b.write(sid,42,b.pos[sid].to_bytes(2,'little'))
        m._apply_small_happy_head(dict(observation=dict(status='LOST',captured_s=20.),intent=dict(mode='SEARCH')),20.)
        self.assertIsNone(m.happy_head_wake_goal)
        self.assertEqual(b.reg[5][42],NORMAL[5])
