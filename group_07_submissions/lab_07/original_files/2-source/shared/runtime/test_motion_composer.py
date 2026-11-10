"""Reference arbitration is tested without connecting a motor."""
import unittest
from motion_composer import compose_goals

BASE={i:2000 for i in range(1,6)}
BOUNDS={i:(1900,2100) for i in BASE}

class Tests(unittest.TestCase):
    def test_bypass_preserves_pose_exactly_without_mutating_inputs(self):
        self.assertEqual(compose_goals(BASE,BOUNDS,cpg={2:40},gaze={1:30}),BASE)
        self.assertEqual(BASE,{i:2000 for i in range(1,6)})

    def test_layers_combine_once_before_bounds_check(self):
        result=compose_goals(BASE,BOUNDS,cpg={2:12.5},gaze={2:3.5},
                             cpg_enabled=True,gaze_enabled=True)
        self.assertEqual(result,{**BASE,2:2016})
        with self.assertRaises(ValueError):
            compose_goals(BASE,BOUNDS,cpg={2:80},gaze={2:30},cpg_enabled=True,gaze_enabled=True)

    def test_exclusive_action_owns_pose_and_stop_fault_produce_no_new_goal(self):
        self.assertEqual(compose_goals(BASE,BOUNDS,cpg={2:50},gaze={1:50},
                         cpg_enabled=True,gaze_enabled=True,exclusive=True),BASE)
        for state in ('FAULT','STOPPED','IDLE'):
            self.assertIsNone(compose_goals(BASE,BOUNDS,state=state))

    def test_invalid_nonfinite_partial_or_unknown_joint_rejected(self):
        for change in ({'base':{1:2000}}, {'cpg':{6:1}}, {'gaze':{1:float('nan')}},
                       {'base':{**BASE,2:float('inf')}}, {'bounds':{**BOUNDS,1:(2100,1900)}}):
            args=dict(base=BASE,bounds=BOUNDS);args.update(change)
            with self.assertRaises(ValueError):compose_goals(**args)
