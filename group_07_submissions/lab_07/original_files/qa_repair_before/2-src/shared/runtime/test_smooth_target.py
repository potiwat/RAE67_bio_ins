import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from smooth_target import SmoothTarget


class SmoothTests(unittest.TestCase):
    def test_lab02_filter_does_not_jump_to_raw_face_target(self):
        s=SmoothTarget(.25,100);s.reset(0,0)
        self.assertEqual(s.update(20,1),5)
        self.assertEqual(s.update(20,2),8.75)
    def test_lab06_step_limits_change_using_elapsed_time(self):
        s=SmoothTarget(1,10);s.reset(0,0)
        self.assertEqual(s.update(100,.1),1)
        self.assertEqual(s.update(-100,.2),0)


if __name__=='__main__':unittest.main()
