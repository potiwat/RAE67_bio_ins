import unittest
from types import SimpleNamespace
from sync_position_writer import PositionSyncWriter, SyncPositionError, position_packet

class Port:
    def __init__(self):self.packets=[];self.short=False
    def reset_input_buffer(self):pass
    def write(self,p):self.packets.append(p);return len(p)-(1 if self.short else 0)
    def flush(self):pass
class Bus:
    sync_position_trial=True
    def __init__(self):
        self.port=Port();self.windows={1:(1985,2053),2:(2803,2871),3:(2712,2780)};self.reads=[];self.bad=False
    def read(self,i,a,n):
        self.reads.append((i,a,n))
        p=self.port.packets[-1];start=7+(i-1)*3
        return b'xx' if self.bad else p[start+1:start+3]
class Tests(unittest.TestCase):
    def test_four_axis_frame_requires_separate_opt_in_and_verifies_all_four(self):
        b=Bus();b.windows[4]=(1600,2400);goals={**self.goals,4:1997}
        with self.assertRaises(ValueError):PositionSyncWriter().commit(b,goals,lambda:False)
        self.assertFalse(b.port.packets)
        b.sync_roll_position_trial=True
        report=PositionSyncWriter().commit(b,goals,lambda:False)
        self.assertEqual(report['verified_ids'],[1,2,3,4])
        self.assertEqual(len(b.port.packets[0]),20)
        self.assertEqual(sum(b.port.packets[0][2:])&255,255)
        self.assertEqual(b.reads,[(i,42,2) for i in (1,2,3,4)])

    def test_fourth_readback_failure_latches_without_retry(self):
        b=Bus();b.windows[4]=(1600,2400);b.sync_roll_position_trial=True
        read=b.read;b.read=lambda i,a,n:b'xx' if i==4 else read(i,a,n)
        writer=PositionSyncWriter();goals={**self.goals,4:1997}
        with self.assertRaises(SyncPositionError):writer.commit(b,goals,lambda:False)
        self.assertEqual(writer.last_report['verified_ids'],[1,2,3])
        with self.assertRaises(SyncPositionError):writer.commit(b,goals,lambda:False)
        self.assertEqual(len(b.port.packets),1)

    goals={1:2019,2:2837,3:2746}
    def test_packet_only_42_two_bytes_little_endian_ids123(self):
        p=position_packet(self.goals)
        self.assertEqual(p[:7],bytes((255,255,254,13,131,42,2)))
        self.assertEqual(p[7:-1],bytes((1,227,7,2,21,11,3,186,10)))
        self.assertEqual(sum(p[2:])&255,255);self.assertEqual(len(p),17)
    def test_one_packet_and_three_readbacks_without_write_ack_wait(self):
        b=Bus();w=PositionSyncWriter();report=w.commit(b,self.goals,lambda:False)
        self.assertEqual(len(b.port.packets),1)
        self.assertEqual(b.reads,[(1,42,2),(2,42,2),(3,42,2)])
        self.assertEqual(report['verified_ids'],[1,2,3]);self.assertEqual(report['status'],'goal_readback_verified')
    def test_invalid_or_disabled_frame_never_touches_bus(self):
        for goals in ({1:2019,2:2837,3:4096},{1:True,2:2837,3:2746},{1:2019,2:2837},{1:2019,2:2837,3:2800}):
            b=Bus()
            with self.assertRaises(ValueError):PositionSyncWriter().commit(b,goals,lambda:False)
            self.assertEqual(b.port.packets,[]);self.assertEqual(b.reads,[])
        b=Bus();b.sync_position_trial=False
        with self.assertRaises(ValueError):PositionSyncWriter().commit(b,self.goals,lambda:False)
        self.assertEqual(b.port.packets,[])
    def test_failure_latches_and_never_retries_on_same_owner(self):
        for kind in ('bad_readback','short_write'):
            b=Bus();w=PositionSyncWriter();b.bad=kind=='bad_readback';b.port.short=kind=='short_write'
            with self.assertRaises(SyncPositionError):w.commit(b,self.goals,lambda:False)
            count=len(b.port.packets)
            b.bad=b.port.short=False
            with self.assertRaises(SyncPositionError):w.commit(b,self.goals,lambda:False)
            self.assertEqual(len(b.port.packets),count)
    def test_stop_before_send_and_between_readbacks(self):
        b=Bus();w=PositionSyncWriter()
        with self.assertRaises(SyncPositionError):w.commit(b,self.goals,lambda:True)
        self.assertEqual(b.port.packets,[])
        b=Bus();w=PositionSyncWriter()
        with self.assertRaises(SyncPositionError):w.commit(b,self.goals,lambda:len(b.reads)>0)
        self.assertEqual(len(b.reads),1);self.assertTrue(w.blocked)
    def test_freezes_requested_mapping_before_io(self):
        b=Bus();w=PositionSyncWriter();goals=dict(self.goals);original=b.port.write
        def write(p):
            goals[2]=4095;return original(p)
        b.port.write=write
        report=w.commit(b,goals,lambda:False)
        self.assertEqual(report['requested_goals'][2],2837)

    def test_stop_during_input_reset_prevents_transmission(self):
        b=Bus();w=PositionSyncWriter();stop=[False]
        b.port.reset_input_buffer=lambda:stop.__setitem__(0,True)
        with self.assertRaises(SyncPositionError):w.commit(b,self.goals,lambda:stop[0])
        self.assertEqual(b.port.packets,[]);self.assertEqual(b.reads,[])
