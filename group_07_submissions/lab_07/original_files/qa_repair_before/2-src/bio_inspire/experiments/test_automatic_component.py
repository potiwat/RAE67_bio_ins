import unittest
from .automatic_component import inputs_for,component,select_duration,STATES,filming_plan,verify_pair

class Tests(unittest.TestCase):
    def test_same_source_and_matching_initials_for_both_conditions(self):
        inputs=inputs_for('normal',45.)
        a=component('normal','C0',45.);b=component('normal','C1',45.)
        self.assertEqual(a['input_sha256'],b['input_sha256'])
        self.assertEqual(a['initial'],b['initial'])
        self.assertEqual(len(inputs),1200)
        self.assertEqual({v['stimulus'] for v in inputs},{0.,1.})
        self.assertEqual(a['metrics']['period_count']-1,a['metrics']['delta_t_count'])
        verify_pair(a,b)
        b['input_sha256']='changed'
        with self.assertRaisesRegex(ValueError,'input_sha256'):verify_pair(a,b)
    def test_duration_selection_has_enough_periods_for_all_states(self):
        duration,checks=select_duration()
        self.assertIn(duration,(30.,40.,45.,50.,60.))
        self.assertTrue(all(r['period_count']>=4 and r['delta_t_count']>=3 for r in checks))
        self.assertEqual({r['state'] for r in checks},set(STATES))
    def test_invalid_duration_or_state_rejected(self):
        for state,duration in [('bad',45.),('normal',0.),('normal',601.)]:
            with self.assertRaises(ValueError):inputs_for(state,duration)
    def test_filming_plan_does_not_drop_the_human_worksheet_trials(self):
        p=filming_plan(45.)
        self.assertEqual(p['human_trials'],6)
        self.assertEqual(p['human_seconds_per_trial'],600)
        self.assertEqual(p['component_trials'],6)
        self.assertEqual(p['component_seconds_per_trial'],360)
        self.assertEqual(p['total_hardware_minutes'],96.)

if __name__=='__main__':unittest.main()
