import unittest
from types import SimpleNamespace
from unittest.mock import Mock
import test_taught_crouch as fixture
from distance_behavior import DistanceGate
from automatic_fsm import AutomaticFSM

class Tests(unittest.TestCase):
    def motor(self):
        m,b=fixture.Tests().motor();m.all_states_cpg_enabled=True;m.automatic_fsm_enabled=True
        m.distance_gate=DistanceGate();sample=dict(distance_cm=120.,received_s=20.,error=None,sequence=1)
        m.physical_distance=SimpleNamespace(latest=lambda:dict(sample))
        m.physical_touch=Mock();m.physical_button=Mock()
        m.physical_touch.poll.return_value=False;m.physical_button.poll.return_value=False
        m.touch_sequence=0;m.button_sequence=0
        m.automatic_fsm=AutomaticFSM();m.now=lambda:20.
        m.automatic_fsm.service(m,20.)
        return m,b,sample
    def at(self,m,s,now,**updates):
        m.now=lambda:now;s.update(received_s=now,**updates);m.automatic_fsm.service(m,now)
    def test_idle_sleep_and_button_wake_without_gui(self):
        m,b,s=self.motor();self.at(m,s,26.)
        self.assertEqual(m.automatic_fsm.fsm.state,'sleepy');self.assertEqual(m.behavior_trial,'sleepy')
        m.physical_button.poll.return_value=True;self.at(m,s,26.1)
        self.assertEqual(m.automatic_fsm.fsm.state,'interested')
        self.assertEqual(m.behavior_trial,'button_look')
    def test_near_beats_simultaneous_touch_and_clear_beats_touch(self):
        m,b,s=self.motor();m.physical_touch.poll.return_value=True
        self.at(m,s,20.1,distance_cm=10.)
        self.assertEqual(m.behavior_trial,'afraid');self.assertEqual(m.automatic_fsm.fsm.state,'afraid')
        self.at(m,s,20.2,distance_cm=120.)
        self.assertEqual(m.automatic_fsm.fsm.state,'normal');self.assertEqual(m.behavior_trial,'normal_transition')
    def test_approach_enters_interest_without_button_glance(self):
        m,b,s=self.motor();self.at(m,s,20.1,distance_cm=70.)
        self.assertEqual(m.automatic_fsm.fsm.state,'interested')
        self.assertEqual(m.controller.pose_route.phase,'lean')
        self.assertNotEqual(m.behavior_trial,'button_look')
    def test_stop_is_never_overridden_by_inputs(self):
        m,b,s=self.motor();m.operator_stopped=True;b.calls.clear()
        m.physical_touch.poll.return_value=True;self.at(m,s,30.,distance_cm=10.)
        self.assertEqual(b.calls,[])
    def test_manual_emotion_key_cannot_override_automatic_fsm(self):
        m,b,s=self.motor();b.calls.clear();m._key(ord('s'))
        self.assertEqual(b.calls,[]);self.assertEqual(m.automatic_fsm.fsm.state,'normal')
    def test_timeout_preempts_button_motion_at_two_seconds(self):
        m,b,s=self.motor();m.physical_button.poll.return_value=True;self.at(m,s,20.1)
        m.physical_button.poll.return_value=False;self.at(m,s,22.1)
        self.assertEqual(m.automatic_fsm.fsm.state,'normal');self.assertEqual(m.behavior_trial,'normal_transition')

    def test_automatic_happy_blends_from_interested_pose_without_normal_pause(self):
        from test_small_happy_trial import Tests as HappyTests
        from small_happy_trial import SmallHappyTrial
        from three_state_behavior import enter_happy
        m,b,unused=HappyTests().fixture();c=m.controller
        m.automatic_fsm_enabled=True;m.behavior_trial='interested'
        entry={2:c.normal[2]-102,3:c.normal[3]+102}
        for i,q in entry.items():b.pos[i]=q;b.reg[i][42]=q
        c.behavior_joint_windows={i:(q-34,q+34) for i,q in entry.items()}
        c.behavior_joint_allowances={2:0,3:0};b.windows.update(c.behavior_joint_windows)
        enter_happy(m);self.assertEqual(m.behavior_trial,'happy')
        d=SmallHappyTrial(time_scale=.75);b.calls.clear()
        for n in range(121):
            now=n*.05;m.latest_result['observation']['captured_s']=now
            d.step(m,now)
            if n==0:self.assertEqual({i:b.reg[i][42] for i in entry},entry)
            b.pos={i:b.reg[i][42] for i in c.normal};c.tick(c.last_tick+.05)
            self.assertNotEqual(c.state,'FAULT')
        self.assertTrue(all(abs(b.reg[i][42]-c.normal[i])<=34 for i in (2,3)))

    def test_automatic_panel_only_submits_start_and_stop(self):
        from behavior_panel import BehaviorPanel
        cv=SimpleNamespace(EVENT_LBUTTONUP=4,setMouseCallback=lambda *args:None)
        panel=BehaviorPanel(cv,'test',automatic=True);panel.width=500;panel.top=300
        panel.click(4,100,320,0,None);self.assertEqual(panel.take(None),ord('m'))
        panel.click(4,450,320,0,None);self.assertEqual(panel.take(None),ord('h'))
        self.assertIsNone(panel.cpg_amplitude)

    def test_complete_input_sequence_with_real_motion_handlers_and_decoders(self):
        from test_small_happy_trial import Tests as HappyTests
        from state_rhythms import StateRhythms
        from small_happy_trial import SmallHappyTrial
        from afraid_rhythm import AfraidRhythm
        m,b,unused=HappyTests().fixture();c=m.controller
        m.automatic_fsm_enabled=True;m.all_states_cpg_enabled=True;m.behavior_trial='normal';m.yaw_follow_enabled=True;m.state_leds_enabled=True
        m.afraid_pose_trial_enabled=True;m.afraid_taught_pose={1:2017,2:3165,3:3224,4:1999,5:2044};m.afraid_crouch_duration_s=6.
        m.distance_gate=DistanceGate();sample=dict(distance_cm=120.,received_s=31.,error=None)
        m.physical_distance=SimpleNamespace(latest=lambda:dict(sample))
        m.physical_touch=Mock();m.physical_button=Mock();m.automatic_fsm=AutomaticFSM()
        m.rhythm_driver=StateRhythms(SmallHappyTrial(time_scale=.75),AfraidRhythm());m.afraid_rhythm_driver=None
        seen=set()
        for n in range(601):
            now=31.+n*.05;m.now=lambda t=now:t
            sample.update(received_s=now,distance_cm=10. if 7.<=n*.05<9. else 120.)
            m.physical_button.poll.return_value=n in (20,360)
            m.physical_touch.poll.return_value=n in (30,370)
            m.latest_result=dict(state='normal',observation=dict(status='TRACKING',captured_s=now,source_id=n),intent=dict(mode='FOLLOW',error_xy=(0.,0.)))
            b.pos={i:b.reg[i][42] for i in c.normal};c.tick(now)
            self.assertNotEqual(c.state,'FAULT',c.last_error)
            m.automatic_fsm.service(m,now);m._service_behavior_request();m._finish_button_route();m._service_interested_roll();m._service_body_rhythm()
            seen.add(m.automatic_fsm.fsm.state)
        self.assertEqual(seen,{'normal','interested','happy','afraid','sleepy'})

    def test_idle_sleep_preserves_guard_if_normal_return_has_not_arrived(self):
        m,b,s=self.motor();c=m.controller
        self.at(m,s,20.1,distance_cm=70.)
        b.pos.update({2:c.normal[2]-100,3:c.normal[3]+100,4:c.normal[4]-130})
        self.at(m,s,22.1)
        self.assertEqual(m.behavior_trial,'normal_transition')
        self.at(m,s,26.1)
        lo,hi=c.feedback_window(2)
        self.assertTrue(lo<=b.pos[2]<=hi)
        c.tick(c.last_tick+.1);self.assertNotEqual(c.state,'FAULT',c.last_error)

    def test_button_preempts_a_coasting_return_without_shrinking_old_guard(self):
        from afraid_pose import enter_afraid
        from three_state_behavior import handle_state_key
        m,b,s=self.motor();c=m.controller
        enter_afraid(m);c.tick(30.)
        b.pos.update({2:3100,3:3150})
        handle_state_key(m,ord('n'))
        old=c.feedback_window(2)
        m.automatic_fsm.dispatch(m,'interested','button')
        self.assertLessEqual(c.feedback_window(2)[0],old[0])
        self.assertGreaterEqual(c.feedback_window(2)[1],old[1])
        b.pos[2]=3150;c.tick(c.last_tick+.1)
        self.assertNotEqual(c.state,'FAULT',c.last_error)

