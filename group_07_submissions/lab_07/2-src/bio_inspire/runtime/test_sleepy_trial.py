import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'shared'/'runtime'))
from test_normal_gaze_motor import Bus,NORMAL,ORIGIN
from normal_gaze_motor import NormalGaze
from sleepy_trial import set_sleepy_trial,set_interested_trial

class Tests(unittest.TestCase):
    def test_body_rhythm_motion_does_not_block_sleepy_head_entry(self):
        b=Bus();c=NormalGaze(b,ORIGIN,NORMAL,manual_tuning=True,tracking_speed=100,tracking_acceleration=3,yaw_range_deg=10,pitch_probe=True,pitch_tracking=True,pitch_range_deg=6,motion_speed=100)
        c.start(0);b.pos=dict(NORMAL)
        for t in (1,2,3):c.tick(t)
        snapshot=b.snapshot
        def moving_body():
            rows=snapshot();rows[1]['speed_raw']=1;rows[1]['moving_raw']=1;return rows
        b.snapshot=moving_body;b.calls.clear();set_sleepy_trial(c,True)
        self.assertEqual(b.reg[5][42],2901)
        self.assertFalse(any(i in (2,3) for i,a,v in b.calls))

    def test_interested_moves_only_roll_then_returns_and_keeps_path_guard(self):
        b=Bus();c=NormalGaze(b,ORIGIN,NORMAL,manual_tuning=True,tracking_speed=100,tracking_acceleration=3,yaw_range_deg=10,pitch_probe=True,pitch_tracking=True,pitch_range_deg=6,motion_speed=100)
        c.start(0);b.pos=dict(NORMAL)
        for t in (1,2,3):c.tick(t)
        b.calls.clear();set_interested_trial(c,True)
        self.assertEqual(b.calls,[(4,46,100),(4,41,1),(4,42,2054)])
        b.pos[4]=2054
        for t in (4,5,6):c.tick(t)
        self.assertEqual(b.reg[4][42],1940)
        b.pos[4]=1940
        for t in (7,8,9):c.tick(t)
        self.assertEqual(b.reg[4][42],2054)
        b.calls.clear();set_interested_trial(c,False)
        self.assertEqual(b.calls,[(4,46,100),(4,41,1),(4,42,1997)])
        c.tick(10);self.assertEqual(c.state,'READY')
        b.pos[4]=1997;c.tick(11)
        self.assertEqual(c.behavior_joint_windows,{})
        self.assertIsNone(c.behavior_sweep)
        set_interested_trial(c,True);c.hold('operator stop',all_axes=True)
        self.assertIsNone(c.behavior_sweep)

    def test_sleepy_only_moves_head_and_restore_uses_normal_speed(self):
        b=Bus();c=NormalGaze(b,ORIGIN,NORMAL,manual_tuning=True,tracking_speed=100,tracking_acceleration=3,yaw_range_deg=10,pitch_probe=True,pitch_tracking=True,pitch_range_deg=6,motion_speed=100)
        c.start(0);b.pos=dict(NORMAL)
        for t in (1,2,3):c.tick(t)
        b.calls.clear();set_sleepy_trial(c,True)
        self.assertEqual(b.calls,[(5,46,25),(5,41,1),(5,42,2901)])
        self.assertEqual(c.last_pitch_goal,2901)
        self.assertEqual(c.pitch_window,(2628,2764))
        b.pos[5]=2901;c.tick(4);self.assertEqual(c.state,'READY')
        b.calls.clear();set_sleepy_trial(c,False)
        self.assertEqual(b.calls,[(5,46,100),(5,41,1),(5,42,2696)])
        c.tick(5);self.assertEqual(c.state,'READY')
        b.pos[5]=2696;c.tick(6)
        self.assertIsNone(c.behavior_pitch_window)
        self.assertEqual(b.windows[5],c.pitch_window)

    def test_block_before_writes_when_not_ready_or_moving(self):
        b=Bus();c=NormalGaze(b,ORIGIN,NORMAL)
        with self.assertRaises(RuntimeError):set_sleepy_trial(c,True)
        self.assertEqual(b.calls,[])
