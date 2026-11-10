import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from manual_tuning import validate_values,apply_values,DEFAULTS,trajectory_speed_limit

class Bus:
    def __init__(self):self.pid=bytes((16,32,0));self.speed=4;self.calls=[];self.lock=1
    def read(self,i,a,n):
        if a==55:return bytes((self.lock,))
        if a==21:return self.pid
        if a==42:return (2019).to_bytes(2,'little')
        if a==46:return self.speed.to_bytes(2,'little')
        if a==41:return b'\3'
        raise AssertionError((i,a,n))
    def write(self,i,a,d):
        self.calls.append((i,a,bytes(d)))
        if a==21:self.pid=bytes(d)
        if a==46:self.speed=int.from_bytes(d,'little')

class Tests(unittest.TestCase):
    def test_bounds_and_only_integers(self):
        self.assertEqual(validate_values(dict(p=8,i=2,d=48,speed=100))['speed'],100)
        for field,value in [('p',7),('p',33),('i',3),('d',49),('speed',101),('speed',0),('p',True)]:
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):
                validate_values(dict(DEFAULTS,**{field:value}))
    def test_pid_is_p_d_i_in_one_write_and_only_id1_changes(self):
        b=Bus();r=apply_values(b,dict(p=12,i=1,d=40,speed=6))
        self.assertEqual(b.calls,[(1,21,bytes((12,40,1))),(1,46,bytes((6,0)))])
        self.assertEqual(r,dict(p=12,i=1,d=40,speed=6))
    def test_unlocked_bus_never_writes(self):
        b=Bus();b.lock=0
        with self.assertRaises(RuntimeError):apply_values(b,DEFAULTS)
        self.assertEqual(b.calls,[])
    def test_readback_mismatch_does_not_report_applied(self):
        b=Bus();b.write=lambda *a:None
        with self.assertRaises(RuntimeError):apply_values(b,dict(p=8,i=0,d=16,speed=1))
    def test_manual_base_tuning_keeps_native_acceleration_one(self):
        class ManualBus(Bus):
            manual_joint_mode=True
            def read(self,i,a,n):return b'\1' if a==41 else super().read(i,a,n)
        b=ManualBus();b.speed=1
        apply_values(b,dict(p=24,i=0,d=32,speed=1),sid=1)
        self.assertEqual(b.calls,[(1,21,bytes((24,32,0)))])

    def test_extended_raw_servo_limit_does_not_multiply_host_trajectory_ceiling(self):
        self.assertAlmostEqual(trajectory_speed_limit(7),7*.732*6*4096/360)
        self.assertEqual(trajectory_speed_limit(100),trajectory_speed_limit(8))

class PitchTuningTests(unittest.TestCase):
    def test_manual_joint_bounds_are_supported_for_2_to_5_only(self):
        from manual_tuning import bounds_for,defaults_for
        for sid in (2,3,4,5):
            self.assertEqual(validate_values(dict(p=1,i=8,d=64,speed=1),sid=sid)['p'],1)
            self.assertEqual(defaults_for(sid),dict(p=32,i=0,d=32,speed=1))
        with self.assertRaises(ValueError):bounds_for(6)

    def test_wider_pitch_pid_bounds_keep_speed_fixed_and_base_bounds_unchanged(self):
        for values in [dict(p=1,i=8,d=0,speed=1),dict(p=64,i=0,d=64,speed=1)]:
            self.assertEqual(validate_values(values,sid=5),values)
        for field,value in [('p',0),('p',65),('i',9),('d',65),('speed',2)]:
            with self.assertRaises(ValueError):validate_values(dict(p=16,i=0,d=16,speed=1,**{})|{field:value},sid=5)
        with self.assertRaises(ValueError):validate_values(dict(p=1,i=0,d=0,speed=1),sid=1)

    def test_id5_writes_pid_only_at_fixed_speed_acceleration(self):
        class PitchBus(Bus):
            def read(self,i,a,n):
                if i!=5:raise AssertionError('wrong joint')
                if a==41:return b'\1'
                return super().read(i,a,n)
            def write(self,i,a,d):
                if i!=5:raise AssertionError('wrong joint')
                return super().write(i,a,d)
        b=PitchBus();b.pid=bytes((32,32,0));b.speed=1
        actual=apply_values(b,dict(p=24,i=0,d=40,speed=1),sid=5)
        self.assertEqual(actual,dict(p=24,i=0,d=40,speed=1))
        self.assertEqual(b.calls,[(5,21,bytes((24,40,0)))])
        for values in [dict(p=0,i=0,d=32,speed=1),dict(p=24,i=0,d=32,speed=2)]:
            with self.assertRaises(ValueError):apply_values(b,values,sid=5)

class GroupPIDTests(unittest.TestCase):
    def bus(self):
        from test_normal_gaze_motor import Bus as JointBus
        b=JointBus()
        for r in b.reg.values():r[21]=int.from_bytes(bytes((32,32,0)),'little');r[55]=1
        return b
    def test_base_startup_restores_only_approved_pid_without_speed_or_goal_writes(self):
        from manual_tuning import ensure_base_pid
        b=self.bus();ensure_base_pid(b)
        self.assertEqual(b.calls,[(1,21,int.from_bytes(bytes((8,16,1)),'little'))])
        b.calls.clear();b.torque={i:1 for i in b.torque}
        ensure_base_pid(b);self.assertEqual(b.calls,[])
    def test_base_restore_refuses_changed_gains_while_loaded(self):
        from manual_tuning import ensure_base_pid
        b=self.bus();b.torque={i:1 for i in b.torque}
        with self.assertRaises(RuntimeError):ensure_base_pid(b)
        self.assertEqual(b.calls,[])

    def test_cold_group_trial_reads_back_all_and_does_not_move_or_enable(self):
        from manual_tuning import apply_group_pid_trial
        b=self.bus();result=apply_group_pid_trial(b)
        self.assertEqual(result['before']['2'],[32,32,0])
        self.assertEqual(result['after']['5'],[8,16,1])
        self.assertEqual(b.calls,[(i,21,int.from_bytes(bytes((8,16,1)),'little')) for i in range(1,6)])
    def test_any_unlocked_or_enabled_joint_blocks_entire_trial(self):
        from manual_tuning import apply_group_pid_trial
        for bad in ('lock','torque'):
            b=self.bus()
            if bad=='lock':b.reg[5][55]=0
            else:b.torque[2]=1
            with self.assertRaises(RuntimeError):apply_group_pid_trial(b)
            self.assertEqual(b.calls,[])

if __name__=='__main__':unittest.main()