class EngagementAdapterTests(unittest.TestCase):
    motor=Tests.motor
    at=Tests.at
    def engaged_motor(self):
        m,b,s=self.motor();m.automatic_fsm=AutomaticFSM(motion_aware=True,active_timeout_s=5.)
        m.behavior_trial='normal';m.controller.pose_route=None;m.automatic_fsm.service(m,20.)
        return m,b,s
    def test_normal_return_cannot_be_interrupted_by_sleep(self):
        m,b,s=self.engaged_motor();m.behavior_trial='normal_transition'
        self.at(m,s,40.);self.assertEqual(m.automatic_fsm.fsm.state,'normal')
        m.behavior_trial='normal';self.at(m,s,41.)
        self.at(m,s,46.9);self.assertEqual(m.automatic_fsm.fsm.state,'normal')
        self.at(m,s,47.);self.assertEqual(m.automatic_fsm.fsm.state,'sleepy')
    def test_debounced_held_input_prevents_sleep_without_repolling(self):
        m,b,s=self.engaged_motor();m.physical_touch.edge=SimpleNamespace(stable=True)
        self.at(m,s,40.);self.assertEqual(m.automatic_fsm.fsm.state,'normal')
        m.physical_touch.edge.stable=False;self.at(m,s,41.)
        self.at(m,s,47.);self.assertEqual(m.automatic_fsm.fsm.state,'sleepy')
    def test_recovered_tof_does_not_invent_a_new_arrival(self):
        m,b,s=self.motor();self.at(m,s,20.1,distance_cm=43.)
        a=m.automatic_fsm;a.fault(21.);a.approach=False
        m.behavior_trial='normal';m.controller.pose_route=None
        self.at(m,s,21.1,distance_cm=43.)
        self.assertEqual(a.fsm.state,'normal')
    def test_single_no_target_does_not_rearm_approach(self):
        m,b,s=self.motor();self.at(m,s,20.1,distance_cm=43.)
        self.at(m,s,22.1);self.assertEqual(m.automatic_fsm.fsm.state,'normal')
        self.at(m,s,22.2,distance_cm=None,measurement_state='no_target',range_status_raw=4,error=None)
        self.at(m,s,22.3,distance_cm=43.,measurement_state='range')
        self.assertEqual(m.automatic_fsm.fsm.state,'normal')
    def test_fault_gap_is_not_continuous_absence(self):
        m,b,s=self.motor();self.at(m,s,20.1,distance_cm=43.)
        self.at(m,s,22.1)
        self.at(m,s,22.2,distance_cm=None,measurement_state='no_target',range_status_raw=4)
        m.automatic_fsm.fault(22.4)
        self.at(m,s,23.,distance_cm=None,measurement_state='no_target',range_status_raw=4)
        self.at(m,s,23.1,distance_cm=43.,measurement_state='range',range_status_raw=9)
        self.assertEqual(m.automatic_fsm.fsm.state,'normal')
    def test_happy_fade_does_not_consume_its_five_seconds(self):
        m,b,s=self.engaged_motor();a=m.automatic_fsm
        m.physical_touch.poll.return_value=True;self.at(m,s,20.1)
        m.physical_touch.poll.return_value=False
        m.rhythm_view_cache={'small_happy':'running','envelope':.5}
        self.at(m,s,30.);self.assertEqual(a.fsm.state,'happy')
        m.rhythm_view_cache={'small_happy':'running','envelope':1.}
        self.at(m,s,31.);self.at(m,s,35.99);self.assertEqual(a.fsm.state,'happy')
        self.at(m,s,36.);self.assertEqual(a.fsm.state,'normal')

