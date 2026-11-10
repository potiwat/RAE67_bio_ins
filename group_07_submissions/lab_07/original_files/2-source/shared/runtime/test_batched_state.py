import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from normal_gaze_motor import decode_state


class StateTests(unittest.TestCase):
    def test_memory_offsets_keep_mode_torque_feedback_and_status_distinct(self):
        b=bytearray(34);b[0]=0;b[7]=1;b[8]=1
        b[9:11]=(2019).to_bytes(2,'little');b[13:15]=(400).to_bytes(2,'little')
        b[23:25]=b'\xe3\x07';b[25:27]=b'\x00\x00';b[27:29]=b'\x03\x00'
        b[29]=72;b[30]=35;b[32]=4;b[33]=1
        r=decode_state(1,b)
        self.assertEqual((r['position_raw'],r['torque_raw'],r['status_raw'],r['moving_raw']),(2019,1,4,1))
        self.assertEqual((r['voltage_V'],r['temperature_C']),(7.2,35))
        self.assertEqual((r['goal_raw'],r['target_speed_raw'],r['acceleration_raw']),(2019,400,1))
    def test_short_reply_is_not_treated_as_good_status(self):
        with self.assertRaises(ValueError):decode_state(1,bytes(33))


if __name__=='__main__':unittest.main()
