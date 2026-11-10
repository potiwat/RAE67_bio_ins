import sys
from pathlib import Path
import unittest
from unittest.mock import patch
root=Path(__file__).resolve().parents[2]
parser=root/'calibration_readonly'
if not parser.is_dir():parser=root.parent/'calibration_readonly'
sys.path.insert(0,str(parser))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from read_only_bus import ReadOnlyBus
from normal_gaze_motor import open_bus

class Port:
    def __init__(self):self.writes=[];self.reg={21:bytes((16,32,0)),55:b'\1',46:b'\4\0'}
    def reset_input_buffer(self):pass
    def write(self,p):self.writes.append(p);self.reg[p[5]]=p[6:-1];return len(p)
    def flush(self):pass
    def close(self):pass

class Tests(unittest.TestCase):
    def test_awake_acceleration_guard_is_scoped_to_exact_recipe(self):
        b,p=self.make_bus();p.reg[41]=b'\1'
        with self.assertRaises(ValueError):b.write(3,41,b'\10')
        b.awake_dynamic_acceleration_trial=True
        with patch('normal_gaze_motor.receive_write_ack'):
            for sid,v in ((1,3),(2,8),(3,8),(4,12),(5,6)):b.write(sid,41,bytes((v,)))
        for sid,v in ((1,8),(2,12),(4,254),(5,12)):
            with self.assertRaises(ValueError):b.write(sid,41,bytes((v,)))
    def test_dynamic_button_acceleration_permission_is_explicit_and_exact(self):
        b,p=self.make_bus();p.reg[41]=b'\1'
        with self.assertRaises(ValueError):b.write(2,41,b'\10')
        b.button_look_dynamic_acceleration_trial=True
        with patch('normal_gaze_motor.receive_write_ack'):
            for sid,v in ((1,3),(2,8),(3,8),(4,12),(5,6)):b.write(sid,41,bytes((v,)))
        for sid,v in ((1,8),(2,12),(4,8),(5,12)):
            with self.assertRaises(ValueError):b.write(sid,41,bytes((v,)))
    def test_native_interested_speed17_is_scoped_to_opted_in_body_only(self):
        b,p=self.make_bus()
        with self.assertRaises(ValueError):b.write(2,46,(17).to_bytes(2,'little'))
        b.interested_native_body_trial=True
        with patch('normal_gaze_motor.receive_write_ack'):
            for sid in (2,3):b.write(sid,46,(17).to_bytes(2,'little'))
        for sid,value in ((1,17),(4,17),(5,17),(2,18),(3,16)):
            with self.assertRaises(ValueError):b.write(sid,46,value.to_bytes(2,'little'))
        self.assertEqual(len(p.writes),2)
    def test_gentle_interested_speed_permission_exact_and_scoped(self):
        b,p=self.make_bus()
        with self.assertRaises(ValueError):b.write(2,46,(150).to_bytes(2,'little'))
        b.interested_gentle_entry_trial=True
        with patch('normal_gaze_motor.receive_write_ack'):
            for sid,value in ((2,150),(3,150),(4,100)):b.write(sid,46,value.to_bytes(2,'little'))
        for sid,value in ((1,150),(5,100),(2,100),(4,150),(3,151)):
            with self.assertRaises(ValueError):b.write(sid,46,value.to_bytes(2,'little'))
        self.assertEqual(len(p.writes),3)
    def make_bus(self):
        port=Port()
        def init(b):b.port=port
        def response(b,p,sid,n):return b'\1' if p[5]==8 else port.reg[p[5]]
        with patch.object(ReadOnlyBus,'__init__',init),patch.object(ReadOnlyBus,'_read_response',response):
            bus=open_bus()
        bus._read_response=lambda p,sid,n:response(bus,p,sid,n)
        return bus,port
    def test_pid_and_speed_six_require_manual_mode_and_stay_unicast(self):
        b,p=self.make_bus()
        with self.assertRaises(ValueError):b.write(1,21,bytes((8,48,2)))
        with self.assertRaises(ValueError):b.write(1,46,b'\6\0')
        b.manual_tuning=True
        with patch('normal_gaze_motor.receive_write_ack'):
            b.write(1,21,bytes((8,48,2)));b.write(1,46,bytes((100,0)))
        self.assertEqual([list(x[2:6]) for x in p.writes],[[1,6,3,21],[1,5,3,46]])
        for sid,a,d in [(2,21,bytes((8,32,0))),(1,55,b'\0'),(1,21,bytes((7,32,0))),(1,46,bytes((101,0))),(2,46,b'\6\0')]:
            with self.assertRaises(ValueError):b.write(sid,a,d)
        self.assertEqual(len(p.writes),2)
    def test_group_trial_allows_only_exact_approved_pid_with_opt_in(self):
        b,p=self.make_bus();b.group_pid_trial=True
        with patch('normal_gaze_motor.receive_write_ack'):
            for sid in range(1,6):b.write(sid,21,bytes((8,16,1)))
        self.assertEqual(len(p.writes),5)
        for sid in range(1,6):
            with self.assertRaises(ValueError):b.write(sid,21,bytes((10,16,1)))
        with self.assertRaises(ValueError):b.write(5,46,bytes((100,0)))

    def test_id5_tuning_scope_cannot_change_other_joints_or_speed(self):
        b,p=self.make_bus();b.manual_tuning=True;b.tuning_id=5
        with patch('normal_gaze_motor.receive_write_ack'):b.write(5,21,bytes((24,40,0)))
        for sid,a,d in [(1,21,bytes((8,16,1))),(2,21,bytes((24,40,0))),(5,21,bytes((0,16,1))),(5,46,b'\2\0')]:
            with self.assertRaises(ValueError):b.write(sid,a,d)
        self.assertEqual(len(p.writes),1)

    def test_unlocked_pid_write_denied(self):
        b,p=self.make_bus();b.manual_tuning=True;p.reg[55]=b'\0'
        with self.assertRaises(RuntimeError):b.write(1,21,bytes((16,32,0)))
        self.assertEqual(p.writes,[])

if __name__=='__main__':unittest.main()