class InitialApproachTests(unittest.TestCase):
    def test_initial_nearby_player_is_baseline_not_a_new_arrival(self):
        m,b,s=Tests().motor();m.automatic_fsm=AutomaticFSM()
        s['distance_cm']=50.;m.automatic_fsm.service(m,20.)
        self.assertEqual(m.automatic_fsm.fsm.state,'normal')
        m.now=lambda:20.1;s.update(distance_cm=100.,received_s=20.1);m.automatic_fsm.service(m,20.1)
        m.now=lambda:20.2;s.update(distance_cm=50.,received_s=20.2);m.automatic_fsm.service(m,20.2)
        self.assertEqual(m.automatic_fsm.fsm.state,'interested')
    def test_gaze_wait_cannot_latch_interested_forever(self):
        m,b,s=EngagementAdapterTests().engaged_motor()
        m.controller.interest_gaze_priority=True;m.controller.lean_command_limits=(100.,100.,.5);m.controller.control_now_s=20.1
        Tests.at(self,m,s,20.1,distance_cm=70.)
        self.assertTrue(m.controller.pose_route.waiting_for_player)
        Tests.at(self,m,s,21.);self.assertEqual(m.automatic_fsm.fsm.state,'interested')
        Tests.at(self,m,s,26.);self.assertEqual(m.automatic_fsm.fsm.state,'normal')
    def test_repeated_brief_centering_does_not_reset_total_gaze_wait_budget(self):
        m,b,s=EngagementAdapterTests().engaged_motor()
        m.controller.interest_gaze_priority=True;m.controller.lean_command_limits=(100.,100.,.5);m.controller.control_now_s=20.1
        Tests.at(self,m,s,20.1,distance_cm=70.)
        route=m.controller.pose_route
        route.waiting_for_player=False;Tests.at(self,m,s,21.)
        route.waiting_for_player=True;Tests.at(self,m,s,22.)
        route.waiting_for_player=False;Tests.at(self,m,s,23.)
        route.gaze_wait_elapsed_s=5.
        Tests.at(self,m,s,24.)
        self.assertEqual(m.automatic_fsm.fsm.state,'normal')
    def test_repeated_button_replays_glance_and_preserves_player_return(self):
        m,b,s=Tests().motor();Tests.at(self,m,s,20.1,distance_cm=70.)
        saved=dict(m.controller.pose_route.return_pose)
        m.physical_button.poll.return_value=True;Tests.at(self,m,s,20.2)
        self.assertEqual(m.controller.pose_route.phase,'look')
        self.assertEqual(m.controller.pose_route.return_pose,saved)
    def test_press_during_startup_does_not_run_after_ready(self):
        from physical_button import BufferedInput
        m,b,s=Tests().motor();m.automatic_fsm=AutomaticFSM();q=BufferedInput(.06);m.physical_button=q
        m.controller.state='NORMAL_STARTUP'
        for pressed,t in ((False,20.),(False,20.07),(True,20.1),(True,20.17)):q.sample(pressed,t)
        Tests.at(self,m,s,20.2)
        m.controller.state='READY';Tests.at(self,m,s,22.)
        self.assertEqual(m.automatic_fsm.fsm.state,'normal')

