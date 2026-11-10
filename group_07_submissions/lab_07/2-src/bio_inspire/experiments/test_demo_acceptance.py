"""Acceptance scenarios: production loop, virtual devices, no physical claims."""
import random,tempfile,unittest
from dataclasses import replace
from pathlib import Path
from .runtime_integration import run_runtime,ROOT
from .ahm_input_bridge import scenario
PROFILE=ROOT/'bio_inspire/hardware/boot_ready_c1.json'
class Tests(unittest.TestCase):
    def run_case(self,frames,duration=45.,**kw):
        with tempfile.TemporaryDirectory(dir=ROOT/'bio_inspire/results') as folder:
            r=run_runtime(Path(folder),profile_path=PROFILE,duration_s=duration,frames_override=frames,**kw)
        self.assertFalse(r['forbidden_writes']);self.assertEqual(r['bounds_violations'],0)
        self.assertTrue(r['bus_closed']);return r
    def frames(self,duration=45.):
        return [replace(f,button=False,touch=False,distance_m=1.2,distance_kind='range') for f in scenario(41)[:int(duration/.05)]]
    def test_latest_happy_to_angry_then_normal_without_false_fault(self):
        frames=[replace(f,touch=3.<=f.time_s<4. or any(a<=f.time_s<a+.15 for a in (6.,6.4,6.8))) for f in self.frames()]
        r=self.run_case(frames)
        self.assertNotIn('FAULT',r['controller_states'])
        self.assertIn('happy',r['behaviors']);self.assertIn('angry',r['behaviors'])
        self.assertTrue(any(v['time_s']>20. and v['fsm']['state']=='normal' for v in r['trace']))
    def test_no_face_is_not_camera_failure(self):
        frames=[replace(f,touch=3.<=f.time_s<4.,button=18.<=f.time_s<18.3) for f in self.frames()]
        r=self.run_case(frames,face_lost=(0.,40.))
        self.assertNotIn('FAULT',r['controller_states'])
        self.assertIn('happy',r['behaviors'])
    def test_randomized_user_inputs_keep_bounds_and_do_not_false_fault(self):
        for seed in range(41,61):
            rng=random.Random(seed);events=[]
            for n in range(18):events.append((2.+n*2.,rng.choice(('button','touch','burst','near'))))
            frames=[]
            for f in self.frames():
                button=any(k=='button' and t<=f.time_s<t+.2 for t,k in events)
                touch=any(k=='touch' and t<=f.time_s<t+1. or k=='burst' and any(t+d<=f.time_s<t+d+.15 for d in (0.,.4,.8)) for t,k in events)
                near=any(k=='near' and t<=f.time_s<t+1. for t,k in events)
                frames.append(replace(f,button=button,touch=touch,distance_m=.16 if near else 1.2))
            with self.subTest(seed=seed):
                r=self.run_case(frames)
                self.assertNotIn('FAULT',r['controller_states'])
    def test_real_sensor_fault_and_stop_still_stop(self):
        for kw in ({'stop_s':5.},{'camera_stall':(5.,7.)},{'bus_fault_s':5.}):
            r=self.run_case(self.frames(10.),duration=10.,**kw)
            if 'stop_s' in kw:self.assertFalse(r['position_writes_after_stop'])
            else:self.assertIn('FAULT',r['controller_states'])

    def test_no_target_clear_and_held_touch_do_not_stall(self):
        frames=[]
        for f in self.frames():
            frames.append(replace(f,touch=3.<=f.time_s<15.,
                distance_m=.16 if 20.<=f.time_s<24. else None if 24.<=f.time_s<30. else 1.2,
                distance_kind='no_target' if 24.<=f.time_s<30. else 'range'))
        r=self.run_case(frames)
        self.assertNotIn('FAULT',r['controller_states'])
        self.assertIn('happy',r['behaviors']);self.assertIn('afraid',r['behaviors'])
        self.assertTrue(any(v['time_s']>=25. and v['fsm']['state']=='normal' for v in r['trace']))
