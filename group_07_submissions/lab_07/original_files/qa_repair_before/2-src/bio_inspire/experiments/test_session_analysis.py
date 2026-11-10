import math,unittest
from .session_analysis import analyze
class Tests(unittest.TestCase):
    def rows(self):
        return [dict(time_s=i*.05,state='READY',behavior='normal',pose_phase=None,oscillator=dict(o1=math.sin(2*math.pi*i*.05),updates=i,envelope=1.)) for i in range(101)]
    def test_frequency_and_delta_are_measured_with_denominators(self):
        a=analyze(self.rows())['per_state']['normal']
        self.assertAlmostEqual(a['frequency_hz'],1.,places=5)
        self.assertGreater(a['period_count'],2)
        self.assertAlmostEqual(a['delta_t_mean_s'],0.,places=5)
    def test_mask_and_state_changes_do_not_stitch_cycles(self):
        rows=self.rows()
        for i,row in enumerate(rows):
            row['behavior']='normal' if i%20<10 else 'happy'
        a=analyze(rows)
        self.assertIsNone(a['per_state']['normal']['frequency_hz'])
        self.assertIsNone(a['per_state']['happy']['delta_t_mean_s'])
    def test_unknown_or_stopped_rows_are_excluded(self):
        rows=self.rows()
        for r in rows:r['state']='STOPPED'
        self.assertEqual(analyze(rows)['valid_samples'],0)

    def test_reset_inside_same_state_splits_episode(self):
        rows=self.rows()
        for i,r in enumerate(rows):r['oscillator']['updates']=i%20
        self.assertIsNone(analyze(rows)['per_state']['normal']['frequency_hz'])
