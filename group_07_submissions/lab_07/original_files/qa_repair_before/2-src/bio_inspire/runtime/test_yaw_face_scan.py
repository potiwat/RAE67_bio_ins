import unittest
from types import SimpleNamespace
from unittest.mock import patch
import test_native_posture as fixture

class Tests(unittest.TestCase):
    def motor(self):
        m,b=fixture.Tests().motor();c=m.controller
        m.yaw_face_scan_enabled=True;m.follow_enabled=True;m.yaw_follow_enabled=True
        m.behavior_trial='normal';m.operator_stopped=False;c.pose_route=None
        b.calls.clear();return m,b
    def frame(self,t,status='WAITING',mode='SEARCH'):
        return dict(observation=dict(status=status,captured_s=t,source_id=t),
                    intent=dict(mode=mode,error_xy=(0.,0.) if mode=='FOLLOW' else None))
    def test_no_history_waits_then_sweeps_both_directions_within_existing_limits(self):
        from yaw_face_scan import service
        m,b=self.motor();seen=[]
        self.assertFalse(service(m,self.frame(20.),20.))
        for t in (20.45,20.9,20.99):
            self.assertFalse(service(m,self.frame(t),t))
        self.assertTrue(service(m,self.frame(21.),21.))
        for n in range(1,301):
            now=21+n*.05;service(m,self.frame(now),now)
            q=b.reg[1][42];seen.append(q)
            self.assertTrue(m.visual.low<=q<=m.visual.high)
            b.pos[1]=q;m.controller.last_rows=b.snapshot()
        self.assertLess(min(seen),m.controller.normal[1]-20)
        self.assertGreater(max(seen),m.controller.normal[1]+20)
        self.assertGreater(m.yaw_scan_status['turns'],0)
        self.assertTrue(all(i==1 and a==42 for i,a,q in b.calls))
    def test_recent_exit_keeps_old_half_second_then_scan_and_face_rebases_gaze(self):
        from yaw_face_scan import service
        m,b=self.motor();m.last_tracking_seen_s=20.
        self.assertFalse(service(m,self.frame(20.3,'LOST'),20.3))
        self.assertFalse(service(m,self.frame(20.6,'LOST'),20.6))
        self.assertFalse(service(m,self.frame(20.99,'LOST'),20.99))
        self.assertFalse(service(m,self.frame(21.,'LOST'),21.))
        self.assertTrue(service(m,self.frame(21.3,'LOST'),21.3))
        b.pos[1]+=10;m.controller.last_rows=b.snapshot()
        self.assertTrue(service(m,self.frame(21.4,'TRACKING','FOLLOW'),21.4))
        self.assertFalse(m.yaw_scan_status['active'])
        self.assertEqual(m.visual.position,b.pos[1])
        self.assertEqual(m.visual.time,21.4)
        self.assertIsNone(getattr(m,'yaw_scan_found',None))
    def test_no_scan_for_other_owners_or_stop_or_bad_frames(self):
        from yaw_face_scan import service
        for kind in ('sleepy','happy','afraid','angry','stop','fault','stale','ambiguous','look','probe','paused'):
            m,b=self.motor();r=self.frame(20.);c=m.controller
            if kind in ('sleepy','happy','afraid','angry'):m.behavior_trial=kind
            elif kind=='stop':m.urgent_stop.set()
            elif kind=='fault':c.state='FAULT'
            elif kind=='stale':r['observation']['captured_s']=19.
            elif kind=='ambiguous':r['observation']['status']='AMBIGUOUS';r['intent']['mode']='HOLD'
            elif kind=='look':c.pose_route=SimpleNamespace(phase='look')
            elif kind=='probe':m.head_probe_active=True
            elif kind=='paused':m.follow_enabled=False
            b.calls.clear();self.assertFalse(service(m,r,20.),kind);self.assertEqual(b.calls,[],kind)
    def test_interested_waiting_lean_never_starts_scan_before_behavior_finishes(self):
        from yaw_face_scan import service
        m,b=self.motor();m.behavior_trial='button_look'
        m.controller.pose_route=SimpleNamespace(phase='lean',head_tracking_active=True)
        m.last_tracking_seen_s=19.
        for t in (20.,21.,22.):self.assertFalse(service(m,self.frame(t,'LOST'),t))
        self.assertEqual(b.calls,[])
        m.behavior_trial='normal';m.controller.pose_route=None
        self.assertFalse(service(m,self.frame(23.,'LOST'),23.))
        self.assertFalse(service(m,self.frame(23.99,'LOST'),23.99))
        self.assertTrue(service(m,self.frame(24.,'LOST'),24.))

    def test_camera_owner_runs_scan_and_holds_on_ambiguous_frame(self):
        m,b=self.motor();c=m.controller
        for n in range(31):
            t=20+n*.05;m._apply(self.frame(t),t)
            b.pos[1]=b.reg[1][42];c.last_rows=b.snapshot()
        self.assertTrue(m.yaw_scan_status['active'])
        self.assertNotEqual(b.reg[1][42],c.normal[1])
        b.calls.clear();t=21.55;m._apply(self.frame(t,'AMBIGUOUS','HOLD'),t)
        self.assertFalse(m.yaw_scan_status['active'])
        self.assertEqual(b.reg[1][42],b.pos[1])
        self.assertEqual(len([v for v in b.calls if v[0]==1 and v[1]==42]),1)
        self.assertNotEqual(c.state,'FAULT')

    def test_profile_opt_in_dependencies_are_checked(self):
        from yaw_face_scan import validate
        self.assertFalse(validate({}))
        good=dict(yaw_face_scan_enabled=True,fast_awake_trial=True,native_posture_compensation=True,gaze_enabled=True,yaw_range_deg=30)
        self.assertTrue(validate(good))
        for change in ({'yaw_range_deg':60},{'fast_awake_trial':False},{'yaw_face_scan_enabled':1}):
            with self.assertRaises(ValueError):validate({**good,**change})

    def test_ready_startup_without_any_face_enables_search_before_idle_sleep(self):
        from unittest.mock import Mock
        m,b=self.motor();c=m.controller
        m.follow_enabled=False;m.rhythm_normal_gaze_started=False
        m.yaw_clearance_confirmed=True;m.pitch_clearance_confirmed=True
        c.face_ready_for_interest=False
        m.rhythm_driver=SimpleNamespace(step=Mock(),rhythm=SimpleNamespace(status=lambda:{}))
        for n in range(41):
            t=20+n*.05;m.now=lambda t=t:t;m.latest_result=self.frame(t)
            m._service_body_rhythm();m._apply(m.latest_result,t)
            b.pos[1]=b.reg[1][42];c.last_rows=b.snapshot()
        self.assertTrue(m.follow_enabled)
        self.assertTrue(m.rhythm_normal_gaze_started)
        self.assertTrue(m.yaw_scan_status['active'])
        self.assertNotEqual(b.reg[1][42],c.normal[1])
        self.assertEqual(m.behavior_trial,'normal')

    def test_missing_frame_cannot_enable_search_on_stale_or_stopped_startup(self):
        from unittest.mock import Mock
        for case in ('stale','stop','disabled'):
            m,b=self.motor();c=m.controller;m.follow_enabled=False
            m.rhythm_normal_gaze_started=False;c.face_ready_for_interest=False
            m.yaw_clearance_confirmed=True;m.pitch_clearance_confirmed=True
            m.rhythm_driver=SimpleNamespace(step=Mock(),rhythm=SimpleNamespace(status=lambda:{}))
            m.now=lambda:20.;m.latest_result=self.frame(19. if case=='stale' else 20.)
            if case=='stop':m.operator_stopped=True
            if case=='disabled':m.yaw_face_scan_enabled=False
            b.calls.clear();m._service_body_rhythm()
            self.assertFalse(m.follow_enabled,case)
            self.assertEqual(b.calls,[],case)

    def test_selected_profile_real_startup_and_owner_flow_can_search_without_face(self):
        from contextlib import ExitStack
        from pathlib import Path
        from unittest.mock import Mock,patch
        from camera_motor import CameraMotor
        from test_normal_gaze_motor import Bus,NORMAL
        from awake_motion import prepare_awake
        b=Bus();b.pos=dict(NORMAL);b.close=Mock()
        profile=Path(__file__).resolve().parents[1]/'hardware'/'happy_dynamic_c1_trial.json'
        with ExitStack() as stack:
            clock=stack.enter_context(patch.object(CameraMotor,'now',return_value=20.))
            stack.enter_context(patch('camera_motor.open_bus',return_value=b))
            stack.enter_context(patch('physical_distance.PhysicalDistance'))
            stack.enter_context(patch('physical_button.PhysicalButton'))
            stack.enter_context(patch('physical_touch.PhysicalTouch'))
            stack.enter_context(patch('startup_preflight.prepare_operator_start',return_value=dict(NORMAL)))
            stack.enter_context(patch('camera_motor.read_values',return_value=dict(p=8,i=0,d=16,speed=600)))
            stack.enter_context(patch('camera_motor.threading.Thread'))
            m=CameraMotor(profile,operator_start=True);c=m.controller
            self.assertFalse(m.follow_enabled);self.assertEqual(c.state,'NORMAL_STARTUP')
            self.assertTrue(m.yaw_clearance_confirmed);self.assertTrue(m.pitch_clearance_confirmed)
            # Real motion/CPG paths; isolate sensor-driven hormone input only.
            m.rhythm_driver.normal_ahm=None
            for n in range(1,45):
                t=20+n*.05;clock.return_value=t
                c.control_now_s=t;c.face_ready_for_interest=False;c.tick(t)
                m.latest_result=self.frame(t)
                prepare_awake(m);m._service_body_rhythm();m._apply(m.latest_result,t)
                b.pos[1]=b.reg[1][42]
            self.assertTrue(m.follow_enabled)
            self.assertTrue(m.yaw_scan_status['active'])
            self.assertNotEqual(b.reg[1][42],NORMAL[1])
            self.assertNotEqual(c.state,'FAULT',c.last_error)

    def test_green_handoff_preserves_fresh_hold_encoder_and_does_not_reuse_scan_frame(self):
        from yaw_face_scan import service
        m,b=self.motor();c=m.controller
        service(m,self.frame(20.),20.);service(m,self.frame(21.),21.)
        b.pos[1]+=25  # Feedback cache is older than the encoder read by hold_actual.
        expected=b.pos[1]
        self.assertTrue(service(m,self.frame(21.1,'TRACKING','FOLLOW'),21.1))
        self.assertEqual(c.last_goal,expected)
        self.assertEqual(m.visual.position,expected)
        self.assertEqual(b.reg[1][42],expected)
        self.assertTrue(service(m,self.frame(21.1,'TRACKING','FOLLOW'),21.2))
        self.assertTrue(service(m,self.frame(21.21,'TRACKING','FOLLOW'),21.21))
        c.last_rows=b.snapshot()
        self.assertFalse(service(m,self.frame(21.31,'TRACKING','FOLLOW'),21.31))
        self.assertEqual(m.visual.position,expected)
