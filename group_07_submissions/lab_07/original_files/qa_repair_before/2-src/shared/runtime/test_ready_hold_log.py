import json
import tempfile
import unittest
from pathlib import Path
from ready_hold_log import ReadyHoldLog


class Tests(unittest.TestCase):
    def rows(self,p=100):
        return [dict(id=i,position_raw=p if i==3 else 100,speed_raw=0,moving_raw=0,torque_raw=1,status_raw=0) for i in range(1,6)]

    def test_captures_late_motion_with_constant_goals_without_writing_hardware(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            p=Path(folder)/'hold.json';log=ReadyHoldLog(p);reads=[]
            def read_goals():reads.append(1);return {i:100 for i in range(1,6)}
            log.step(0,'NORMAL_STARTUP',False,self.rows(),read_goals)
            self.assertEqual(reads,[])
            log.step(1,'READY',False,self.rows(),read_goals)
            log.step(1.1,'READY',False,self.rows(),read_goals)
            self.assertEqual(len(reads),1)
            log.step(11,'READY',False,self.rows(106),read_goals)
            log.step(26,'READY',False,self.rows(105),read_goals)
            d=json.loads(p.read_text());self.assertEqual(d['reason'],'complete')
            self.assertEqual(d['summary']['3']['span_ticks'],6)
            self.assertEqual(d['summary']['3']['goal_values'],[100])
            self.assertEqual(d['samples'][2]['rows'][2]['position_raw'],106)

    def test_follow_or_stop_ends_observation_instead_of_calling_it_a_hold(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            p=Path(folder)/'hold.json';log=ReadyHoldLog(p)
            read=lambda:{i:100 for i in range(1,6)}
            log.step(0,'READY',False,self.rows(),read)
            log.step(1,'FOLLOWING',True,self.rows(),read)
            self.assertEqual(json.loads(p.read_text())['reason'],'interrupted')
