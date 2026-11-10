import unittest
import json
from pathlib import Path
import tempfile
from bio_inspire.experiments import ahm_input_bridge as bridge
from bio_inspire.experiments import ahm_cpg_compare as model


def frame(t, *, button=False, touch=False, distance=1.2, kind='range', sampled=None):
    return bridge.InputFrame(t, t if sampled is None else sampled, button, touch, kind, distance, f'snapshot_{t}')


class InputBridgeTests(unittest.TestCase):
    def test_digital_debounce_not_raw_bounce_drives_stimulus(self):
        a = bridge.InputAdapter()
        self.assertEqual(a.step(frame(0, button=True))['stimulus'], 0)
        self.assertEqual(a.step(frame(.05, button=False))['stimulus'], 0)
        self.assertEqual(a.step(frame(.1, button=True))['stimulus'], 0)
        result = a.step(frame(.2, button=True))
        self.assertEqual(result['stimulus'], 1)
        self.assertEqual([e['kind'] for e in result['events']], ['button'])
        self.assertEqual(a.step(frame(.3, button=True))['events'], [])

    def test_touch_release_is_debounced_and_does_not_create_press(self):
        a = bridge.InputAdapter()
        a.step(frame(0, touch=True)); a.step(frame(.1, touch=True))
        self.assertEqual(a.step(frame(.15))['stimulus'], 1)
        result = a.step(frame(.25))
        self.assertEqual(result['stimulus'], 0)
        self.assertEqual(result['events'], [])

    def test_range_hysteresis_and_near_priority(self):
        a = bridge.InputAdapter(stimulus_policy='approach_or_near_v1')
        self.assertEqual(a.step(frame(0, distance=.8))['stimulus'], 1)
        self.assertTrue(a.step(frame(.05, distance=.94))['approach'])
        result = a.step(frame(.1, distance=.95))
        self.assertEqual(result['stimulus'], 0)
        result = a.step(frame(.15, distance=.2))
        self.assertEqual([e['kind'] for e in result['events']], ['near'])
        self.assertTrue(a.step(frame(.2, distance=.279))['near'])
        self.assertFalse(a.step(frame(.25, distance=.28))['near'])

    def test_fresh_no_target_is_absence_not_invalid_and_clears_after_half_second(self):
        a = bridge.InputAdapter()
        a.step(frame(0, distance=.15))
        first = a.step(frame(.05, kind='no_target', distance=None))
        self.assertEqual(first['fault'], False)
        self.assertTrue(first['near'])
        self.assertTrue(a.step(frame(.5, kind='no_target', distance=None))['near'])
        result = a.step(frame(.55, kind='no_target', distance=None))
        self.assertFalse(result['near'])
        self.assertEqual(result['stimulus'], 0)
        self.assertEqual([e['kind'] for e in result['events']], ['clear'])
        self.assertIsNone(result['distance_m'])

    def test_invalid_and_stale_are_fault_not_false_far(self):
        for bad in (frame(.2, sampled=0), frame(0, distance=float('nan')), frame(0, kind='error', distance=None)):
            result = bridge.InputAdapter().step(bad)
            self.assertIsNone(result['stimulus'])
            self.assertTrue(result['fault'])
            self.assertEqual(result['events'][0]['kind'], 'fault')

    def test_out_of_order_time_rejected(self):
        a = bridge.InputAdapter();a.step(frame(1))
        with self.assertRaises(ValueError):a.step(frame(.5))

    def test_negative_sample_time_and_persistent_fault_do_not_create_sleep(self):
        result=bridge.InputAdapter().step(frame(0,sampled=-.05))
        self.assertTrue(result['fault'])
        adapter=bridge.InputAdapter();emotion=bridge.EmotionAdapter()
        for k in range(300):
            result=emotion.step(adapter.step(frame(k*.05,kind='error',distance=None)))
        self.assertEqual(result['emotion'],'normal')

    def test_near_after_angry_timeout_then_clear_returns_normal(self):
        adapter=bridge.InputAdapter();emotion=bridge.EmotionAdapter();states={}
        for k in range(151):
            t=k*.05;touch=any(a<=t<a+.2 for a in (.2,.6,1.))
            states[k]=emotion.step(adapter.step(frame(t,touch=touch,distance=.15 if 1.5<=t<7 else 1.2)))['emotion']
        self.assertEqual(states[120],'angry')
        self.assertEqual(states[130],'afraid')
        self.assertEqual(states[145],'normal')

    def test_fault_clears_deferred_near_before_later_angry(self):
        adapter=bridge.InputAdapter();emotion=bridge.EmotionAdapter();states={}
        for k in range(161):
            t=k*.05;touch=any(a<=t<a+.2 for a in (1.,1.4,1.8))
            f=frame(t,touch=touch,distance=.15 if t<.1 else 1.2)
            if k==2:f=frame(t,kind='error',distance=None)
            states[k]=emotion.step(adapter.step(f))['emotion']
        self.assertIn('angry',states.values())
        self.assertNotIn('afraid',[v for k,v in states.items() if k>=2])

    def test_delayed_input_preserves_acquisition_source_time(self):
        a=bridge.InputAdapter()
        a.step(frame(1.,touch=True,sampled=.9))
        result=a.step(frame(1.1,touch=True,sampled=1.))
        self.assertAlmostEqual(result['events'][0]['source_s'],.9)
        b=bridge.InputAdapter()
        event=b.step(frame(1.,distance=.15,sampled=.9))['events'][0]
        self.assertAlmostEqual(event['source_s'],.9)

    def test_delayed_first_press_does_not_compress_two_second_burst_window(self):
        adapter=bridge.InputAdapter();emotion=bridge.EmotionAdapter()
        samples=[(.1,0.,True),(.2,.1,True),(.4,.4,False),(.5,.5,False),
                 (1.1,1.1,True),(1.2,1.2,True),(1.4,1.4,False),(1.5,1.5,False),
                 (2.05,2.05,True),(2.15,2.15,True)]
        states=[emotion.step(adapter.step(frame(t,sampled=s,touch=touch)))['emotion'] for t,s,touch in samples]
        self.assertNotIn('angry',states)

    def test_button_touch_and_approach_use_or_not_unbounded_sum(self):
        a=bridge.InputAdapter()
        a.step(frame(0,button=True,touch=True,distance=.5))
        self.assertEqual(a.step(frame(.1,button=True,touch=True,distance=.5))['stimulus'],1)

    def test_three_presses_enter_angry_and_near_is_deferred(self):
        adapter=bridge.InputAdapter();emotion=bridge.EmotionAdapter()
        last=None
        for k in range(81):
            t=k*.05
            touched=any(a<=t<a+.2 for a in (.2,.6,1.))
            distance=.15 if t>=1.5 else 1.2
            last=emotion.step(adapter.step(frame(t,touch=touched,distance=distance)))
            if 1.2<=t<4:self.assertEqual(last['emotion'],'angry')

    def test_c0_c1_input_and_fsm_states_are_identical(self):
        frames=bridge.scenario(41)
        self.assertEqual(len(frames),12000)
        inputs=bridge.process_inputs(frames)
        self.assertEqual(len(inputs),12000)
        states={r['emotion'] for r in inputs}
        self.assertEqual(states,{'normal','interested','happy','angry','afraid','sleepy'})
        c0=model.simulate_samples('C0',[r['stimulus'] for r in inputs])
        c1=model.simulate_samples('C1',[r['stimulus'] for r in inputs])
        self.assertEqual(len(c0),12001)
        self.assertEqual([r['stimulus'] for r in c0],[r['stimulus'] for r in c1])
        self.assertNotEqual([r['phi_rad_per_update'] for r in c0],[r['phi_rad_per_update'] for r in c1])

    def test_paired_scenario_replay_and_seed_scope(self):
        self.assertEqual(bridge.scenario(41),bridge.scenario(41))
        self.assertNotEqual(bridge.scenario(41),bridge.scenario(42))

    def test_general_simulator_preserves_original_step_results(self):
        values=[float(200<=k<400) for k in range(600)]
        for condition in ('C0','C1'):
            self.assertEqual(model.simulate(condition),model.simulate_samples(condition,values))


class PackageTests(unittest.TestCase):
    def test_pair_export_records_real_duration_and_rejects_overwrite(self):
        from bio_inspire.experiments import run_ahm_input_compare as runner
        with tempfile.TemporaryDirectory(dir=model.ROOT/'bio_inspire/experiments') as tmp:
            out=Path(tmp)/'results'
            runner.run_experiment(out,seeds=(41,),make_plots=False)
            verification=json.loads((out/'verification.json').read_text())
            self.assertTrue(verification['paired_input_and_fsm_identical'])
            self.assertTrue(verification['protected_files_unchanged'])
            self.assertEqual(verification['states_observed'],['afraid','angry','happy','interested','normal','sleepy'])
            self.assertEqual(verification['input_intervals_per_seed'],12000)
            self.assertFalse(verification['physical_robot_tested'])
            with self.assertRaises(FileExistsError):runner.run_experiment(out,seeds=(41,),make_plots=False)


if __name__=='__main__':unittest.main()
