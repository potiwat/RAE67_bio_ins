import json
import subprocess
import sys
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from camera_preview import normalized_boxes, replay_rows

class RestartTests(unittest.TestCase):
    def test_retry_closes_old_owner_before_fresh_preflight(self):
        from camera_preview import operator_motor_start
        from unittest.mock import Mock
        old=Mock();old.fault_message.return_value='power lost'
        events=[]
        old.disconnect_for_retry.side_effect=lambda:events.append('closed')
        def factory(profile,operator_start):
            self.assertEqual(events,['closed']);self.assertTrue(operator_start)
            return 'new'
        self.assertEqual(operator_motor_start(old,'profile',factory),'new')
        old.fault_message.return_value=''
        self.assertIs(operator_motor_start(old,'profile',factory),old)
        old.snapshot_view.return_value={'state':'STOPPED'}
        events.clear()
        self.assertEqual(operator_motor_start(old,'profile',factory),'new')

from camera_preview import live_preview, PreviewEngine


class PreviewTests(unittest.TestCase):
    def test_full_sensor_view_sets_maximum_crop_and_records_native_area(self):
        from camera_preview import configure_full_sensor_view
        from unittest.mock import Mock
        c=Mock();c.camera_properties={'Model':'imx708','PixelArraySize':(4608,2592)}
        c.camera_controls={'ScalerCrop':((0,0,82,64),(0,0,4608,2592),(0,0,4608,2592))}
        report=configure_full_sensor_view(c)
        c.set_controls.assert_called_once_with({'ScalerCrop':(0,0,4608,2592)})
        self.assertEqual(report['requested_scaler_crop'],(0,0,4608,2592))
        self.assertEqual(report['pixel_array_size'],(4608,2592))

    def test_wide_capture_uses_full_sensor_mode_not_central_high_speed_crop(self):
        from camera_preview import capture_configuration
        config=capture_configuration(30)
        self.assertEqual(config['main']['size'],(640,360))
        self.assertEqual(config['lores']['size'],(320,180))
        self.assertEqual(config['sensor'],{'output_size':(2304,1296),'bit_depth':10})
        self.assertEqual(config['controls']['FrameRate'],30)

    def test_detector_pixels_become_normalized_boxes(self):
        self.assertEqual(normalized_boxes([(160, 60, 80, 60)], 320, 240),
                         [(0.5, 0.25, 0.25, 0.25)])

    def test_bad_detection_does_not_become_a_motion_target(self):
        for rects in [[(-1, 0, 10, 10)], [(0, 0, 500, 10)], [(0, 0, 0, 10)]]:
            with self.assertRaises(ValueError):
                normalized_boxes(rects, 320, 240)

    def test_replay_end_to_end_does_not_wake_sleepy_from_face(self):
        rows = [dict(boxes=[(.2, .2, .1, .1)], captured_s=1, processed_s=1),
                dict(boxes=[], captured_s=2, processed_s=2),
                dict(boxes=[], captured_s=3, processed_s=3, state='sleepy'),
                dict(boxes=[(.7, .7, .1, .1)], captured_s=4, processed_s=4, state='normal')]
        result = list(replay_rows(rows, .5))
        self.assertEqual([r['intent']['mode'] for r in result],
                         ['FOLLOW', 'SEARCH', 'DOZE', 'FOLLOW'])
        self.assertEqual([r['observation']['status'] for r in result],
                         ['ACQUIRED', 'LOST', 'LOST', 'ACQUIRED'])
        self.assertTrue(all(not r['intent']['motor_output_enabled'] for r in result))
        self.assertTrue(all(not r['intent']['counts_as_activity'] for r in result))

    def test_replay_fault_holds_and_never_replays_an_old_error(self):
        rows = [dict(boxes=[(.2, .2, .1, .1)], captured_s=1, processed_s=1, fault=True),
                dict(boxes=[], captured_s=2, processed_s=3)]
        result = list(replay_rows(rows, .5))
        self.assertTrue(all(r['intent']['mode'] == 'HOLD' for r in result))
        self.assertTrue(all(r['intent']['error_xy'] is None for r in result))

    def test_help_does_not_import_camera_or_open_devices(self):
        script = Path(__file__).with_name('camera_preview.py')
        result = subprocess.run([sys.executable, '-B', str(script), '--help'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--replay', result.stdout)
        self.assertIn('--check', result.stdout)

    def test_explicit_live_requires_age_limit_before_importing_devices(self):
        script = Path(__file__).with_name('camera_preview.py')
        result = subprocess.run([sys.executable, '-B', str(script), '--live'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('--max-age-s', result.stderr)

    def test_bad_replay_controls_never_reset_or_switch_player(self):
        engine = PreviewEngine(.5)
        engine.step(dict(boxes=[(.1, .1, .1, .1)], captured_s=1, processed_s=1))
        for changes in [{'reset': 'false'}, {'fault': 'false'}, {'state': None}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                engine.step(dict(boxes=[(.7, .7, .1, .1)], captured_s=2,
                                 processed_s=2, **changes))
        result = engine.step(dict(boxes=[(.7, .7, .1, .1)], captured_s=2, processed_s=2))
        self.assertEqual(result['observation']['status'], 'LOST')

    def test_replay_rows_must_be_objects(self):
        for row in [None, [], 'face']:
            with self.subTest(row=row), self.assertRaises(ValueError):
                PreviewEngine(.5).step(row)

    def test_request_and_camera_released_even_if_detector_fails(self):
        # Camera/OpenCV are external hardware boundaries unavailable on this PC.
        # This catches leaked camera requests when processing fails after capture.
        events = []

        class Frame:
            shape=(240,320,3)
            def __getitem__(self, key): return self
            def copy(self): return self

        class Request:
            def make_array(self, stream): return Frame()
            def get_metadata(self): return {'SensorTimestamp': 1_000_000_000}
            def release(self): events.append('release')

        class Camera:
            def __init__(self, **kwargs): pass
            def configure(self, config): pass
            def create_preview_configuration(self, **kwargs): return kwargs
            def stream_configuration(self, stream): return {'size': (320, 240)}
            def start(self): events.append('start')
            def capture_request(self): return Request()
            def stop(self): events.append('stop')
            def close(self): events.append('close')

        class Classifier:
            def empty(self): return False
            def detectMultiScale(self, *args): raise RuntimeError('detector failed')

        cv2 = SimpleNamespace(CascadeClassifier=lambda path: Classifier(),
            namedWindow=lambda *a: None, resizeWindow=lambda *a: None, WINDOW_NORMAL=0,
            COLOR_GRAY2BGR=0,FONT_HERSHEY_SIMPLEX=0,WND_PROP_VISIBLE=0,
            cvtColor=lambda *a:Frame(),drawMarker=lambda *a:None,putText=lambda *a:None,
            rectangle=lambda *a:None,imshow=lambda *a:None,
            waitKey=lambda *a:time.sleep(.01) or 255,getWindowProperty=lambda *a:1,
            destroyAllWindows=lambda: events.append('destroy'))
        locks = SimpleNamespace(flock=lambda *a: None, LOCK_EX=2, LOCK_NB=4)
        args = SimpleNamespace(cascade=Path(__file__), camera=0, max_age_s=.5, max_frames=0)
        with patch.dict(sys.modules, {'cv2': cv2, 'picamera2': SimpleNamespace(Picamera2=Camera),
                                      'fcntl': locks}), \
                patch.dict('os.environ', {'DISPLAY': ':test'}), \
                patch('camera_preview.time.clock_gettime',return_value=1.1,create=True), \
                patch('camera_preview.time.CLOCK_BOOTTIME', 7, create=True):
            with self.assertRaisesRegex(RuntimeError, 'Vision worker failed'):
                live_preview(args)
        self.assertEqual(events[0],'start')
        self.assertIn('release',events[:-3])
        self.assertEqual(events[-3:],['stop','close','destroy'])


if __name__ == '__main__':
    unittest.main()

class PlayerGlanceMemoryTests(unittest.TestCase):
    def test_button_glance_cannot_replace_player_with_background_box(self):
        e=PreviewEngine(.5);player=(.25,.2,.4,.5);background=(.4,.3,.1,.1)
        e.step(dict(boxes=[player],captured_s=1.,processed_s=1.1))
        r=e.step(dict(boxes=[background],captured_s=1.2,processed_s=1.3,preserve_player=True))
        self.assertIsNone(r['observation']['box'])
        self.assertEqual(e.tracker.previous_box,player)
        r=e.step(dict(boxes=[player],captured_s=1.4,processed_s=1.5))
        self.assertEqual(r['observation']['box'],player)

    def test_shifted_player_after_glance_is_confirmed_without_old_box_overlap(self):
        e=PreviewEngine(.5);old=(.05,.1,.1,.2);player=(.35,.25,.25,.45)
        e.step(dict(boxes=[old],captured_s=1.,processed_s=1.01))
        e.step(dict(boxes=[],captured_s=1.1,processed_s=1.11,preserve_player=True))
        for t in (1.2,1.3):
            r=e.step(dict(boxes=[player],captured_s=t,processed_s=t+.01))
            self.assertIsNone(r['observation']['box'])
        r=e.step(dict(boxes=[player],captured_s=1.4,processed_s=1.41))
        self.assertEqual(r['observation']['status'],'ACQUIRED')
        self.assertEqual(r['observation']['box'],player)
        self.assertEqual(r['intent']['mode'],'FOLLOW')
        self.assertEqual(r['observation']['source_id'],5)

    def test_glance_without_prior_player_requires_stable_candidate(self):
        e=PreviewEngine(.5);player=(.35,.25,.25,.45);tiny=(.45,.45,.05,.05)
        e.step(dict(boxes=[],captured_s=1.,processed_s=1.01,preserve_player=True))
        for t in (1.1,1.2,1.3):
            r=e.step(dict(boxes=[tiny],captured_s=t,processed_s=t+.01))
            self.assertIsNone(r['observation']['box'])
        for t in (1.4,1.5,1.6):
            r=e.step(dict(boxes=[player,tiny],captured_s=t,processed_s=t+.01))
        self.assertEqual(r['observation']['box'],player)

    def test_reacquisition_does_not_bypass_stale_ambiguous_or_invalid_frames(self):
        e=PreviewEngine(.5);old=(.05,.1,.1,.2);a=(.25,.25,.2,.4);b=(.6,.25,.2,.4)
        e.step(dict(boxes=[old],captured_s=1.,processed_s=1.01))
        e.step(dict(boxes=[],captured_s=1.1,processed_s=1.11,preserve_player=True))
        for t in (1.2,1.3,1.4):
            r=e.step(dict(boxes=[a,b],captured_s=t,processed_s=t+.01))
            self.assertIsNone(r['observation']['box'])
        r=e.step(dict(boxes=[a],captured_s=1.5,processed_s=2.1))
        self.assertEqual(r['observation']['status'],'STALE')
        r=e.step(dict(boxes=[(0.,0.,-1.,.2)],captured_s=2.2,processed_s=2.21))
        self.assertEqual(r['observation']['status'],'INVALID')
        self.assertEqual(e.tracker.previous_box,old)

    def test_no_unrelated_face_switch_outside_glance_and_recovery_expires(self):
        e=PreviewEngine(.5);old=(.05,.1,.1,.2);new=(.45,.25,.25,.45)
        e.step(dict(boxes=[old],captured_s=1.,processed_s=1.01))
        for t in (1.1,1.2,1.3):
            self.assertEqual(e.step(dict(boxes=[new],captured_s=t,processed_s=t+.01))['observation']['status'],'LOST')
        e.step(dict(boxes=[],captured_s=1.4,processed_s=1.41,preserve_player=True))
        e.step(dict(boxes=[],captured_s=1.5,processed_s=1.51))
        for t in (7.,7.1,7.2):
            self.assertEqual(e.step(dict(boxes=[new],captured_s=t,processed_s=t+.01))['observation']['status'],'LOST')

    def test_unequal_overlapping_detections_remain_ambiguous(self):
        e=PreviewEngine(.5);old=(.1,.1,.4,.5);a=(.12,.12,.4,.4);small=(.13,.13,.1,.1)
        e.step(dict(boxes=[old],captured_s=1.,processed_s=1.01))
        e.step(dict(boxes=[],captured_s=1.1,processed_s=1.11,preserve_player=True))
        for t in (1.2,1.3,1.4,1.5):
            r=e.step(dict(boxes=[a,small],captured_s=t,processed_s=t+.01))
            self.assertEqual(r['observation']['status'],'AMBIGUOUS')
            self.assertIsNone(r['observation']['error_xy'])
        self.assertEqual(e.tracker.previous_box,old)

    def test_fault_clears_partial_candidate_confirmation(self):
        e=PreviewEngine(.5);old=(.05,.1,.1,.2);player=(.35,.25,.25,.45)
        e.step(dict(boxes=[old],captured_s=1.,processed_s=1.01))
        e.step(dict(boxes=[],captured_s=1.1,processed_s=1.11,preserve_player=True))
        for t in (1.2,1.3):e.step(dict(boxes=[player],captured_s=t,processed_s=t+.01))
        r=e.step(dict(boxes=[player],captured_s=1.4,processed_s=1.41,fault=True))
        self.assertIsNone(r['observation']['box'])
        r=e.step(dict(boxes=[player],captured_s=1.5,processed_s=1.51))
        self.assertIsNone(r['observation']['box'])

    def test_active_yaw_scan_can_confirm_shifted_player_without_glance(self):
        e=PreviewEngine(.5);old=(.05,.1,.1,.2);player=(.35,.25,.25,.45)
        e.step(dict(boxes=[old],captured_s=1.,processed_s=1.01))
        for t in (1.2,1.3,1.4):
            r=e.step(dict(boxes=[player],captured_s=t,processed_s=t+.01,acquisition_scan=True))
        self.assertEqual(r['observation']['status'],'ACQUIRED')
        self.assertEqual(r['observation']['box'],player)
