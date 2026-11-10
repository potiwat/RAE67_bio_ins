import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from bio_inspire.runtime.normal_measurement import NormalMeasurement, ScheduledAHM


class Tests(unittest.TestCase):
    def fixture(self):return dict(dt_s=.05,stimulus_policy='near_only_v2',raw_sha256='a'*64,
        source_start_s=80.,source_end_s=130.,samples=[dict(stimulus=float(200<=k<400),source_id=str(k),source_s=80+k*.05) for k in range(1000)])

    def test_reference_matches_teacher_timing_and_same_input(self):
        from bio_inspire.experiments.ahm_cpg_compare import course_model,RATES
        c0=ScheduledAHM(self.fixture(),'C0');c1=ScheduledAHM(self.fixture(),'C1')
        self.assertEqual(c0.values,c1.values)
        c0.start(10.);c1.start(10.);h=0.
        for k,s in enumerate(c1.values):
            a=c0.step(10+k*.05,None);b=c1.step(10+k*.05,None)
            self.assertEqual(a['stimulus'],s)
            self.assertAlmostEqual(a['phi'],.1+.03*s)
            self.assertAlmostEqual(b['h'],h)
            self.assertAlmostEqual(b['phi'],.1+.03*h)
            h=course_model()['hormone_step'](h,s,.05,RATES)['h']
        self.assertEqual(c1.step(60,None)['phi'],.1)
        self.assertEqual(c1.step(60,None)['reason'],'complete')

    def test_skipped_indices_logged_and_disabled_baseline(self):
        a=ScheduledAHM(self.fixture(),'C1');a.start(1.)
        a.step(1.,None);r=a.step(1.21,None)
        self.assertEqual(r['schedule_index'],4);self.assertEqual(r['skipped_schedule_updates'],3)
        self.assertEqual(a.step(1.3,None,enabled=False)['phi'],.1)

    def test_invalid_reference_rejected(self):
        for change in (dict(dt_s=.1),dict(samples=[]),dict(stimulus_policy='other'),
                       dict(samples=[dict(stimulus=None)]*1000)):
            with self.assertRaises(ValueError):ScheduledAHM({**self.fixture(),**change},'C1')

    def test_supervisor_never_dispatches_emotions_and_near_aborts(self):
        from test_taught_crouch import Tests as Fixture
        from state_rhythms import StateRhythms
        m,b=Fixture().motor();m.behavior_trial='normal'
        m.automatic_fsm=Mock();m.distance_gate=SimpleNamespace(near=False)
        m.rhythm_driver=StateRhythms(Mock(),Mock());m._key=Mock();m.now=lambda:20.
        d=NormalMeasurement(self.fixture(),'C0',None)
        with patch('bio_inspire.runtime.distance_behavior.poll_distance'):
            d.service(m,20.)
            self.assertEqual(d.state,'running')
            m.automatic_fsm.service.assert_not_called()
            self.assertEqual(m.rhythm_driver.breathing.rhythm.envelope,0.)
            m.distance_gate.near=True;d.service(m,20.1)
        self.assertEqual(d.state,'aborted');m._key.assert_called_with(ord('h'))
        m.distance_gate.near=False
        with patch('bio_inspire.runtime.distance_behavior.poll_distance'):d.service(m,20.2)
        self.assertEqual(d.state,'aborted')

    def test_wait_tof_fault_stop_abort_instead_of_resuming(self):
        for state,stopped in [('WAIT_TOF',False),('FAULT',False),('READY',True)]:
            from test_taught_crouch import Tests as Fixture
            m,b=Fixture().motor();m.behavior_trial='normal';m.controller.state=state
            m.operator_stopped=stopped;m._key=Mock();m.distance_gate=SimpleNamespace(near=False)
            m.automatic_fsm=Mock();m.now=lambda:20.
            d=NormalMeasurement(self.fixture(),'C1',None);d.state='running';d.replay.start(19.)
            with patch('bio_inspire.runtime.distance_behavior.poll_distance'):d.service(m,20.)
            self.assertEqual(d.state,'aborted')

    def test_bounded_complete_log_and_early_q_classification(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'result.json'
            d=NormalMeasurement(self.fixture(),'C0',path)
            d.replay.start(0.);d.state='running'
            m=SimpleNamespace(controller=SimpleNamespace(state='READY',last_rows=[],last_joint_targets={}),
                              behavior_trial='normal',rhythm_view_cache={})
            for k in range(1000):d.record(m,k*.05)
            d.close('operator_q')
            data=json.loads(path.read_text())
            self.assertFalse(data['completed']);self.assertEqual(len(data['trace']),1000)

    def test_near_after_completed_saved_trial_still_holds(self):
        from test_taught_crouch import Tests as Fixture
        m,b=Fixture().motor();m.distance_gate=SimpleNamespace(near=True)
        m._key=Mock();m.now=lambda:80.
        d=NormalMeasurement(self.fixture(),'C0',None)
        d.state='complete';d.saved=True;d.replay.start(0.)
        with patch('bio_inspire.runtime.distance_behavior.poll_distance'):d.service(m,80.)
        m._key.assert_called_with(ord('h'))

    def test_final_cycle_fault_cannot_be_saved_as_completed(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'result.json';d=NormalMeasurement(self.fixture(),'C0',path)
            d.state='complete';d.replay.start(0.)
            m=SimpleNamespace(controller=SimpleNamespace(state='FAULT',last_rows=[]),behavior_trial='normal',_key=Mock())
            d.record(m,50.)
            self.assertFalse(json.loads(path.read_text())['completed'])
            m._key.assert_called_with(ord('h'))

    def test_worker_exception_before_final_record_marks_incomplete(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'result.json';d=NormalMeasurement(self.fixture(),'C0',path)
            d.state='complete';d.worker_failed();d.close('worker_exit')
            self.assertFalse(json.loads(path.read_text())['completed'])


if __name__=='__main__':unittest.main()
