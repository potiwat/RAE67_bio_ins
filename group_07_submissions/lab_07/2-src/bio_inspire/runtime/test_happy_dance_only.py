import unittest
import test_happy_taught_center as fixture
from small_happy_trial import SmallHappyTrial

class Tests(unittest.TestCase):
    def test_dance_still_obeys_stop_and_does_not_ignore_stalled_camera(self):
        m,b=fixture.Tests().motor();m.happy_dance_only=True;m.last_frame=0.
        d=SmallHappyTrial(expanded=True,taught_center=True,fast_trial=True,fast_period_s=5.,dynamic_trial=True)
        m.latest_result['observation'].update(status='STALE',captured_s=0.)
        d.step(m,1.);self.assertTrue(d.rhythm.status()['output_held'])
        m.last_frame=1.;m.operator_stopped=True
        d.step(m,1.);self.assertEqual(d.rhythm.status()['small_happy'],'inactive')

    def test_dance_only_uses_camera_heartbeat_not_detector_result_freshness(self):
        m,b=fixture.Tests().motor();m.happy_dance_only=True
        d=SmallHappyTrial(expanded=True,taught_center=True,fast_trial=True,fast_period_s=5.,dynamic_trial=True)
        for n in range(121):
            now=n*.05;m.last_frame=now
            m.latest_result['observation'].update(status='STALE',captured_s=0.)
            d.step(m,now)
            b.pos={i:b.reg[i][42] for i in b.pos};m.controller.last_rows=b.snapshot()
        self.assertEqual(d.rhythm.status()['small_happy'],'running')
        self.assertFalse(d.rhythm.status()['output_held'])

    def test_yaw_is_symmetric_and_independent_of_opposite_faces(self):
        histories=[]
        for face in (-1.,1.):
            m,b=fixture.Tests().motor();m.happy_dance_only=True
            d=SmallHappyTrial(expanded=True,taught_center=True,fast_trial=True,fast_period_s=5.,dynamic_trial=True)
            seen=[]
            for n in range(801):
                now=n*.05;m.latest_result['observation']['captured_s']=now
                m.latest_result['intent']['error_xy']=(face,face);d.step(m,now)
                if now>10.:seen.append(d.rhythm.status()['command_targets_raw'][1])
                b.pos={i:b.reg[i][42] for i in b.pos};m.controller.last_rows=b.snapshot()
            self.assertLessEqual(abs((min(seen)+max(seen))/2-m.controller.normal[1]),1.)
            self.assertGreater(max(seen)-min(seen),125);histories.append(seen)
        self.assertEqual(histories[0],histories[1])
    def test_native_head_receives_no_visual_error_but_keeps_posture_compensation(self):
        from interested_head import apply_gaze
        from unittest.mock import Mock
        m,b=fixture.Tests().motor();m.happy_dance_only=True;m.native_posture_compensation=True
        m._apply_pitch=Mock();m._face_exit_memory=Mock(return_value=True)
        r=dict(observation=dict(status='TRACKING',captured_s=20.,source_id=1),intent=dict(mode='FOLLOW',error_xy=(1.,1.)))
        apply_gaze(m,r,20.)
        m._apply_pitch.assert_called_once()
        args=m._apply_pitch.call_args.args
        self.assertFalse(args[3]);self.assertIsNone(args[0]['error_xy']);m._face_exit_memory.assert_not_called()

    def test_head_reference_is_repeatable_from_normal_not_previous_pose(self):
        from camera_motor import CameraMotor
        from visual_servo import VisualServo
        m,b=fixture.Tests().motor();c=m.controller
        m.happy_dance_only=True;m.native_posture_compensation=True;m.happy_head_wake_goal=None
        m.pitch_direction=1;m.pitch_reacquire=False;m.pitch_enabled=True
        m.pitch_visual=VisualServo(2070,2764,800.,600.,.25,6.,90.,.5)
        m.interested_head_model=None;m.interested_head_route=None
        m.posture_body_plan=dict(mode='happy',time_s=20.05,goals={2:2654,3:3095})
        for i,q in {2:2700,3:3000,5:2250}.items():b.pos[i]=q
        c.last_rows=b.snapshot()
        CameraMotor._apply_pitch(m,dict(mode='HOLD',error_xy=None),dict(status='LOST',source_id=1,captured_s=20.05),20.05,False)
        self.assertEqual(b.reg[5][42],2164)
