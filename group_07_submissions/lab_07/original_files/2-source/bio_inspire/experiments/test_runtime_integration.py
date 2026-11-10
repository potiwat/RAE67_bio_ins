import builtins
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from bio_inspire.experiments.runtime_integration import run_runtime, ROOT


class Tests(unittest.TestCase):
    def test_happy_height_probe_timeout_pause_keeps_near_and_stop(self):
        from dataclasses import replace
        from bio_inspire.experiments.ahm_input_bridge import scenario
        frames=[replace(f,touch=8.<=f.time_s<8.3,button=False,
                        distance_m=.1 if 30.<=f.time_s<36. else .5 if 16.<=f.time_s<20. else 1.2) for f in scenario(41)[:1000]]
        r=self.run_case(duration_s=50.,frames_override=frames,
                        profile_path=ROOT/'bio_inspire/hardware/happy_height_probe_c1_trial.json')
        self.assertNotIn('FAULT',r['controller_states'])
        self.assertTrue(any(row['behavior']=='happy' and row['time_s']>25 for row in r['trace']))
        self.assertIn('afraid',r['behaviors'])
        self.assertEqual(r['bounds_violations'],0)
        stopped=self.run_case(duration_s=20.,frames_override=frames,stop_s=15.,
                        profile_path=ROOT/'bio_inspire/hardware/happy_height_probe_c1_trial.json')
        self.assertFalse(stopped['position_writes_after_stop'])

    def test_fast_happy_candidate_preserves_six_state_preemption_and_bounds(self):
        from dataclasses import replace
        from bio_inspire.experiments.ahm_input_bridge import scenario
        frames=[replace(f,touch=8.<=f.time_s<30.,button=False,
                        distance_m=.1 if 35.<=f.time_s<42. else 1.2) for f in scenario(41)[:1200]]
        r=self.run_case(duration_s=60.,frames_override=frames,
                        profile_path=ROOT/'bio_inspire/hardware/happy_taught_fast_c1_candidate.json')
        self.assertNotIn('FAULT',r['controller_states'])
        self.assertTrue({'happy','afraid','sleepy'}<=set(r['behaviors']))
        self.assertEqual(r['bounds_violations'],0)
        self.assertFalse(r['forbidden_writes'])

    def test_taught_happy_profile_preemption_and_return_use_actual_runtime(self):
        from dataclasses import replace
        from bio_inspire.experiments.ahm_input_bridge import scenario
        frames=[replace(f,touch=8.<=f.time_s<45.,button=False,
                        distance_m=.1 if 47.<=f.time_s<54. else 1.2) for f in scenario(41)[:1600]]
        r=self.run_case(duration_s=80.,frames_override=frames,
                        profile_path=ROOT/'bio_inspire/hardware/happy_taught_center_c1_trial.json')
        self.assertNotIn('FAULT',r['controller_states'])
        self.assertTrue({'happy','afraid','sleepy'}<=set(r['behaviors']))
        self.assertEqual(r['bounds_violations'],0)
        self.assertFalse(r['forbidden_writes'])

    def run_case(self,**kw):
        with tempfile.TemporaryDirectory(dir=ROOT/'bio_inspire/results') as td:
            return run_runtime(Path(td),**kw)

    def test_actual_runtime_never_opens_real_devices_and_closes(self):
        original=builtins.__import__
        def reject(name,*args,**kwargs):
            if name.split('.')[0] in ('serial','gpiozero','picamera2','board','busio','lgpio'):
                raise AssertionError('Hardware import '+name)
            return original(name,*args,**kwargs)
        with patch('builtins.__import__',side_effect=reject):result=self.run_case(duration_s=4.)
        self.assertTrue(result['cleanup_confirmed']);self.assertTrue(result['bus_closed'])
        self.assertEqual(result['real_threads_started'],0)
        self.assertFalse(result['forbidden_writes'])
        self.assertIn('normal',result['behaviors'])

    def test_existing_evidence_directory_is_never_overwritten(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'bio_inspire/results') as td:
            out=Path(td);(out/'evidence.txt').write_text('preserve')
            with self.assertRaises(FileExistsError):run_runtime(out,duration_s=1.)
            self.assertEqual((out/'evidence.txt').read_text(),'preserve')

    def test_supported_m_preflight_uses_live_memory_pose_without_pid_write(self):
        r=self.run_case(duration_s=4.,initial_pose={1:2080,2:3000,3:3100,4:2010,5:2800},initial_torque=1)
        self.assertIn('READY',r['controller_states'])
        self.assertTrue(r['operator_start_preflight'])
        self.assertFalse(r['forbidden_writes'])

    def test_stop_cannot_be_overridden_by_touch_button_or_near(self):
        from dataclasses import replace
        from bio_inspire.experiments.ahm_input_bridge import scenario
        frames=[replace(f,touch=3.5<=f.time_s<4.,button=4.5<=f.time_s<5.,
                        distance_m=.1 if f.time_s>=5.5 else 1.2) for f in scenario(41)[:160]]
        r=self.run_case(duration_s=8.,stop_s=3.,frames_override=frames)
        self.assertTrue(all(v['operator_stopped'] for v in r['trace'] if v['time_s']>=3.05))
        self.assertFalse(r['position_writes_after_stop'])

    def test_camera_stall_faults_and_never_auto_resumes(self):
        r=self.run_case(duration_s=8.,camera_stall=(3.,4.))
        self.assertIn('FAULT',r['controller_states'])
        self.assertEqual(r['trace'][-1]['state'],'FAULT')
        self.assertTrue(r['cleanup_confirmed'])

    def test_tof_stale_recovers_without_releasing_torque(self):
        r=self.run_case(duration_s=8.,tof_stall=(3.,3.5))
        self.assertIn('WAIT_TOF',r['controller_states'])
        self.assertNotEqual(r['trace'][-1]['state'],'FAULT')
        self.assertFalse(r['forbidden_writes'])

    def test_bus_failure_has_safe_cleanup(self):
        r=self.run_case(duration_s=6.,bus_fault_s=3.)
        self.assertIn('FAULT',r['controller_states'])
        self.assertTrue(r['bus_closed']);self.assertTrue(r['cleanup_confirmed'])

    def test_lost_face_reacquisition_keeps_fresh_camera_and_head_bounds(self):
        r=self.run_case(duration_s=8.,face_lost=(3.,4.2))
        self.assertNotIn('FAULT',r['controller_states'])
        self.assertEqual(r['bounds_violations'],0)
        self.assertIn('LOST',{v['face_status'] for v in r['trace']})
        self.assertEqual(r['trace'][-1]['face_status'],'TRACKING')
        gaze_writes=[w for v in r['trace'] if 4.3<=v['time_s']<7.9 for w in v['writes']
                     if w['address']==42 and w['joint_id'] in (1,5)]
        self.assertTrue(gaze_writes)
        self.assertGreater(len({(w['joint_id'],w['value']) for w in gaze_writes}),1)

    def test_initial_approach_range_does_not_skip_normal(self):
        from dataclasses import replace
        from bio_inspire.experiments.ahm_input_bridge import scenario
        frames=[replace(f,distance_m=.5) for f in scenario(41)[:120]]
        r=self.run_case(duration_s=6.,frames_override=frames)
        self.assertEqual(set(r['behaviors']),{'normal'})

    def test_angry_defers_near_until_timer_then_afraid_and_clear(self):
        from dataclasses import replace
        from bio_inspire.experiments.ahm_input_bridge import scenario
        frames=[replace(f,touch=any(a<=f.time_s<a+.2 for a in (3.,3.4,3.8)),
                        distance_m=.1 if 4.5<=f.time_s<14. else 1.2) for f in scenario(41)[:400]]
        r=self.run_case(duration_s=20.,frames_override=frames)
        self.assertIn('angry',r['behaviors']);self.assertIn('afraid',r['behaviors'])
        deferred=[v for v in r['trace'] if v['fsm'].get('angry_near_deferred')]
        self.assertTrue(deferred)
        self.assertTrue(all(v['fsm']['state']=='angry' for v in deferred))
        angry=[v for v in r['trace'] if v['fsm']['state']=='angry' and v['fsm']['timer_ready']]
        afraid=next(v for v in r['trace'] if v['fsm']['state']=='afraid')
        self.assertGreaterEqual(afraid['time_s']-angry[0]['fsm_active_since_s'],5.-1e-9)
        self.assertLess(afraid['time_s']-angry[0]['fsm_active_since_s'],5.15)
        self.assertTrue(any(v['time_s']>=14. and v['fsm']['state']=='normal' for v in r['trace']))
        self.assertNotIn('FAULT',r['controller_states'])

    def test_sleepy_to_happy_wakes_head_and_keeps_gaze(self):
        from dataclasses import replace
        from bio_inspire.experiments.ahm_input_bridge import scenario
        frames=[replace(f,touch=20.<=f.time_s<20.3) for f in scenario(41)[:540]]
        r=self.run_case(duration_s=27.,frames_override=frames)
        self.assertIn('sleepy',r['behaviors'])
        happy=[v for v in r['trace'] if v['behavior']=='happy' and v['time_s']>=22.]
        self.assertTrue(happy)
        self.assertTrue(all(v['happy_head_wake_goal'] is None for v in happy))
        self.assertTrue(all(v['follow_enabled'] for v in happy))
        self.assertNotIn('FAULT',r['controller_states'])

    def test_interested_survives_face_loss_then_reacquires_without_fault(self):
        from dataclasses import replace
        from bio_inspire.experiments.ahm_input_bridge import scenario
        frames=[replace(f,button=3.<=f.time_s<3.3) for f in scenario(41)[:220]]
        r=self.run_case(duration_s=11.,frames_override=frames,face_lost=(6.,7.2))
        self.assertTrue(any(v['behavior']=='interested' and v['face_status']=='LOST' for v in r['trace']))
        self.assertNotIn('FAULT',r['controller_states'])
        self.assertEqual(r['bounds_violations'],0)

    def test_boot_parking_keeps_normal_despite_inputs_until_manual_start(self):
        from dataclasses import replace
        from .ahm_input_bridge import scenario
        frames=[replace(f,button=3.<=f.time_s<3.3,touch=6.<=f.time_s<12.,distance_m=.16 if 15.<=f.time_s<18. else 1.2) for f in scenario(41)[:500]]
        r=self.run_case(duration_s=25.,frames_override=frames,
            profile_path=ROOT/'bio_inspire/hardware/boot_ready_c1.json',park_only=True)
        self.assertNotIn('FAULT',r['controller_states'])
        self.assertEqual(r['behaviors'],['normal'])
        self.assertTrue(all(v['fsm']['state']=='normal' for v in r['trace']))
        self.assertTrue(all(v['rhythm'].get('envelope',0) in (None,0) for v in r['trace']))


if __name__=='__main__':unittest.main()
