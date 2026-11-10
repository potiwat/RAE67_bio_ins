import unittest
from .scripted_batch import simulate_pair

class Tests(unittest.TestCase):
    def test_six_state_matched_600s_pair_is_deterministic_and_has_decay(self):
        a,b=simulate_pair('P1')
        self.assertEqual(len(a),12000);self.assertEqual(len(b),12000)
        self.assertEqual({r['state'] for r in a},{'normal','interested','happy','angry','afraid','sleepy'})
        for x,y in zip(a,b):
            self.assertEqual(x['stimulus'],y['stimulus']);self.assertEqual(x['state'],y['state'])
            self.assertEqual(x['h'],y['h'])
        self.assertTrue(any(r['stimulus']==0. and r['h']>.1 for r in b))
        self.assertEqual(a[0]['o1'],b[0]['o1']);self.assertEqual(a[0]['o2'],b[0]['o2'])
        self.assertLessEqual(max(r['time_s'] for r in a if r['state']=='angry' and r['time_s']<120),120)
