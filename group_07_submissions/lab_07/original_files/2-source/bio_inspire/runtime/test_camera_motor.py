import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'shared'/'runtime'))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_normal_gaze_motor import Bus,NORMAL,ORIGIN
from camera_motor import CameraMotor
from manual_tuning import DEFAULTS


class ClosingBus(Bus):
    closed=False
    def close(self):self.closed=True


class CameraMotorTests(unittest.TestCase):
    def test_new_pitch_paths_must_be_confirmed_before_interest(self):
        from types import SimpleNamespace
        m=CameraMotor.__new__(CameraMotor)
        m.controller=SimpleNamespace(state='READY',pose_route=None)
        m.pitch_clearance_confirmed=False;m.yaw_clearance_confirmed=True
        m._key(ord('i'))
        self.assertIn('U/J/K/J',m.tune_status)

    def test_new_yaw_range_confirmation_requires_both_operator_probes(self):
        from types import SimpleNamespace
        m=CameraMotor.__new__(CameraMotor)
        m.controller=SimpleNamespace(state='READY');m.tune_job=None
        m.yaw_clearance_confirmed=False;m.yaw_probe_requested={1}
        m._key(ord('c'));self.assertFalse(m.yaw_clearance_confirmed)
        m.yaw_probe_requested.add(-1);m._key(ord('c'))
        self.assertTrue(m.yaw_clearance_confirmed)

    def test_normal_rhythm_enables_gaze_once_but_cannot_restart_operator_stop(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        m=CameraMotor.__new__(CameraMotor);m.rhythm_driver=Mock();m.rhythm_normal_gaze_started=False;m.lock=threading.Lock()
        m.controller=SimpleNamespace(state='READY',face_ready_for_interest=True,configure_tracking=Mock())
        m.behavior_trial='normal';m.gaze_enabled=True;m.operator_stopped=False
        m.visual=SimpleNamespace(position=None);m._reset_pitch=Mock();m.now=lambda:1.
        m._service_body_rhythm()
        self.assertTrue(m.follow_enabled);m.controller.configure_tracking.assert_called_once_with(yaw=True)
        m._service_body_rhythm();m.controller.configure_tracking.assert_called_once()
        m.rhythm_normal_gaze_started=False;m.operator_stopped=True
        m.controller.configure_tracking.reset_mock();m._service_body_rhythm()
        m.controller.configure_tracking.assert_not_called()

    def test_interested_roll_returns_after_two_seconds_without_resetting_body_or_gaze(self):
        from types import SimpleNamespace
        b=ClosingBus();b.pos={**NORMAL,2:2735,3:2848,4:1860}
        for i in NORMAL:b.reg[i][42]=b.pos[i]
        m=CameraMotor.__new__(CameraMotor);m.bus=b;m.behavior_trial='interested'
        m.interested_roll_due=12.;m.now=lambda:11.9;m.follow_enabled=True
        m.controller=SimpleNamespace(state='FOLLOWING',normal=NORMAL,motion_speed=200,
            behavior_joint_windows={4:(1838,1882)},behavior_joint_allowances={4:0})
        b.windows={4:(1838,1882)}
        m._service_interested_roll();self.assertEqual(b.reg[4][42],1860)
        m.now=lambda:12.;m._service_interested_roll()
        self.assertEqual(b.reg[4][42],NORMAL[4]);self.assertEqual(b.reg[2][42],2735)
        self.assertEqual(b.reg[3][42],2848);self.assertTrue(m.follow_enabled)
        b.calls.clear();m._service_interested_roll();self.assertEqual(b.calls,[])
        m.interested_roll_due=0.;m.behavior_trial='sleepy'
        m._service_interested_roll();self.assertEqual(b.calls,[])
        self.assertIsNone(m.interested_roll_due)

    def test_lost_face_pitch_search_keeps_looking_up_in_reviewed_window(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from visual_servo import VisualServo
        m=CameraMotor.__new__(CameraMotor);m.pitch_enabled=True;m.pitch_direction=1
        m.pitch_reacquire=True;m.last_tracking_error_xy=(0.,-.5)
        m.controller=SimpleNamespace(last_rows=[dict(id=5,position_raw=2696)],goal_pitch=Mock())
        m.pitch_visual=VisualServo(2491,2764,100,100,.25,6,90,.5)
        m.stopping=threading.Event();m.urgent_stop=threading.Event()
        obs=dict(source_id=1,captured_s=1.)
        m._apply_pitch(dict(error_xy=None),obs,1.,False)
        m._apply_pitch(dict(error_xy=None),obs,1.2,False)
        goal=m.controller.goal_pitch.call_args.args[0]
        self.assertLess(goal,2696);self.assertGreaterEqual(goal,2491)

    def test_interested_face_is_followed_without_resetting_body_pose(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        m=CameraMotor.__new__(CameraMotor);m.gaze_enabled=True;m.follow_enabled=True;m.held=True
        m.controller=SimpleNamespace(state='READY',direction=1,yaw_window=(1900,2100),
            last_rows=[dict(id=1,position_raw=2000)],goal_yaw=Mock(return_value=True))
        m.visual=Mock();m.visual.position=2000;m.visual.step.return_value=2002
        m._apply_pitch=Mock();m.stopping=threading.Event();m.urgent_stop=threading.Event()
        result=dict(state='interested',intent=dict(mode='FOLLOW',error_xy=(.2,-.4)),
                    observation=dict(captured_s=10.,source_id=1,status='TRACKING'))
        m._apply(result,10.1)
        m.controller.goal_yaw.assert_called_once_with(2002)
        m._apply_pitch.assert_called_once_with(result['intent'],result['observation'],10.1,True)

    def test_sleepy_request_during_button_route_interrupts_without_normal_command(self):
        import test_three_state_behavior
        fixture=test_three_state_behavior.Tests();m,b=fixture.motor()
        m._key(ord('i'));route=m.controller.pose_route
        b.calls.clear()
        m._key(ord('s'))
        self.assertEqual(m.behavior_trial,'sleepy')
        self.assertEqual(route.phase,'cancelled')
        self.assertFalse(route.force_normal)
        self.assertEqual(b.reg[5][42],2901)

    def test_route_completion_enables_gaze_without_changing_body_targets(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        m=CameraMotor.__new__(CameraMotor);m.gaze_enabled=True;m.pitch_enabled=True
        m.controller=SimpleNamespace(pose_route=SimpleNamespace(phase='complete',force_normal=False),configure_tracking=Mock())
        m.visual=SimpleNamespace(position=None);m._reset_pitch=Mock()
        m.now=lambda:0.;m._finish_button_route()
        self.assertTrue(m.follow_enabled);self.assertFalse(m.held)
        m.controller.configure_tracking.assert_called_once_with(yaw=True)
        self.assertEqual(m.behavior_trial,'interested')

    def test_gestures_only_blocks_gaze_on_route_completion_and_g_key(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        m=CameraMotor.__new__(CameraMotor)
        m.gaze_enabled=False;m.pitch_enabled=True;m.follow_enabled=True;m.held=False
        m.controller=SimpleNamespace(pose_route=SimpleNamespace(phase='complete',force_normal=False),
                                     state='READY',direction=1,configure_tracking=Mock())
        m.visual=SimpleNamespace(position=12);m._reset_pitch=Mock()
        m.now=lambda:0.;m._finish_button_route()
        self.assertFalse(m.follow_enabled);self.assertTrue(m.held)
        m.controller.configure_tracking.assert_not_called()
        m.sleepy_trial_active=False;m.tune_job=None
        m._key(ord('g'))
        self.assertFalse(m.follow_enabled)
        m.controller.configure_tracking.assert_not_called()

    def test_gestures_only_rejects_face_output_even_if_follow_flag_is_set(self):
        from unittest.mock import Mock
        m=CameraMotor.__new__(CameraMotor);m.gaze_enabled=False;m.follow_enabled=True
        m.controller=Mock();m.controller.state='READY'
        m._apply({'intent':None,'observation':None},1.)
        m.controller.goal_yaw.assert_not_called();m.controller.goal_pitch.assert_not_called()

    def test_real_button_is_single_owner_request_and_cannot_override_operator_stop(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        m=CameraMotor.__new__(CameraMotor);m.physical_button=Mock();m.physical_button.poll.return_value=True
        m.operator_stopped=False;m.button_sequence=0;m.last_button_event=None
        m.controller=SimpleNamespace(state='READY',pose_route=None)
        m._key=Mock();m._poll_physical_button(5.)
        m._key.assert_called_once_with(ord('i'))
        self.assertEqual(m.last_button_event['source_id'],'button_000001')
        self.assertEqual(m.last_button_event['status'],'requested')
        m.operator_stopped=True;m._key.reset_mock();m._poll_physical_button(6.)
        m._key.assert_not_called();self.assertEqual(m.last_button_event['status'],'ignored_operator_stop')

    def test_status_reports_exact_normal_blockers_and_live_rows(self):
        from types import SimpleNamespace
        from camera_motor import motor_status
        rows=[dict(id=i,position_raw=NORMAL[i],speed_raw=0,moving_raw=0) for i in NORMAL]
        rows[1]['position_raw']+=26
        c=SimpleNamespace(state='NORMAL_STARTUP',normal=NORMAL,normal_tolerances={i:22 for i in NORMAL},last_rows=rows)
        report=motor_status(c,10.,ord('i'))
        self.assertEqual(report['waiting'],['ID2 error=26 limit=22'])
        c.normal_tolerances[2]=34
        self.assertEqual(motor_status(c,11.,None)['waiting'],[])

    def test_button_request_waits_for_normal_and_hold_clears_pending(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        m=CameraMotor.__new__(CameraMotor);m.joint_mode=False;m.pending_behavior=None
        m.controller=SimpleNamespace(state='NORMAL_STARTUP',last_rows=[],normal=NORMAL,normal_tolerances={i:22 for i in NORMAL},hold=Mock())
        m._key(ord('i'));self.assertEqual(m.pending_behavior,ord('i'))
        m._service_behavior_request();self.assertEqual(m.pending_behavior,ord('i'))
        m.controller.state='READY'
        m.controller.last_rows=[dict(id=i,position_raw=NORMAL[i],speed_raw=0,moving_raw=0) for i in NORMAL]
        with patch.object(m,'_key') as key:
            m._service_behavior_request();key.assert_called_once_with(ord('i'))
        m.visual=SimpleNamespace(position=None);m.pitch_visual=None
        m._hold('stop',True);self.assertIsNone(m.pending_behavior)

    def test_disconnect_for_retry_requires_closed_owner_but_not_old_hold_ack(self):
        from unittest.mock import Mock
        m=CameraMotor.__new__(CameraMotor)
        m.stopping=threading.Event();m.finished=threading.Event();m.finished.set()
        m.watchdog=Mock();m.watchdog.is_alive.return_value=False
        m.cleanup_confirmed=False
        m.disconnect_for_retry()
        self.assertTrue(m.stopping.is_set())
        m.watchdog.is_alive.return_value=True
        with self.assertRaises(RuntimeError):m.disconnect_for_retry()

    def test_operator_start_restores_cold_pid_and_uses_current_pose_not_cached_origin(self):
        from test_startup_preflight import PIDS
        b=ClosingBus();b.pos[1]+=50
        for i in NORMAL:b.reg[i][21]=int.from_bytes(bytes([32,32,0]),'little');b.reg[i][55]=1
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder, \
                patch('camera_motor.open_bus',return_value=b),patch.object(CameraMotor,'now',return_value=0.):
            p=self.profile(folder);config=json.loads(p.read_text());config['startup_pid_by_id']=PIDS;p.write_text(json.dumps(config))
            m=CameraMotor(p,operator_start=True)
            try:
                self.assertEqual(m.controller.origin,b.pos)
                self.assertEqual(m.controller.state,'NORMAL_STARTUP')
                for key,pid in PIDS.items():self.assertEqual(b.read(int(key),21,3),bytes([pid['p'],pid['d'],pid['i']]))
                for i in NORMAL:self.assertEqual(b.reg[i][42],NORMAL[i])
            finally:m.close()

    def test_manual_probe_records_confirmed_goal_and_selected_pid(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        m=CameraMotor.__new__(CameraMotor)
        m.controller=SimpleNamespace(state='READY',last_rows=[dict(id=2,position_raw=2859)],probe_joint=Mock(return_value=True))
        m.tuning_id=2;m.tune_job=None;m.tune_applied=dict(p=32,i=0,d=22,speed=1)
        m.motion_log=Mock();m.active_goal=dict(joint_id=2,raw=2871)
        m._refresh_goal=Mock();m.now=lambda:10.;m.lock=threading.Lock()
        m._joint_key(ord('u'))
        m.controller.probe_joint.assert_called_once_with(2,1)
        m._refresh_goal.assert_called_once()
        m.motion_log.begin.assert_called_once_with(2,2859,2871,m.tune_applied,10.)

    def test_stop_report_keeps_trace_before_cleanup_changes_hold(self):
        from types import SimpleNamespace
        from collections import deque
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            m=CameraMotor.__new__(CameraMotor)
            m.now=lambda:0.
            m.stopping=threading.Event();m.stopping.set();m.finished=threading.Event()
            m.trace=deque([dict(state='READY',goal_raw=2019,rows=[dict(id=1,position_raw=2029)])])
            m.stop_path=Path(folder)/'last_gaze_stop.json';m.cleanup_confirmed=False
            def hold(*a,**kw):m.trace.clear();return True
            m.controller=SimpleNamespace(hold=hold,last_error='')
            m.bus=SimpleNamespace(close=lambda:None)
            m._run()
            self.assertTrue(m.finished.is_set())
            data=json.loads(m.stop_path.read_text())
            self.assertEqual(data['trace'][0]['goal_raw'],2019)
            self.assertEqual(data['trace'][0]['rows'][0]['position_raw'],2029)

    def test_image_y_controls_only_pitch_and_stop_discards_both_trajectories(self):
        from normal_gaze_motor import NormalGaze
        from visual_servo import VisualServo
        b=Bus();c=NormalGaze(b,ORIGIN,NORMAL,pitch_probe=True,pitch_tracking=True)
        c.start(0);b.pos=dict(NORMAL)
        for t in (1,2,3):c.tick(t)
        c.set_direction(1)
        m=CameraMotor.__new__(CameraMotor);m.controller=c;m.follow_enabled=True;m.held=False
        m.pitch_enabled=True;m.pitch_direction=1;m.yaw_follow_enabled=False
        m.visual=VisualServo(1985,2053,50,100,.25,6,160,.5)
        m.pitch_visual=VisualServo(2662,2730,50,100,.25,6,90,.5)
        m.stopping=threading.Event();m.urgent_stop=threading.Event();b.calls.clear()
        for t in (4.,4.1,4.2,4.3):
            m._apply(dict(state='normal',observation=dict(captured_s=t,source_id=t,status='TRACKING'),
                          intent=dict(mode='FOLLOW',error_xy=(.8,.8))),t)
        self.assertGreater(b.reg[5][42],2696)
        self.assertEqual(b.reg[1][42],2019)
        self.assertFalse(any(i in (2,3,4) for i,a,v in b.calls))
        m._hold('test stop',True)
        self.assertIsNone(m.visual.position);self.assertIsNone(m.pitch_visual.position)
        self.assertEqual(b.reg[5][42],NORMAL[5])

    def test_id5_manual_tuning_does_not_write_base_pid_or_change_base_speed_model(self):
        from normal_gaze_motor import NormalGaze
        from types import SimpleNamespace
        m,_=self.tuning_motor();b=Bus()
        for r in b.reg.values():r[21]=int.from_bytes(bytes((32,32,0)),'little');r[55]=1
        c=NormalGaze(b,ORIGIN,NORMAL,pitch_probe=True,pitch_tracking=True,pitch_range_deg=6)
        c.start(0);b.pos=dict(NORMAL)
        for t in (1,2,3):c.tick(t)
        c.tracking_speed=100;m.controller=c;m.bus=b;m.tuning_id=5
        m.pitch_visual=SimpleNamespace(position=2696,max_speed=50);m.pitch_enabled=True
        m.visual.max_speed=123.;b.calls.clear()
        m.request_tuning(dict(p=24,i=0,d=40,speed=1));m._service_tuning(4.)
        for t in (4.1,4.2,4.3):
            c.last_rows=b.snapshot()
            for r in c.last_rows:r['sampled_monotonic_s']=t
            m._service_tuning(t)
        self.assertEqual(m.tune_applied,dict(p=24,i=0,d=40,speed=1))
        self.assertEqual([(i,a) for i,a,v in b.calls if a==21],[(5,21)])
        self.assertEqual(c.tracking_speed,100);self.assertEqual(m.visual.max_speed,123.)
        self.assertEqual(b.reg[5][41],1)

    def test_follow_is_blocked_until_operator_confirms_wider_pitch_paths(self):
        m,b=self.tuning_motor();m.follow_enabled=False;m.tuning_id=5
        m.pitch_clearance_confirmed=False;m.controller.direction=1
        m._key(ord('g'))
        self.assertFalse(m.follow_enabled);self.assertEqual(b.calls,[])

    def test_tuning_near_nominal_edge_is_rejected_without_motor_fault_or_pid_write(self):
        m,b=self.tuning_motor();m.controller.last_rows[0]['position_raw']=2134
        m.request_tuning(dict(p=16,i=0,d=32,speed=4));m._service_tuning(0.)
        m.controller.last_rows[0]['sampled_monotonic_s']=.1
        m._service_tuning(.1)
        self.assertIsNone(m.tune_job);self.assertFalse(m.follow_enabled)
        self.assertIn(m.controller.state,('READY','FOLLOWING'))
        self.assertEqual(b.calls,[]);self.assertIn('Not applied',m.tune_status)

    def test_manual_joint_selection_is_stationary_and_tuning_requests_keep_target_id(self):
        from normal_gaze_motor import NormalGaze
        m,_=self.tuning_motor();b=Bus()
        for r in b.reg.values():r[21]=int.from_bytes(bytes((32,32,0)),'little');r[55]=1
        c=NormalGaze(b,ORIGIN,NORMAL,manual_joints=True);c.start(0);b.pos=dict(NORMAL)
        for t in (1,2,3):c.tick(t)
        m.bus=b;m.controller=c;m.joint_mode=True;m.tuning_id=5
        m._select_joint(3);self.assertEqual(m.tuning_id,3);self.assertEqual(b.tuning_id,3)
        b.calls.clear();m.request_joint_tuning(5,dict(p=16,i=0,d=16,speed=1));m._service_tuning(4)
        self.assertEqual(b.calls,[]);self.assertIsNone(m.tune_job)
        c.last_rows[0]['speed_raw']=1;m._select_joint(2)
        self.assertEqual(m.tuning_id,3)

    def test_joint_switch_waits_for_probe_to_finish_even_before_motion_bit_changes(self):
        from normal_gaze_motor import NormalGaze
        m,_=self.tuning_motor();b=Bus()
        for r in b.reg.values():r[21]=int.from_bytes(bytes((32,32,0)),'little');r[55]=1
        c=NormalGaze(b,ORIGIN,NORMAL,manual_joints=True);c.start(0);b.pos=dict(NORMAL)
        for t in (1,2,3):c.tick(t)
        m.bus=b;m.controller=c;m.tuning_id=3;m.joint_mode=True;c.probe_joint(3,1)
        m._select_joint(2);self.assertEqual(m.tuning_id,3)
        b.pos[3]=NORMAL[3]+34
        for t in (4,5,6):c.tick(t)
        m._select_joint(2);self.assertEqual(m.tuning_id,2)

    def test_manual_profile_uses_live_selected_joint_pid_and_has_no_vision_commands(self):
        bus=ClosingBus();clock=[0.]
        for r in bus.reg.values():r[21]=int.from_bytes(bytes((32,32,0)),'little');r[55]=1
        snapshot=bus.snapshot
        def timestamped():
            rows=snapshot()
            for r in rows:r['sampled_monotonic_s']=time.monotonic()
            return rows
        bus.snapshot=timestamped
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder,                 patch('camera_motor.open_bus',return_value=bus),patch.object(CameraMotor,'now',side_effect=lambda:clock[0]):
            p=self.profile(folder);data=json.loads(p.read_text());data.update(manual_joint_tuning=True,manual_tuning=True,
                manual_tuning_id=5,speed_raw=1,acceleration_raw=3,yaw_range_deg=10,pitch_range_deg=6)
            p.write_text(json.dumps(data));m=CameraMotor(p)
            try:
                bus.pos=dict(NORMAL)
                end=time.monotonic()+1
                while not m.ready() and time.monotonic()<end:m.poll();time.sleep(.02)
                self.assertTrue(m.ready());m.key(ord('3'))
                end=time.monotonic()+1
                while m.tuning_id!=3 and time.monotonic()<end:m.poll();time.sleep(.02)
                self.assertEqual(m.tuning_view()['joint_id'],3)
                self.assertEqual(m.tuning_view()['applied'],dict(p=32,i=0,d=32,speed=1))
                bus.calls.clear();m.key(ord('u'));end=time.monotonic()+1
                while bus.reg[3][42]!=NORMAL[3]+34 and time.monotonic()<end:m.poll();time.sleep(.02)
                self.assertEqual(bus.reg[3][42],NORMAL[3]+34)
                self.assertFalse(any(i!=3 for i,a,v in bus.calls))
            finally:m.close()

    def test_restore_can_pause_incomplete_normal_and_apply_without_forcing_ready(self):
        from normal_gaze_motor import NormalGaze
        m,_=self.tuning_motor();b=Bus()
        for r in b.reg.values():r[21]=int.from_bytes(bytes((32,32,0)),'little');r[55]=1
        origin=dict(ORIGIN);origin[5]=NORMAL[5]+39;b.pos[5]=origin[5]
        c=NormalGaze(b,origin,NORMAL,manual_joints=True);c.start(0)
        b.pos=dict(NORMAL);b.pos[5]+=39;b.reg[5][21]=int.from_bytes(bytes((1,1,0)),'little')
        c.tick(1);self.assertEqual(c.state,'NORMAL_STARTUP')
        m.bus=b;m.controller=c;m.tuning_id=5;m.joint_mode=True;m.follow_enabled=False
        m.request_joint_tuning(5,dict(p=32,i=0,d=32,speed=1));m._service_tuning(2)
        self.assertEqual(c.state,'STOPPED')
        for t in (2.1,2.2,2.3):
            c.last_rows=b.snapshot()
            for r in c.last_rows:r['sampled_monotonic_s']=t
            m._service_tuning(t)
        self.assertEqual(m.tune_applied,dict(p=32,i=0,d=32,speed=1))
        self.assertEqual(c.state,'STOPPED');self.assertEqual(b.reg[5][42],b.pos[5])
        m.now=lambda:3.;m._joint_key(ord('m'))
        self.assertEqual(c.state,'NORMAL_STARTUP');self.assertEqual(b.reg[5][42],NORMAL[5])

    def test_manual_move_reports_acknowledged_goal_even_if_encoder_does_not_move(self):
        from normal_gaze_motor import NormalGaze
        m,_=self.tuning_motor();b=Bus();c=NormalGaze(b,ORIGIN,NORMAL,manual_joints=True)
        c.start(0);b.pos=dict(NORMAL)
        for t in (1,2,3):c.tick(t)
        m.bus=b;m.controller=c;m.tuning_id=5;m.joint_mode=True;m.now=lambda:4.
        m._joint_key(ord('u'))
        self.assertIn('SENT ID5',m.tune_status)
        m._refresh_goal()
        self.assertEqual(m.active_goal['raw'],NORMAL[5]+68)
        self.assertEqual(b.pos[5],NORMAL[5])

    def test_simple_gui_connects_current_pose_without_forcing_normal_and_accepts_id1(self):
        bus=ClosingBus()
        for r in bus.reg.values():r[21]=int.from_bytes(bytes((32,32,0)),'little');r[55]=1
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder,                 patch('camera_motor.open_bus',return_value=bus),patch.object(CameraMotor,'now',return_value=0.):
            p=self.profile(folder);d=json.loads(p.read_text());d.update(manual_joint_tuning=True,manual_tuning=True,
                manual_tuning_id=5,manual_connect_hold=True,speed_raw=1,acceleration_raw=3,yaw_range_deg=10)
            p.write_text(json.dumps(d));m=CameraMotor(p,initial_joint=1)
            try:
                self.assertEqual(m.controller.state,'STOPPED');self.assertEqual(m.tuning_id,1)
                self.assertTrue(all(bus.reg[i][42]==ORIGIN[i] for i in NORMAL))
            finally:m.close()

    def tuning_motor(self):
        from types import SimpleNamespace
        from test_manual_tuning import Bus as TuningBus
        b=TuningBus();b.acc=3
        m=CameraMotor.__new__(CameraMotor)
        m.bus=b;m.lock=threading.Lock();m.stopping=threading.Event();m.urgent_stop=threading.Event()
        m.tuning_enabled=True;m.tune_pending=None;m.tune_job=None;m.tune_status='READY';m.tune_applied={}
        m.tune_history=[];m.tune_path=None;m.follow_enabled=True;m.held=False
        m.visual=SimpleNamespace(position=2019,max_speed=1)
        m.controller=SimpleNamespace(state='FOLLOWING',last_rows=[dict(id=1,position_raw=2019,speed_raw=0,moving_raw=0,sampled_monotonic_s=0)],
            hold=lambda *a,**kw:True,tracking_speed=4,tracking_acceleration=3,last_error='',yaw_window=(1905,2133))
        return m,b

    def test_manual_request_stages_without_uart_and_applies_after_fresh_stationary_tick(self):
        m,b=self.tuning_motor()
        m.request_tuning(dict(p=12,i=0,d=40,speed=6))
        self.assertEqual(b.calls,[])
        m._service_tuning(0)
        self.assertEqual(b.calls,[]);self.assertFalse(m.follow_enabled)
        for t in (.1,.2,.3):
            m.controller.last_rows[0]['sampled_monotonic_s']=t;m._service_tuning(t)
        self.assertEqual(m.tune_applied,dict(p=12,i=0,d=40,speed=6))
        self.assertTrue(m.follow_enabled)

    def test_stationary_encoder_offset_is_not_mistaken_for_motion(self):
        m,b=self.tuning_motor();m.request_tuning(dict(p=10,i=1,d=34,speed=8));m._service_tuning(0)
        row=m.controller.last_rows[0];row['position_raw']=2029
        for t in (.1,.2,.3):row['sampled_monotonic_s']=t;m._service_tuning(t)
        self.assertEqual(m.tune_applied['speed'],8)

    def test_repeated_snapshot_cannot_count_as_three_stationary_samples(self):
        m,b=self.tuning_motor();m.request_tuning(DEFAULTS);m._service_tuning(0)
        row=m.controller.last_rows[0];row['sampled_monotonic_s']=.1
        for t in (.1,.2,.3):m._service_tuning(t)
        self.assertIsNotNone(m.tune_job)
        self.assertEqual(b.calls,[])

    def test_pending_tune_cancelled_by_stop_does_not_resume_or_write(self):
        m,b=self.tuning_motor();m.request_tuning(DEFAULTS);m._service_tuning(0)
        m.urgent_stop.set();m._service_tuning(.1)
        self.assertEqual(b.calls,[]);self.assertFalse(m.follow_enabled)

    def test_moving_feedback_blocks_gain_change(self):
        m,b=self.tuning_motor();m.request_tuning(DEFAULTS);m._service_tuning(0)
        m.controller.last_rows[0]['moving_raw']=1;m._service_tuning(.1)
        self.assertEqual(b.calls,[])

    def test_approved_control_period_and_no_catch_up_burst(self):
        from camera_motor import next_control_deadline
        self.assertAlmostEqual(next_control_deadline(1.,1.01),1.05)
        self.assertAlmostEqual(next_control_deadline(1.,1.08),1.08)

    def profile(self,folder):
        p=Path(folder)/'profile.json'
        p.write_text(json.dumps(dict(speed_raw=1,acceleration_raw=1,yaw_range_deg=3,
                                    origin_raw=ORIGIN,normal_raw=NORMAL,yaw_direction=1)),encoding='utf-8')
        return p

    def test_camera_stall_holds_even_without_main_loop_poll(self):
        bus=ClosingBus();clock=[0.]
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder, \
                patch('camera_motor.open_bus',return_value=bus), \
                patch.object(CameraMotor,'now',side_effect=lambda:clock[0]):
            motor=CameraMotor(self.profile(folder))
            try:
                clock[0]=1.
                end=time.monotonic()+1
                while motor.controller.state!='FAULT' and time.monotonic()<end:time.sleep(.01)
                self.assertEqual(motor.controller.state,'FAULT')
                self.assertTrue(all(bus.reg[i][42]==ORIGIN[i] for i in NORMAL))
                self.assertFalse(motor.follow_enabled)
            finally:motor.close()
            report=json.loads(motor.fault_path.read_text())
            self.assertIn('camera processing stalled',report['error'])
            self.assertTrue(report['trace'])
        self.assertTrue(bus.closed)

    def test_fault_stops_motor_but_does_not_hide_camera_target_after_normal(self):
        bus=ClosingBus();clock=[0.]
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder, \
                patch('camera_motor.open_bus',return_value=bus), \
                patch.object(CameraMotor,'now',side_effect=lambda:clock[0]):
            motor=CameraMotor(self.profile(folder))
            try:
                bus.pos=dict(NORMAL)
                end=time.monotonic()+1
                while not motor.ready() and time.monotonic()<end:motor.poll();time.sleep(.02)
                self.assertTrue(motor.vision_ready())
                clock[0]=1.
                end=time.monotonic()+1
                # Wait for the public UI snapshot, not the earlier internal state.
                while motor.ready() and time.monotonic()<end:time.sleep(.01)
                self.assertFalse(motor.ready())
                self.assertTrue(motor.vision_ready())
            finally:motor.close()

    def test_keyboard_interrupt_during_arming_holds_and_closes(self):
        bus=ClosingBus();write=bus.write
        def interrupt(i,a,data):
            write(i,a,data)
            if a==46:raise KeyboardInterrupt
        bus.write=interrupt
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder, \
                patch('camera_motor.open_bus',return_value=bus), \
                patch.object(CameraMotor,'now',return_value=0.), \
                self.assertRaises(KeyboardInterrupt):
            CameraMotor(self.profile(folder))
        self.assertTrue(bus.closed)
        self.assertEqual(bus.calls[-1],(1,42,ORIGIN[1]))

    def test_watchdog_start_failure_holds_and_closes_after_normal_goals(self):
        bus=ClosingBus()
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder, \
                patch('camera_motor.open_bus',return_value=bus), \
                patch.object(CameraMotor,'now',return_value=0.), \
                patch('camera_motor.threading.Thread.start',side_effect=RuntimeError('no thread')), \
                self.assertRaisesRegex(RuntimeError,'no thread'):
            CameraMotor(self.profile(folder))
        self.assertTrue(bus.closed)
        self.assertTrue(all(bus.reg[i][42]==ORIGIN[i] for i in NORMAL))

    def test_slow_uart_does_not_block_ui_mailbox(self):
        bus=ClosingBus();snapshot=bus.snapshot;count=[0]
        blocked=threading.Event();release=threading.Event();ui_done=threading.Event()
        def slow_snapshot():
            count[0]+=1
            if count[0]==3:blocked.set();release.wait(1)
            return snapshot()
        bus.snapshot=slow_snapshot
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder, \
                patch('camera_motor.open_bus',return_value=bus),patch.object(CameraMotor,'now',return_value=0.):
            motor=CameraMotor(self.profile(folder))
            try:
                self.assertTrue(blocked.wait(1))
                def ui():motor.poll();motor.apply(None);motor.key(ord('h'));ui_done.set()
                caller=threading.Thread(target=ui);caller.start()
                self.assertTrue(ui_done.wait(.2),'UI waited for a blocked serial transaction')
            finally:release.set();motor.close()
            caller.join(1)

    def test_face_expired_after_uart_poll_cannot_issue_yaw_target(self):
        bus=ClosingBus();clock=[0.]
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder, \
                patch('camera_motor.open_bus',return_value=bus), \
                patch.object(CameraMotor,'now',side_effect=lambda:clock[0]):
            motor=CameraMotor(self.profile(folder))
            try:
                bus.pos=dict(NORMAL)
                end=time.monotonic()+1
                while not motor.ready() and time.monotonic()<end:motor.poll();time.sleep(.02)
                self.assertTrue(motor.ready());bus.calls.clear()
                clock[0]=1.;motor.poll()
                motor.apply({'state':'normal','observation':{'captured_s':0.},
                             'intent':{'mode':'FOLLOW','error_xy':(1.,0.)}})
                motor.key(ord('g'));time.sleep(.2)
                self.assertTrue(all(a!=42 or v==NORMAL[i] for i,a,v in bus.calls))
            finally:motor.close()

    def test_stop_during_uart_read_prevents_cached_follow_write(self):
        bus=ClosingBus();snapshot=bus.snapshot;count=[0]
        blocked=threading.Event();release=threading.Event()
        def slow_snapshot():
            count[0]+=1
            if count[0]==3:blocked.set();release.wait(1)
            return snapshot()
        bus.snapshot=slow_snapshot
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder, \
                patch('camera_motor.open_bus',return_value=bus),patch.object(CameraMotor,'now',return_value=0.):
            motor=CameraMotor(self.profile(folder))
            try:
                self.assertTrue(blocked.wait(1));bus.pos=dict(NORMAL)
                motor.controller.state='READY';motor.follow_enabled=True
                motor.visual.reset(NORMAL[1]+10,-.1);bus.calls.clear()
                motor.apply({'state':'normal','observation':{'captured_s':0.},
                             'intent':{'mode':'FOLLOW','error_xy':(1.,0.)}})
                motor.key(ord('h'));release.set();time.sleep(.2)
                self.assertTrue(all(a!=42 or v==NORMAL[i] for i,a,v in bus.calls))
                self.assertFalse(motor.follow_enabled)
            finally:release.set();motor.close()


if __name__=='__main__':unittest.main()


class FaceExitMemoryTests(unittest.TestCase):
    def test_exit_direction_memory_is_short_lived_and_needs_live_camera(self):
        m=CameraMotor.__new__(CameraMotor)
        m._face_exit_memory(dict(status='TRACKING',captured_s=10.),dict(mode='FOLLOW',error_xy=(-.8,.7)),10.,True)
        obs=dict(status='LOST',captured_s=10.2);intent=dict(mode='SEARCH')
        self.assertTrue(m._face_exit_memory(obs,intent,10.2,False))
        self.assertEqual(m.last_tracking_error_xy,(-.8,.7))
        self.assertFalse(m._face_exit_memory(dict(status='LOST',captured_s=10.6),intent,10.6,False))
        self.assertFalse(m._face_exit_memory(dict(status='LOST',captured_s=11.1),intent,11.1,False))
        self.assertFalse(m._face_exit_memory(dict(status='STALE',captured_s=10.2),intent,10.2,False))
        self.assertFalse(m._face_exit_memory(dict(status='LOST',captured_s=9.),intent,10.2,False))

class PitchSearchBoundaryTests(unittest.TestCase):
    def test_missing_face_does_not_keep_pushing_outward_at_pitch_limit(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        m=CameraMotor.__new__(CameraMotor);m.pitch_enabled=True;m.pitch_reacquire=True;m.pitch_direction=1
        m.last_tracking_error_xy=(0.,-1.)
        m.controller=SimpleNamespace(last_rows=[dict(id=5,position_raw=2355)],goal_pitch=Mock())
        m.pitch_visual=SimpleNamespace(position=2355.,low=2355,high=2764,step=Mock())
        m.stopping=threading.Event();m.urgent_stop=threading.Event()
        m._apply_pitch(dict(mode='SEARCH'),dict(source_id=2,captured_s=10.),10.,False)
        m.controller.goal_pitch.assert_not_called();m.pitch_visual.step.assert_not_called()
        self.assertEqual(m.pitch_search_status,'limit_hold')

class PreviewRouteViewTests(unittest.TestCase):
    def test_display_receives_route_phase_needed_to_preserve_player(self):
        from types import SimpleNamespace
        m=CameraMotor.__new__(CameraMotor);m.lock=threading.Lock()
        m._view={'behavior':'button_look'};m.controller=SimpleNamespace(pose_route=SimpleNamespace(phase='look'))
        self.assertEqual(m.snapshot_view().get('route_phase'),'look')

class InterestedFeedbackLeadTests(unittest.TestCase):
    def motor(self,actual=2696):
        from types import SimpleNamespace
        from unittest.mock import Mock
        m=CameraMotor.__new__(CameraMotor);m.pitch_enabled=True;m.pitch_direction=1;m.pitch_reacquire=False
        m.interested_pitch_lead_ticks=34;m.behavior_trial='interested'
        m.pitch_visual=SimpleNamespace(position=2600.,velocity=-50.,low=2355,high=2764,step=Mock(return_value=2600.))
        m.controller=SimpleNamespace(last_rows=[dict(id=5,position_raw=actual)],goal_pitch=Mock())
        m.stopping=threading.Event();m.urgent_stop=threading.Event()
        return m
    def test_head_goal_does_not_wind_up_ahead_of_real_head(self):
        m=self.motor();m._apply_pitch(dict(error_xy=(0.,-.5)),dict(source_id=1,captured_s=10.),10.,True)
        m.controller.goal_pitch.assert_called_once_with(2662)
        self.assertEqual(m.pitch_visual.position,2662);self.assertEqual(m.pitch_visual.velocity,0.)
    def test_happy_controller_is_not_changed_by_interested_trial(self):
        m=self.motor();m.behavior_trial='happy'
        m._apply_pitch(dict(error_xy=(0.,-.5)),dict(source_id=1,captured_s=10.),10.,True)
        m.controller.goal_pitch.assert_called_once_with(2600)
    def test_sleepy_position_outside_awake_range_can_still_return(self):
        m=self.motor(actual=2901);m.pitch_visual.position=2764.;m.pitch_visual.step.return_value=2764.
        m._apply_pitch(dict(error_xy=(0.,-.5)),dict(source_id=1,captured_s=10.),10.,True)
        m.controller.goal_pitch.assert_called_once_with(2764)
    def test_feedback_limit_keeps_existing_awake_bounds(self):
        m=self.motor(actual=2360);m.pitch_visual.position=2355.;m.pitch_visual.step.return_value=2355.
        m._apply_pitch(dict(error_xy=(0.,-.5)),dict(source_id=1,captured_s=10.),10.,True)
        m.controller.goal_pitch.assert_called_once_with(2355)
