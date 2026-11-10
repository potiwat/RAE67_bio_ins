import json
from pathlib import Path
import tempfile
import unittest
from joint_motion_log import JointMotionLog

class Tests(unittest.TestCase):
    def test_records_overshoot_and_signed_final_error_without_claiming_smoothness(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            p=Path(folder)/'motion.json';m=JointMotionLog(p)
            m.begin(2,100,110,dict(p=32,i=0,d=22),0)
            for t,pos in [(0.1,104),(0.2,112),(0.3,111),(1.4,111)]:
                m.sample(t,dict(position_raw=pos,speed_raw=0,moving_raw=0),False,'READY',110)
            self.assertFalse(p.exists())
            m.sample(4.,dict(position_raw=114,speed_raw=1,moving_raw=1),False,'READY',110)
            m.sample(4.2,dict(position_raw=111,speed_raw=0,moving_raw=0),False,'READY',110)
            m.sample(12.3,dict(position_raw=111,speed_raw=0,moving_raw=0),False,'READY',110)
            d=json.loads(p.read_text())['history'][-1]
            self.assertEqual(d['overshoot_ticks'],4);self.assertEqual(d['final_error_ticks'],1)
            self.assertEqual(d['reason'],'stationary');self.assertNotIn('smooth',d)

    def test_new_goal_marks_previous_as_interrupted_and_history_is_bounded(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            m=JointMotionLog(Path(folder)/'motion.json')
            for n in range(10):m.begin(2,100,110,{},n)
            self.assertEqual(len(m.history),6)
            self.assertTrue(all(r['reason']=='replaced' for r in m.history))
