import unittest
from bio_inspire.experiments.all_state_compare import simulate, episode_metrics


def sample(t,state,s=0.):return dict(time_s=t,emotion=state,stimulus=s,source_id=str(t),interaction=None,fault=False)


class Tests(unittest.TestCase):
    def test_c0_c1_share_fsm_and_source_and_mapping_reaches_all_states(self):
        inputs=[sample(k*.05,state,1.) for k,state in enumerate(('normal','interested','happy','sleepy','afraid','angry'))]
        a=simulate(inputs,'C0');b=simulate(inputs,'C1')
        self.assertEqual([r['state'] for r in a],[r['state'] for r in b])
        self.assertEqual([r['source_id'] for r in a],[r['source_id'] for r in b])
        self.assertEqual(set(r['state'] for r in a),set(('normal','interested','happy','sleepy','afraid','angry')))
        self.assertTrue(all(r['phi_next']==.13 for r in a))
        self.assertEqual(b[0]['h'],0.);self.assertAlmostEqual(b[1]['h'],.04)
        self.assertTrue(all(.1<=r['phi_next']<=.13 for r in b))

    def test_state_hold_changes_analysis_state_not_shared_stimulus(self):
        inputs=[sample(k*.05,'normal',float(k>20)) for k in range(100)]
        a=simulate(inputs,'C0',hold_state='angry')
        self.assertEqual({r['state'] for r in a},{'angry'})
        self.assertEqual([r['stimulus'] for r in a],[r['stimulus'] for r in inputs])
        self.assertEqual({r['fsm_state'] for r in a},{'normal'})

    def test_metrics_never_bridge_separate_episodes_or_masked_intervals(self):
        rows=[]
        for n,state in enumerate(('normal','normal','happy','normal','normal')):
            rows.append(dict(time_s=n*.1,state=state,owner='body',o1=(-1.)**n,updates=n,dt_s=.05,time_scale=.5,envelope=1.))
        m=episode_metrics(rows)
        self.assertEqual(m['normal']['period_count'],0)
        self.assertIsNone(m['normal']['delta_t_mean_s'])

    def test_fault_masks_output_and_splits_episode(self):
        inputs=[sample(k*.05,'normal') for k in range(400)]
        inputs[200]['fault']=True
        rows=simulate(inputs,'C1')
        self.assertEqual(rows[200]['envelope'],0.)
        self.assertTrue(rows[200]['fault'])
        self.assertEqual(episode_metrics(rows)['normal']['episodes_with_full_envelope'],2)
