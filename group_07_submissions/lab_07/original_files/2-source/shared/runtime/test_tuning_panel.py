import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from tuning_panel import TuningPanel

class CV:
    EVENT_LBUTTONDOWN=1
    def __init__(self):self.positions={};self.callback=None
    def createTrackbar(self,n,w,v,hi,fn):self.positions[n]=v
    def setTrackbarMin(self,*a):pass
    def getTrackbarPos(self,n,w):return self.positions[n]
    def setTrackbarPos(self,n,w,v):self.positions[n]=v
    def setMouseCallback(self,w,fn):self.callback=fn

class Motor:
    def __init__(self):self.calls=[]
    def request_tuning(self,v):self.calls.append(('apply',v))
    def key(self,k):self.calls.append(('key',k))

class Tests(unittest.TestCase):
    def test_slider_changes_only_stage_and_apply_is_explicit(self):
        cv=CV();p=TuningPanel(cv,'test');m=Motor()
        cv.positions[p.labels['p']]=12;p.dispatch(-1,m)
        self.assertEqual(m.calls,[])
        p.dispatch(ord('a'),m)
        self.assertEqual(m.calls[0][1]['p'],12)
    def test_pitch_panel_restores_pitch_baseline_and_rejects_base_speed(self):
        cv=CV();p=TuningPanel(cv,'test',target_id=5);m=Motor()
        p.dispatch(ord('v'),m)
        self.assertEqual(m.calls[-1],('apply',dict(p=32,i=0,d=32,speed=1)))
        cv.positions[p.labels['speed']]=2
        with self.assertRaises(ValueError):p.values()

    def test_manual_panel_apply_carries_selected_joint_even_during_switch(self):
        cv=CV();p=TuningPanel(cv,'test',target_id=5)
        class JointMotor(Motor):
            joint_mode=True
            def request_joint_tuning(self,sid,values):self.calls.append((sid,values))
        m=JointMotor();p.select_joint(3,dict(p=24,i=0,d=32,speed=1))
        p.dispatch(ord('a'),m)
        self.assertEqual(m.calls,[(3,dict(p=24,i=0,d=32,speed=1))])

    def test_restore_uses_known_baseline_and_hold_does_not_apply(self):
        cv=CV();p=TuningPanel(cv,'test');m=Motor()
        cv.callback(cv.EVENT_LBUTTONDOWN,500,450,0,None);p.dispatch(-1,m)
        self.assertEqual(m.calls,[('key',ord('h'))])
        p.dispatch(ord('v'),m)
        self.assertEqual(m.calls[-1],('apply',dict(p=16,i=0,d=32,speed=4)))

if __name__=='__main__':unittest.main()
