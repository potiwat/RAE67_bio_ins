import unittest,json,tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from camera_preview import boot_motor_start,main
class Tests(unittest.TestCase):
    def test_boot_start_requires_dedicated_approved_profile(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'profile.json';p.write_text('{}')
            factory=Mock()
            with self.assertRaises(ValueError):boot_motor_start(p,factory)
            factory.assert_not_called()
            p.write_text(json.dumps(dict(boot_auto_start_approved=True,automatic_fsm_enabled=True,normal_ahm_condition='C1',ahm_scope='all_states')))
            self.assertIs(boot_motor_start(p,factory),factory.return_value)
            factory.assert_called_once_with(p,operator_start=True)
    def test_boot_mode_needs_headless_and_explicit_autostart(self):
        with patch('camera_preview.live_preview') as live:
            for options in (['--boot-ready'],['--headless','--boot-ready'],['--headless','--manual-tuning']):
                with self.assertRaises(SystemExit):main(['--live','--max-age-s','.5','--normal-profile','x',*options])
            live.assert_not_called()

    def test_headless_boot_captures_and_closes_without_any_gui_calls(self):
        import sys
        from contextlib import ExitStack
        from camera_preview import live_preview
        class Frame:
            def __getitem__(self,key):return self
            def copy(self):return self
        request=Mock();request.make_array.return_value=Frame()
        request.get_metadata.return_value={'SensorTimestamp':1000000000}
        camera=Mock();camera.stream_configuration.return_value={'size':(320,180)}
        camera.capture_request.return_value=request
        motor=Mock();motor.just_ready=False;motor.wake_serial=0
        motor.snapshot_view.return_value={'behavior':'normal','route_phase':None}
        motor.vision_ready.return_value=True;motor.fault_message.return_value=''
        vision=Mock();vision.latest.return_value=None
        with tempfile.TemporaryDirectory() as d,ExitStack() as stack:
            profile=Path(d)/'boot.json';profile.write_text(json.dumps(dict(boot_auto_start_approved=True,automatic_fsm_enabled=True,normal_ahm_condition='C1',ahm_scope='all_states')))
            args=SimpleNamespace(headless=True,boot_ready=True,auto_normal_start=True,normal_profile=profile,
                camera=0,cascade=None,max_age_s=.5,max_frames=1)
            cv=SimpleNamespace()  # No GUI methods at all.
            stack.enter_context(patch.dict(sys.modules,{'cv2':cv,'picamera2':SimpleNamespace(Picamera2=Mock(return_value=camera)),
                'fcntl':SimpleNamespace(flock=Mock(),LOCK_EX=2,LOCK_NB=4)}))
            stack.enter_context(patch.dict('os.environ',{},clear=True))
            stack.enter_context(patch('camera_preview.find_cascade',return_value=object()))
            stack.enter_context(patch('camera_preview.configure_full_sensor_view',return_value={}))
            stack.enter_context(patch('camera_preview.LatestWorker',return_value=vision))
            stack.enter_context(patch('camera_preview.time.CLOCK_BOOTTIME',7,create=True))
            stack.enter_context(patch('camera_preview.time.clock_gettime',return_value=1.1,create=True))
            factory=stack.enter_context(patch('bio_inspire.runtime.camera_motor.CameraMotor',return_value=motor))
            live_preview(args)
            factory.assert_called_once_with(profile,operator_start=True)
            motor.apply.assert_called_once();motor.close.assert_called_once()
            camera.stop.assert_called_once();camera.close.assert_called_once();request.release.assert_called_once()

    def test_boot_park_passes_explicit_park_only_before_worker_starts(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'boot.json';p.write_text(json.dumps(dict(boot_auto_start_approved=True,automatic_fsm_enabled=True,normal_ahm_condition='C1',ahm_scope='all_states')))
            factory=Mock();boot_motor_start(p,factory,park_only=True)
            factory.assert_called_once_with(p,operator_start=True,park_only=True)
