import unittest
from types import SimpleNamespace
from unittest.mock import Mock
import test_angry as fixture

class Tests(unittest.TestCase):
    def test_selected_profile_completes_entire_constructor_with_only_devices_mocked(self):
        from pathlib import Path
        from unittest.mock import patch,Mock
        from contextlib import ExitStack
        from camera_motor import CameraMotor
        from normal_gaze_motor import NormalGaze
        from test_normal_gaze_motor import Bus,NORMAL
        b=Bus();b.close=Mock()
        profile=Path(__file__).resolve().parents[1]/'hardware'/'happy_dynamic_c1_trial.json'
        with ExitStack() as stack:
            stack.enter_context(patch.object(CameraMotor,'now',return_value=20.))
            stack.enter_context(patch('camera_motor.open_bus',return_value=b))
            stack.enter_context(patch('physical_distance.PhysicalDistance'))
            stack.enter_context(patch('physical_button.PhysicalButton'))
            stack.enter_context(patch('physical_touch.PhysicalTouch'))
            stack.enter_context(patch('startup_preflight.prepare_operator_start',return_value=dict(NORMAL)))
            stack.enter_context(patch('camera_motor.read_values',return_value=dict(p=8,i=0,d=16,speed=600)))
            stack.enter_context(patch('camera_motor.threading.Thread'))
            start=stack.enter_context(patch.object(NormalGaze,'start'))
            m=CameraMotor(profile,operator_start=True)
            self.assertTrue(m.fast_awake_trial);self.assertEqual(m.controller.interest_native_body_speed_raw,600)
            self.assertTrue(m.happy_wide_caps_trial);self.assertTrue(m.rhythm_driver.happy.wide_caps_trial)
            self.assertTrue(m.angry_enabled);self.assertIsNotNone(m.automatic_fsm)
            start.assert_called_once();m.watchdog.start.assert_called_once()
        self.assertEqual(b.calls,[])
    def test_missing_angry_dependencies_still_block_before_uart(self):
        import json,tempfile
        from pathlib import Path
        from unittest.mock import patch
        from camera_motor import CameraMotor
        profile=Path(__file__).resolve().parents[1]/'hardware'/'happy_dynamic_c1_trial.json'
        config=json.loads(profile.read_text())
        with tempfile.TemporaryDirectory() as folder,patch('camera_motor.open_bus') as bus:
            p=Path(folder)/'p.json';p.write_text(json.dumps({**config,'physical_tof_enabled':False}))
            with self.assertRaisesRegex(ValueError,'Angry requires automatic FSM'):CameraMotor(p)
            bus.assert_not_called()
    def test_actual_selected_profile_reaches_sensor_gate_before_any_motor_command(self):
        from pathlib import Path
        from unittest.mock import patch,Mock
        from camera_motor import CameraMotor
        from test_normal_gaze_motor import Bus
        class SensorGate(Exception):pass
        b=Bus();b.close=Mock()
        profile=Path(__file__).resolve().parents[1]/'hardware'/'happy_dynamic_c1_trial.json'
        with patch.object(CameraMotor,'now',return_value=20.),patch('camera_motor.open_bus',return_value=b),patch('physical_distance.PhysicalDistance',side_effect=SensorGate('pre-motion sensor gate')):
            with self.assertRaises(SensorGate):CameraMotor(profile,operator_start=True)
        self.assertEqual(b.calls,[]);b.close.assert_called_once()
    def motor(self):
        m,b=fixture.MotionTests().motor();m.fast_awake_trial=True;m.controller.fast_awake_trial=True
        m.controller.motion_speed=600;m.behavior_trial='normal';m.operator_stopped=False
        m.visual=SimpleNamespace(max_speed=400.,max_acceleration=300.)
        m.pitch_visual=SimpleNamespace(max_speed=400.,max_acceleration=100.)
        raw_write=b.write
        def write(i,a,v):
            restore=getattr(b,'acceleration_restore',None)
            if a==41 and restore is not None and restore.defer(i,int.from_bytes(v,'little')):return
            raw_write(i,a,v)
        b.write=write
        return m,b
    def test_awake_exact_acceleration_and_visual_caps(self):
        from awake_motion import prepare_awake
        m,b=self.motor();prepare_awake(m)
        self.assertEqual([b.reg[i][41] for i in range(1,6)],[3,8,8,12,6])
        self.assertEqual(m.visual.max_speed,800.);self.assertAlmostEqual(m.pitch_visual.max_acceleration,6*8.7*4096/360)
        self.assertEqual(m.controller.bus.acceleration_restore.pinned,set(range(1,6)))
        self.assertFalse(getattr(b,'awake_dynamic_acceleration_trial',False))
    def test_sleep_releases_pins_restores_original_caps_and_gates_fold(self):
        from awake_motion import prepare_awake,prepare_sleep,sleep_ready
        m,b=self.motor();prepare_awake(m);prepare_sleep(m)
        self.assertEqual(m.visual.max_speed,400.);self.assertEqual(m.pitch_visual.max_acceleration,100.)
        self.assertFalse(sleep_ready(m))
        rows=[{**r,'goal_raw':b.reg[r['id']][42]} for r in b.snapshot()]
        for _ in range(3):b.acceleration_restore.service(rows,b.write)
        self.assertTrue(sleep_ready(m));self.assertEqual([b.reg[i][41] for i in (2,3,4,5)],[1]*4)
    def test_stop_fault_minimum_hold_and_sleep_service_never_send_awake_writes(self):
        from awake_motion import prepare_awake
        for mode in ('stop','fault','minimum','sleep'):
            m,b=self.motor();b.calls.clear()
            if mode=='stop':m.operator_stopped=True
            if mode=='fault':m.controller.state='FAULT'
            if mode=='minimum':
                m.behavior_trial='angry';m.controller.pose_route=SimpleNamespace(safety_hold=True,phase='complete')
            if mode=='sleep':m.behavior_trial='sleepy'
            prepare_awake(m);self.assertEqual(b.calls,[])
    def test_angry_forward_keeps_slow_body_but_fast_head(self):
        from awake_motion import prepare_awake
        m,b=self.motor();prepare_awake(m,'angry_approach')
        self.assertEqual([b.reg[i][41] for i in range(1,6)],[3,1,1,12,6])
    def test_cancelled_angry_route_cannot_apply_slow_arm_policy_during_happy(self):
        from awake_motion import prepare_awake
        m,b=self.motor();m.behavior_trial='happy'
        m.controller.pose_route=SimpleNamespace(phase='cancelled',completion_behavior='angry',range_phase='complete',safety_hold=True)
        prepare_awake(m)
        self.assertEqual([b.reg[i][41] for i in (2,3)],[8,8])
        self.assertEqual(m.visual.max_speed,800.)
    def test_rejected_interested_request_during_angry_does_not_change_acceleration(self):
        from awake_motion import prepare_awake
        from three_state_behavior import handle_state_key
        m,b=self.motor();m.behavior_trial='angry_transition'
        m.controller.pose_route=SimpleNamespace(phase='lean',completion_behavior='angry',range_phase='advance')
        prepare_awake(m);b.calls.clear();handle_state_key(m,ord('i'))
        self.assertEqual(b.calls,[]);self.assertEqual(b.reg[2][41],1)
    def test_lower_pinned_acceleration_waits_for_three_new_stationary_samples(self):
        from awake_motion import prepare_awake
        m,b=self.motor();prepare_awake(m);b.pos[2]-=60
        prepare_awake(m,'angry_approach')
        self.assertEqual(b.reg[2][41],8)
        def rows():return [{**r,'goal_raw':b.reg[r['id']][42]} for r in b.snapshot()]
        for _ in range(5):b.acceleration_restore.service(rows(),b.write);prepare_awake(m,'angry_approach')
        self.assertEqual(b.reg[2][41],8)
        b.pos[2]=b.reg[2][42]
        for _ in range(2):b.acceleration_restore.service(rows(),b.write);prepare_awake(m,'angry_approach')
        self.assertEqual(b.reg[2][41],8)
        b.acceleration_restore.service(rows(),b.write);prepare_awake(m,'angry_approach')
        self.assertEqual(b.reg[2][41],1)
    def test_sleep_handler_does_not_start_droop_while_restoring_acceleration(self):
        from awake_motion import prepare_awake
        from three_state_behavior import handle_state_key
        from unittest.mock import patch
        m,b=self.motor();prepare_awake(m);m.sleepy_entry_prepared=False
        with patch('bio_inspire.runtime.sleepy_trial.set_sleepy_trial') as droop:
            handle_state_key(m,ord('s'))
            self.assertEqual(m.pending_behavior,ord('s'));droop.assert_not_called()
    def test_awake_failure_clears_permission_and_does_not_send_positions(self):
        from awake_motion import prepare_awake
        m,b=self.motor();old=b.write
        def write(i,a,v):
            if i==3 and a==41:raise IOError('partial UART')
            old(i,a,v)
        b.write=write
        with self.assertRaises(IOError):prepare_awake(m)
        self.assertFalse(getattr(b,'awake_dynamic_acceleration_trial',False))
        self.assertFalse(any(a==42 for i,a,v in b.calls[-2:]))
    def test_afraid_three_seconds_is_bounded_and_uses_awake_acceleration(self):
        from afraid_pose import enter_afraid
        m,b=self.motor();m.afraid_crouch_duration_s=3.;m.sleepy_entry_prepared=True
        entry={i:b.reg[i][42] for i in (2,3,4)}
        enter_afraid(m);c=m.controller
        self.assertFalse(m.sleepy_entry_prepared)
        self.assertEqual([b.reg[i][41] for i in range(1,6)],[3,8,8,12,6])
        c.tick(21.5)
        for i in (2,3,4):self.assertAlmostEqual(b.reg[i][42],(entry[i]+c.pose_route.target[i])/2,delta=1)
        c.tick(23.)
        for i in (2,3,4):self.assertEqual(b.reg[i][42],c.pose_route.target[i])
    def test_visual_reacquisition_can_accelerate_faster_but_keeps_original_bounds(self):
        from awake_motion import prepare_awake
        from visual_servo import VisualServo
        m,b=self.motor()
        m.visual=VisualServo(1700.,2350.,400.,300.,.25,6.,160.,.5)
        m.pitch_visual=VisualServo(2355.,2764.,400.,100.,.25,6.,90.,.5)
        prepare_awake(m);v=m.pitch_visual;v.reset(2696.,20.)
        old=VisualServo(2355.,2764.,400.,100.,.25,6.,90.,.5);old.reset(2696.,20.)
        for n in range(1,11):
            now=20+n*.05;goal=v.step(-80.,now,n);slow=old.step(-80.,now,n)
            self.assertTrue(2355<=goal<=2764)
        self.assertLess(goal,slow)

    def test_wide_happy_pins_and_defers_reduction_until_stationary(self):
        from awake_motion import prepare_awake
        m,b=self.motor();m.happy_wide_caps_trial=True;m.behavior_trial='happy'
        prepare_awake(m)
        self.assertEqual([b.reg[i][41] for i in range(1,6)],[8,16,16,24,6])
        prepare_awake(m)
        self.assertEqual([b.reg[i][41] for i in range(1,6)],[8,16,16,24,6])
        m.behavior_trial='normal_transition';prepare_awake(m)
        g=b.acceleration_restore
        self.assertEqual([b.reg[i][41] for i in range(1,6)],[8,16,16,24,6])
        self.assertEqual(g.pending,{1:3,2:8,3:8,4:12})
        rows=[{**r,'goal_raw':b.reg[r['id']][42],'speed_raw':0,'moving_raw':0} for r in b.snapshot()]
        for _ in range(3):g.service(rows,b.write)
        prepare_awake(m)
        self.assertEqual([b.reg[i][41] for i in range(1,6)],[3,8,8,12,6])
        self.assertEqual(g.pinned,set(range(1,6)))
