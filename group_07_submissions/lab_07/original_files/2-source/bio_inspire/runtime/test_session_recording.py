import json,tempfile,unittest
from pathlib import Path
from session_recording import SessionRecorder

class Tests(unittest.TestCase):
    def test_new_input_queue_loss_keeps_raw_but_marks_incomplete(self):
        with tempfile.TemporaryDirectory() as d:
            r=SessionRecorder(Path(d),'C0',30.)
            r.record(dict(time_s=0.,digital_inputs={'touch':dict(overflow_presses=2,stable_sequence=0,stable_edges=[])}))
            r.record(dict(time_s=30.,digital_inputs={'touch':dict(overflow_presses=3,stable_sequence=0,stable_edges=[])}))
            r.close();summary=json.loads((Path(d)/'summary.json').read_text())
            self.assertFalse(summary['complete']);self.assertEqual(summary['written'],2)
            self.assertIn('overflow',summary['input_health_error'])

    def test_rows_and_metadata_are_visible_before_close_for_live_ros(self):
        import time
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);r=SessionRecorder(p,'C0',30.,{'origin':'synthetic_test'})
            try:
                r.record({'time_s':0.})
                deadline=time.monotonic()+1.
                while not (p/'trace.jsonl').read_text() and time.monotonic()<deadline:time.sleep(.01)
                self.assertEqual(json.loads((p/'trace.jsonl').read_text()),{'time_s':0.})
                self.assertEqual(json.loads((p/'metadata.json').read_text())['origin'],'synthetic_test')
            finally:r.close()

    def test_complete_and_early_close_are_distinguished(self):
        for end,complete in ((600.,True),(20.,False)):
            with tempfile.TemporaryDirectory() as d:
                r=SessionRecorder(Path(d),'C0',600.)
                r.record({'time_s':0.});r.record({'time_s':end});r.close()
                m=json.loads((Path(d)/'summary.json').read_text())
                self.assertEqual(m['complete'],complete)
                self.assertEqual(m['written'],2)
                self.assertEqual(len((Path(d)/'trace.jsonl').read_text().splitlines()),2)
    def test_existing_output_not_overwritten_and_invalid_values_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'trace.jsonl').write_text('keep')
            with self.assertRaises(FileExistsError):SessionRecorder(p,'C0',600.)
            self.assertEqual((p/'trace.jsonl').read_text(),'keep')
        for c,t in (('C2',600.),('C0',-1.),('C1',float('nan'))):
            with self.assertRaises(ValueError):SessionRecorder(Path('unused'),c,t)
    def test_clock_regression_marks_incomplete(self):
        with tempfile.TemporaryDirectory() as d:
            r=SessionRecorder(Path(d),'C1',600.)
            r.record({'time_s':2.});r.record({'time_s':1.});r.close()
            self.assertFalse(json.loads((Path(d)/'summary.json').read_text())['complete'])

    def test_profiles_preserve_accepted_movement_and_only_switch_condition(self):
        root=Path(__file__).resolve().parents[1]/'hardware'
        base=json.loads((root/'happy_dynamic_c1_trial.json').read_text(encoding='utf8'))
        from session_recording import validate_recording
        for condition in ('C0','C1'):
            for duration in (30,60,180,600):
                p=json.loads((root/f'lab07_r37_{condition}_{duration}s.json').read_text(encoding='utf8'))
                self.assertEqual(validate_recording(p),duration)
                self.assertEqual({k:v for k,v in p.items() if k not in ('normal_ahm_condition','lab07_recording_seconds')},
                                 {k:v for k,v in base.items() if k!='normal_ahm_condition'})
    def test_bad_serialization_is_incomplete(self):
        with tempfile.TemporaryDirectory() as d:
            r=SessionRecorder(Path(d),'C1',600.)
            r.record({'time_s':0.,'bad':float('nan')});r.close()
            summary=json.loads((Path(d)/'summary.json').read_text())
            self.assertFalse(summary['complete']);self.assertIsNotNone(summary['error'])

    def test_fault_cannot_be_called_complete(self):
        with tempfile.TemporaryDirectory() as d:
            r=SessionRecorder(Path(d),'C0',600.)
            r.record({'time_s':0.,'state':'READY'});r.record({'time_s':300.,'state':'FAULT'})
            r.record({'time_s':600.,'state':'READY'});r.close()
            self.assertFalse(json.loads((Path(d)/'summary.json').read_text())['complete'])

    def test_all_four_profiles_reach_device_boundary_without_opening_hardware(self):
        from unittest.mock import patch
        from camera_motor import CameraMotor
        root=Path(__file__).resolve().parents[1]/'hardware'
        for condition in ('C0','C1'):
            for duration in (30,60,180,600):
                profile=root/f'lab07_r37_{condition}_{duration}s.json'
                with patch('camera_motor.open_bus',side_effect=RuntimeError('DEVICE_BOUNDARY')) as bus:
                    with self.assertRaisesRegex(RuntimeError,'DEVICE_BOUNDARY'):CameraMotor(profile)
                    bus.assert_called_once()