class FaceApproachTests(unittest.TestCase):
    motor=Tests.motor
    at=Tests.at
    def face_gate_motor(self):
        m,b,s=self.motor();m.automatic_fsm=AutomaticFSM(approach_requires_face=True)
        m.latest_result={};m.automatic_fsm.service(m,20.)
        return m,b,s
    def face_frame(self,t,status='TRACKING',mode='FOLLOW'):
        return dict(observation=dict(status=status,captured_s=t,source_id=t,box=(.3,.2,.3,.5)),
                    intent=dict(mode=mode,error_xy=(0.,0.)))
    def test_face_gated_approach_rejects_object_and_accepts_delayed_fresh_face(self):
        m,b,s=self.face_gate_motor();self.at(m,s,20.1,distance_cm=70.)
        self.assertEqual(m.automatic_fsm.fsm.state,'normal')
        m.latest_result=self.face_frame(20.2);self.at(m,s,20.2,distance_cm=70.)
        self.assertEqual(m.automatic_fsm.fsm.state,'interested')
        self.assertEqual(m.controller.pose_route.phase,'lean')
        self.assertNotEqual(m.behavior_trial,'button_look')
    def test_face_gate_rejects_stale_ambiguous_and_expired_arrival(self):
        m,b,s=self.face_gate_motor();self.at(m,s,20.1,distance_cm=70.)
        for t,frame in ((20.2,self.face_frame(19.)),(20.3,self.face_frame(20.3,'AMBIGUOUS','HOLD')),
                        (20.7,self.face_frame(20.7))):
            m.latest_result=frame;self.at(m,s,t,distance_cm=70.)
            self.assertEqual(m.automatic_fsm.fsm.state,'normal')
        self.at(m,s,20.8,distance_cm=110.)
        m.latest_result=self.face_frame(20.9);self.at(m,s,20.9,distance_cm=70.)
        self.assertEqual(m.automatic_fsm.fsm.state,'interested')
    def test_face_gate_does_not_change_button_or_near_without_face(self):
        m,b,s=self.face_gate_motor();m.physical_button.poll.return_value=True
        self.at(m,s,20.1,distance_cm=110.)
        self.assertEqual(m.behavior_trial,'button_look')
        m,b,s=self.face_gate_motor();self.at(m,s,20.1,distance_cm=10.)
        self.assertEqual(m.automatic_fsm.fsm.state,'afraid')
    def test_face_gate_startup_inside_zone_is_baseline_not_arrival(self):
        m,b,s=self.motor();m.automatic_fsm=AutomaticFSM(approach_requires_face=True)
        m.latest_result=self.face_frame(20.1);self.at(m,s,20.1,distance_cm=70.)
        m.latest_result=self.face_frame(20.2);self.at(m,s,20.2,distance_cm=70.)
        self.assertEqual(m.automatic_fsm.fsm.state,'normal')
    def test_sleepy_face_can_confirm_approach_and_face_flicker_does_not_retrigger(self):
        m,b,s=self.face_gate_motor();a=m.automatic_fsm
        a.fsm.state='sleepy';a.applied='sleepy';m.behavior_trial='sleepy'
        m.latest_result=self.face_frame(20.1,mode='FOLLOW_DROOP');self.at(m,s,20.1,distance_cm=70.)
        self.assertEqual(a.fsm.state,'interested')
        a.fsm.state='normal';a.applied='normal';m.behavior_trial='normal';m.controller.pose_route=None
        m.latest_result={};self.at(m,s,20.2,distance_cm=70.)
        m.latest_result=self.face_frame(20.3);self.at(m,s,20.3,distance_cm=70.)
        self.assertEqual(a.fsm.state,'normal')

    def test_face_gate_requires_selected_valid_box_and_current_distance(self):
        m,b,s=self.face_gate_motor();m.latest_result=self.face_frame(20.1)
        m.latest_result['observation']['box']=None;self.at(m,s,20.1,distance_cm=70.)
        self.assertEqual(m.automatic_fsm.fsm.state,'normal')
        m.latest_result=self.face_frame(20.2);self.at(m,s,20.2,distance_cm=90.)
        self.assertEqual(m.automatic_fsm.fsm.state,'normal')
        self.at(m,s,20.3,distance_cm=70.)
        self.assertEqual(m.automatic_fsm.fsm.state,'interested')
    def test_face_requirement_is_strictly_validated_before_uart(self):
        from automatic_fsm import validate_approach_config
        self.assertFalse(validate_approach_config({}))
        good=dict(approach_requires_face=True,automatic_fsm_enabled=True,physical_tof_enabled=True,gaze_enabled=True)
        self.assertTrue(validate_approach_config(good))
        for change in ({'gaze_enabled':False},{'approach_requires_face':1}):
            with self.assertRaises(ValueError):validate_approach_config({**good,**change})


