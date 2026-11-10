import unittest
from dataclasses import replace
from bio_inspire.experiments.ahm_input_bridge import InputFrame, InputAdapter


class FreshnessTests(unittest.TestCase):
    def test_sampler_accepted_short_presses_are_not_debounced_twice(self):
        a=InputAdapter()
        f=InputFrame(1.,1.,True,False,'range',1.2,'buffered',digital_predebounced=True,button_events=(.92,))
        r=a.step(f)
        self.assertEqual([e['kind'] for e in r['events']],['button'])
        self.assertAlmostEqual(r['events'][0]['source_s'],.92)
        r=a.step(InputFrame(1.05,1.05,False,False,'range',1.2,'released',digital_predebounced=True))
        self.assertEqual(r['stimulus'],0.)

    def test_duplicate_buffered_press_is_rejected(self):
        a=InputAdapter()
        a.step(InputFrame(1.,1.,False,True,'range',1.2,'a',digital_predebounced=True,touch_events=(.9,)))
        with self.assertRaises(ValueError):
            a.step(InputFrame(1.05,1.05,False,True,'range',1.2,'b',digital_predebounced=True,touch_events=(.9,)))

    def test_buffered_three_presses_trigger_angry_with_original_source_times(self):
        from bio_inspire.experiments.ahm_input_bridge import EmotionAdapter
        adapter=InputAdapter();emotion=EmotionAdapter()
        for t,stamp in ((1.,.92),(1.3,1.22),(1.6,1.52)):
            r=emotion.step(adapter.step(InputFrame(t,t,False,True,'range',1.2,str(t),digital_predebounced=True,touch_events=(stamp,))))
        self.assertEqual(r['emotion'],'angry')
    def test_valid_close_or_minclip_range_is_near_not_fault(self):
        for distance in (0.,.006,.019):
            row=InputAdapter().step(InputFrame(1.,1.,False,False,'range',distance,'minclip'))
            self.assertFalse(row['fault'])
            self.assertTrue(row['near'])
            self.assertEqual(row['stimulus'],1.)
    def test_old_tof_is_not_refreshed_by_new_digital_sample(self):
        f=InputFrame(1.,1.,False,False,'range',.5,'f1',distance_sample_s=.5)
        self.assertTrue(InputAdapter().step(f)['fault'])

    def test_press_source_uses_own_channel_timestamp(self):
        a=InputAdapter()
        a.step(InputFrame(1.,1.,True,False,'range',1.2,'f1',button_sample_s=.9))
        r=a.step(InputFrame(1.1,1.1,True,False,'range',1.2,'f2',button_sample_s=1.05))
        self.assertAlmostEqual(r['events'][0]['source_s'],.9)


class RecordedTests(unittest.TestCase):
    def test_capture_frames_preserve_actual_freshness_without_grid_artifacts(self):
        from bio_inspire.experiments.recorded_input_ros import capture_frames
        rows=[dict(time_s=t,button=False,touch=False,distance_kind='range',distance_m=1.2,
                   button_sample_s=t,touch_sample_s=t,distance_sample_s=t-.1,source_id=str(k))
              for k,t in enumerate((100.,100.0501,100.1002,100.15))]
        frames=capture_frames(rows)
        self.assertEqual(len(frames),4)
        self.assertEqual([f.source_id for f in frames],['0','1','2','3'])
        adapter=InputAdapter()
        self.assertTrue(all(not adapter.step(f)['fault'] for f in frames))
    def test_transport_must_not_accept_missing_prefix_or_false_complete_count(self):
        from bio_inspire.experiments.recorded_input_ros import SequenceGuard
        guard=SequenceGuard()
        with self.assertRaises(ValueError):guard.accept(dict(index=1))
        guard.accept(dict(index=0))
        with self.assertRaises(ValueError):guard.accept(dict(end=True,count=2))
        guard.accept(dict(end=True,count=1))
    def test_resample_is_causal_and_gap_becomes_fault(self):
        from bio_inspire.experiments.recorded_input_ros import resample_capture
        rows=[dict(time_s=100.,button=False,touch=False,distance_kind='range',distance_m=1.2,
                   button_sample_s=100.,touch_sample_s=100.,distance_sample_s=99.95,source_id='a'),
              dict(time_s=100.3,button=True,touch=False,distance_kind='no_target',distance_m=None,
                   button_sample_s=100.3,touch_sample_s=100.3,distance_sample_s=100.3,source_id='b')]
        frames=resample_capture(rows)
        self.assertEqual(frames[0].source_id,'awaiting_first_sample')
        self.assertFalse(any(f.button for f in frames if f.time_s<.35-1e-9))
        gap=next(f for f in frames if abs(f.time_s-.25)<1e-8)
        self.assertTrue(InputAdapter().step(gap)['fault'])
        self.assertEqual(frames[-1].distance_kind,'no_target')

    def test_incremental_teacher_model_matches_batch(self):
        from bio_inspire.experiments.recorded_input_ros import CPGPair
        from bio_inspire.experiments.ahm_cpg_compare import simulate_samples
        values=[0.]*20+[1.]*30+[None]+[0.]*20
        pair=CPGPair()
        results=[pair.step(s) for s in values]
        for c in ('C0','C1'):
            expected=simulate_samples(c,values)[:-1]
            self.assertEqual([r[c] for r in results],expected)


if __name__=='__main__':unittest.main()
