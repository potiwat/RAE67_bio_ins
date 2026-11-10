import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from yaw_gain_trial import change_yaw_p


class Bus:
    def __init__(self):
        self.p=32;self.lock=1;self.bad=False;self.calls=[];self.torque=1
    def read(self,i,a,n):
        if a==21:return bytes((self.p if i==1 else 32,32,0))
        if a==55:return bytes((self.lock,))
        if a==42:return (2019).to_bytes(2,'little')
        raise AssertionError((i,a,n))
    def snapshot(self):
        return [dict(id=i,position_raw=2019,mode=0,status_raw=int(self.bad),
                     torque_raw=self.torque,speed_raw=0,moving_raw=0) for i in range(1,6)]
    def write_p(self,p):self.calls.append(p);self.p=p


class GainTests(unittest.TestCase):
    def test_gain_can_be_prepared_while_all_torque_off_without_enabling(self):
        b=Bus();b.torque=0;change_yaw_p(b,16)
        self.assertEqual(b.calls,[16]);self.assertEqual(b.torque,0)

    def test_only_changes_base_p_and_can_restore(self):
        b=Bus();r=change_yaw_p(b,16)
        self.assertEqual(b.calls,[16]);self.assertEqual(r['before'][1],[32,32,0])
        self.assertEqual(r['after'][1],[16,32,0])
        self.assertTrue(all(r['before'][i]==r['after'][i] for i in range(2,6)))
        change_yaw_p(b,32);self.assertEqual(b.calls,[16,32])
    def test_refuses_fault_unlocked_or_unknown_gain_before_writing(self):
        for field,value in [('bad',True),('lock',0),('p',20)]:
            b=Bus();setattr(b,field,value)
            with self.assertRaises(RuntimeError):change_yaw_p(b,16)
            self.assertEqual(b.calls,[])
    def test_unapproved_target_rejected(self):
        b=Bus()
        with self.assertRaises(ValueError):change_yaw_p(b,24)
        self.assertEqual(b.calls,[])
    def test_readback_failure_is_not_success(self):
        b=Bus();b.write_p=lambda p:None
        with self.assertRaisesRegex(RuntimeError,'readback'):change_yaw_p(b,16)
    def test_moving_base_refused(self):
        b=Bus();snapshot=b.snapshot
        def moving():
            rows=snapshot();rows[0]['moving_raw']=1;return rows
        b.snapshot=moving
        with self.assertRaises(RuntimeError):change_yaw_p(b,16)
        self.assertEqual(b.calls,[])

if __name__=='__main__':unittest.main()
