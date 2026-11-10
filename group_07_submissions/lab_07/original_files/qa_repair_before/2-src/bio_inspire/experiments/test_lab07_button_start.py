import json,tempfile,unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from .runtime_integration import run_runtime,ROOT
from . import test_demo_acceptance as scenario

class MemoryRecorder:
    def __init__(self):self.first=None;self.rows=[];self.end_seen=False;self.closed=False
    def record(self,row):
        if self.first is None:self.first=row['time_s']
        self.rows.append(row)
    def close(self):self.closed=True

class Tests(unittest.TestCase):
    def case(self,condition,delay,stop_s=None,tof_stall=None,recovery_near=False):
        with tempfile.TemporaryDirectory(dir=ROOT/'bio_inspire/results') as folder:
            root=Path(folder);p=root/'gate.json'
            profile=json.loads((ROOT/'bio_inspire/hardware/boot_ready_c1.json').read_text())
            profile.update(lab07_recording_seconds=180,lab07_start_button_presses=5)
            p.write_text(json.dumps(profile))
            presses=[delay+n for n in range(5)]
            duration=delay+22.
            near_interval=(5.2,7.) if recovery_near is True else recovery_near
            frames=[replace(f,button=any(t<=f.time_s<t+.25 for t in presses+[delay+9]),
                     touch=2<=f.time_s<3 or delay+14<=f.time_s<delay+14.5,
                     distance_m=.16 if 3<=f.time_s<4 or near_interval and near_interval[0]<=f.time_s<near_interval[1] else 1.2)
                    for f in scenario.Tests().frames(duration)]
            recorder=MemoryRecorder()
            with patch('bio_inspire.runtime.session_recording.prepare_recorder',return_value=recorder):
                result=run_runtime(root/'run',profile_path=p,condition=condition,duration_s=duration,
                                   frames_override=frames,stop_s=stop_s,tof_stall=tof_stall,face_lost=(0.,duration))
        self.assertFalse(result['forbidden_writes']);self.assertEqual(result['bounds_violations'],0)
        self.assertNotIn('FAULT',result['controller_states']);self.assertTrue(recorder.closed)
        return result,recorder
    def test_waiting_freezes_models_then_fifth_release_starts_identical_C0_C1(self):
        initials=[]
        for condition,delay in (('C0',8.),('C1',20.)):
            r,recorder=self.case(condition,delay)
            self.assertTrue(recorder.rows)
            first=recorder.rows[0];marker=first['measurement_start']
            self.assertGreaterEqual(first['time_s'],delay+4.25)
            self.assertEqual(marker['presses'],5)
            self.assertEqual(marker['digital_counter_baseline']['button'],5)
            self.assertEqual(first['fsm']['state'],'normal')
            self.assertEqual(first['oscillator']['state_ahm']['h'],0.)
            self.assertEqual(first['oscillator']['state_ahm']['stimulus'],0.)
            for model in marker['initial_oscillator_bank'].values():self.assertEqual(model['updates'],0)
            initials.append((first['oscillator']['o1'],first['oscillator']['o2'],first['oscillator']['decoder_phase_cycles']))
            self.assertTrue(all(v['behavior']=='normal' for v in r['trace'] if .5<v['time_s']<delay+4.25))
            self.assertTrue(any(v['behavior']=='button_look' and v['time_s']>delay+9 for v in r['trace']))
            self.assertTrue(any(v['behavior']=='happy' for v in r['trace']))
        self.assertEqual(initials[0],initials[1])
    def test_stop_before_fifth_release_does_not_start_recording(self):
        r,recorder=self.case('C1',8.,stop_s=11.)
        self.assertEqual(recorder.rows,[])
        self.assertFalse(r['position_writes_after_stop'])
    def test_tof_recovery_before_arming_does_not_leave_wait_mode_stuck(self):
        r,recorder=self.case('C1',8.,tof_stall=(4.5,5.2))
        self.assertIn('WAIT_TOF',r['controller_states'])
        self.assertTrue(recorder.rows,'Sensor recovery must return to Normal and accept five new presses')
    def test_recovery_into_near_holds_until_clear_before_normal_return(self):
        r,recorder=self.case('C1',10.,tof_stall=(4.5,5.2),recovery_near=True)
        self.assertTrue(all(v['behavior']=='distance_wait' for v in r['trace'] if 5.4<v['time_s']<6.9))
        self.assertTrue(recorder.rows)
    def test_near_interrupts_in_progress_preparation_return(self):
        r,recorder=self.case('C1',10.,tof_stall=(4.5,5.2),recovery_near=(5.6,7.))
        self.assertTrue(all(v['behavior']=='distance_wait' for v in r['trace'] if 5.8<v['time_s']<6.9))
        self.assertTrue(recorder.rows)

if __name__=='__main__':unittest.main()