class ScanApproachTests(unittest.TestCase):
    motor=FaceApproachTests.motor
    at=FaceApproachTests.at
    face_gate_motor=FaceApproachTests.face_gate_motor
    face_frame=FaceApproachTests.face_frame
    def scan_motor(self):
        m,b,s=self.face_gate_motor()
        m.automatic_fsm=AutomaticFSM(approach_requires_face=True,approach_scan_arrival=True,sleep_after_s=100.)
        m.automatic_fsm.service(m,20.)
        return m,b,s
    def found(self,m,s,t,serial=1,distance=40.):
        m.yaw_scan_found=dict(serial=serial,time_s=t)
        for offset in (0.,.08,.16):
            m.latest_result=self.face_frame(t+offset)
            self.at(m,s,t+offset,distance_cm=distance)
    def normal_again(self,m):
        a=m.automatic_fsm;a.fsm.state='normal';a.applied='normal'
        m.behavior_trial='normal';m.controller.pose_route=None
        a.recovering_approach=False
    def test_selected_threshold_is_fifty_not_eighty(self):
        m,b,s=self.scan_motor();m.latest_result=self.face_frame(20.1)
        self.at(m,s,20.1,distance_cm=70.);self.assertEqual(m.automatic_fsm.fsm.state,'normal')
        m.latest_result=self.face_frame(20.2);self.at(m,s,20.2,distance_cm=50.)
        self.assertEqual(m.automatic_fsm.fsm.state,'interested')
    def test_actual_scan_finds_stationary_face_and_requires_distinct_stable_frames(self):
        m,b,s=self.scan_motor();self.at(m,s,20.1,distance_cm=40.)
        m.yaw_scan_found=dict(serial=1,time_s=21.)
        m.latest_result=self.face_frame(21.)
        self.at(m,s,21.,distance_cm=40.);self.at(m,s,21.1,distance_cm=40.)
        self.assertEqual(m.automatic_fsm.fsm.state,'normal')
        m.latest_result=self.face_frame(21.15);self.at(m,s,21.15,distance_cm=40.)
        self.assertEqual(m.automatic_fsm.fsm.state,'normal')
        m.latest_result=self.face_frame(21.2);self.at(m,s,21.2,distance_cm=40.)
        self.assertEqual(m.automatic_fsm.fsm.state,'interested')
        self.assertEqual(m.controller.pose_route.phase,'lean')
    def test_face_reappearing_without_scan_never_triggers(self):
        m,b,s=self.scan_motor();self.at(m,s,20.1,distance_cm=40.)
        for t in (21.,21.1,21.2):
            m.latest_result=self.face_frame(t);self.at(m,s,t,distance_cm=40.)
        self.assertEqual(m.automatic_fsm.fsm.state,'normal')
    def test_cooldown_drops_scan_and_distance_events_but_button_still_works(self):
        m,b,s=self.scan_motor();self.at(m,s,20.1,distance_cm=40.)
        self.found(m,s,21.);self.normal_again(m)
        self.found(m,s,22.,serial=2);self.assertEqual(m.automatic_fsm.fsm.state,'normal')
        self.at(m,s,22.3,distance_cm=110.)
        m.latest_result=self.face_frame(22.4);self.at(m,s,22.4,distance_cm=40.)
        self.assertEqual(m.automatic_fsm.fsm.state,'normal')
        m.physical_button.poll.return_value=True;self.at(m,s,22.5,distance_cm=40.)
        self.assertEqual(m.behavior_trial,'button_look')
        m.physical_button.poll.return_value=False;self.normal_again(m)
        m.latest_result=self.face_frame(51.3);self.at(m,s,51.3,distance_cm=40.)
        self.assertEqual(m.automatic_fsm.fsm.state,'normal')  # No queued replay.
        self.found(m,s,51.4,serial=3);self.assertEqual(m.automatic_fsm.fsm.state,'interested')
    def test_scan_event_discarded_for_bad_frame_distance_or_owner(self):
        for case in ('far','near','ambiguous','stale','owner','expired','unreliable'):
            m,b,s=self.scan_motor();self.at(m,s,20.1,distance_cm=40.)
            m.yaw_scan_found=dict(serial=1,time_s=21.)
            m.latest_result=self.face_frame(21.)
            if case=='owner':m.behavior_trial='normal_transition'
            if case=='ambiguous':m.latest_result=self.face_frame(21.,'AMBIGUOUS','HOLD')
            if case=='stale':m.latest_result=self.face_frame(20.)
            distance=70. if case=='far' else 10. if case=='near' else 40.
            updates=dict(distance_cm=distance)
            if case=='unreliable':updates.update(distance_cm=None,measurement_state='unreliable')
            self.at(m,s,22. if case=='expired' else 21.,**updates)
            self.assertNotEqual(m.automatic_fsm.fsm.state,'interested',case)
            if case=='near':continue
            self.normal_again(m)
            for t in (22.1,22.2,22.3):
                m.latest_result=self.face_frame(t);self.at(m,s,t,distance_cm=40.,measurement_state='range')
            self.assertEqual(m.automatic_fsm.fsm.state,'normal',case)

    def test_real_scanner_completion_enters_interest_once(self):
        from yaw_face_scan import service
        from visual_servo import VisualServo
        m,b,s=self.scan_motor();m.visual=VisualServo(1680,2350,400.,100.,.25,6.,160.,.5)
        m.yaw_face_scan_enabled=True;m.follow_enabled=True
        m.yaw_follow_enabled=True;m.controller.pose_route=None
        self.at(m,s,20.1,distance_cm=40.)
        for t in (20.2,21.2,21.3):
            m.latest_result=self.face_frame(t,'WAITING','SEARCH')
            service(m,m.latest_result,t);self.at(m,s,t,distance_cm=40.)
        self.assertTrue(m.yaw_scan_status['active'])
        for t in (21.4,21.48,21.56,21.64,21.72,21.8,21.88,21.96,22.04,22.12,22.2):
            m.latest_result=self.face_frame(t-.4);service(m,m.latest_result,t)
            self.at(m,s,t,distance_cm=40.)
        self.assertEqual(m.automatic_fsm.fsm.state,'interested')
        self.assertEqual(m.automatic_fsm.fsm.last_winner['source_id'],'face_scan_1')
        self.normal_again(m)
        for t in (22.3,22.4,22.5):
            m.latest_result=self.face_frame(t);self.at(m,s,t,distance_cm=40.)
        self.assertEqual(m.automatic_fsm.fsm.state,'normal')
    def test_scan_config_dependencies_rejected_before_uart(self):
        from automatic_fsm import validate_approach_config
        good=dict(approach_requires_face=True,approach_scan_arrival=True,yaw_face_scan_enabled=True,
                  automatic_fsm_enabled=True,physical_tof_enabled=True,gaze_enabled=True)
        self.assertTrue(validate_approach_config(good))
        for change in ({'approach_scan_arrival':1},{'yaw_face_scan_enabled':False},{'approach_requires_face':False}):
            with self.assertRaises(ValueError):validate_approach_config({**good,**change})

    def test_scan_arrival_accepts_fresh_camera_latency(self):
        m,b,s=self.scan_motor();self.at(m,s,20.1,distance_cm=40.)
        m.yaw_scan_found=dict(serial=1,time_s=21.4,captured_s=21.)
        for t in (21.42,21.5,21.58):
            m.latest_result=self.face_frame(t-.4)
            self.at(m,s,t,distance_cm=40.)
        self.assertEqual(m.automatic_fsm.fsm.state,'interested')

    def test_scan_approach_waits_for_yaw_braking_handoff(self):
        m,b,s=self.scan_motor();self.at(m,s,20.1,distance_cm=40.)
        m.yaw_scan_handoff={'stopped_s':21.}
        self.found(m,s,21.)
        self.assertEqual(m.automatic_fsm.fsm.state,'normal')
        m.yaw_scan_handoff=None
        m.latest_result=self.face_frame(21.2);self.at(m,s,21.2,distance_cm=40.)
        self.assertEqual(m.automatic_fsm.fsm.state,'interested')

    def test_distance_approach_does_not_preempt_scan_or_braking(self):
        for field in ('yaw_face_scan','yaw_scan_handoff'):
            m,b,s=self.scan_motor()
            setattr(m,field,{'active':True})
            m.latest_result=self.face_frame(21.)
            self.at(m,s,21.,distance_cm=40.)
            self.assertEqual(m.automatic_fsm.fsm.state,'normal',field)
            setattr(m,field,None)
            m.latest_result=self.face_frame(21.1);self.at(m,s,21.1,distance_cm=40.)
            self.assertEqual(m.automatic_fsm.fsm.state,'interested',field)
