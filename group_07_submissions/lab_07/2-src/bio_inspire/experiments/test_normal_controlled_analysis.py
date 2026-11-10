import unittest
from bio_inspire.experiments.normal_controlled_analysis import cpg_samples, verify_pair


class Tests(unittest.TestCase):
    def test_cpg_timestamps_use_model_index_not_late_logger_receipt(self):
        rows=[dict(elapsed_s=99.,rhythm=dict(updates=k,dt_s=.05,time_scale=.5,o1=v))
              for k,v in ((0,-1.),(1,0.),(1,0.),(3,1.))]
        samples,missing=cpg_samples(rows)
        self.assertEqual(samples,[(0.,-1.),(.1,0.),(.30000000000000004,1.)])
        self.assertEqual(missing,1)

    def test_pair_requires_same_nominal_input_completed_and_initial_state(self):
        common=dict(completed=True,nominal_input={'samples':[0,1]},common_initial_o1=.1,
                    common_initial_o2=.2,cpg_dt_s=.05,cpg_time_scale=.5,amplitude_deg_limit=2.)
        a={**common,'condition':'C0'};b={**common,'condition':'C1'}
        verify_pair(a,b)
        for changed in (dict(completed=False),dict(nominal_input={'samples':[1,0]}),dict(common_initial_o1=.2)):
            with self.assertRaises(ValueError):verify_pair(a,{**b,**changed})

    def test_cpg_index_must_not_reverse(self):
        rows=[dict(rhythm=dict(updates=k,dt_s=.05,time_scale=.5,o1=0.)) for k in (1,0)]
        with self.assertRaises(ValueError):cpg_samples(rows)
