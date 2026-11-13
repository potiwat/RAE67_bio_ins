import unittest,threading
from types import SimpleNamespace as NS
from unittest.mock import Mock
try:
    from shared.experiments.resistance_id1_20261109.observer import Observer,Sessions,scoped_step,label
except ImportError:Observer=Sessions=scoped_step=label=None

class Tests(unittest.TestCase):
    def test_observer_exists(self):self.assertIsNotNone(Observer,'R1 calibration observer not implemented')
    def setUp(self):
        if Observer is None and self._testMethodName!='test_observer_exists':self.skipTest('Not implemented')
    def motor(self):
        row=dict(id=1,sampled_monotonic_s=0.,mode=0,torque_raw=1,status_raw=0,position_raw=2019,goal_raw=2019,
          internal_target_raw=2019,current_raw=0,load_raw=0,speed_raw=0,moving_raw=0,target_speed_raw=600,acceleration_raw=3,voltage_V=7.1,temperature_C=30)
        rows=[{**row,'id':i} for i in range(1,6)]
        bus=NS(write=Mock(side_effect=AssertionError('Observer must never write motor')),read=Mock(side_effect=AssertionError('No competing UART reads')))
        c=NS(state='READY',last_rows=rows,normal={2:2837,3:2746},bus=bus,pose_route=None)
        m=NS(lab07_pair_id='resistance_id1_R1_baseline',behavior_trial='normal',controller=c,
          normal_measurement=NS(state='running'),operator_stopped=False,distance_gate=NS(near=False),
          stopping=threading.Event(),urgent_stop=threading.Event(),finished=threading.Event())
        d=NS(rhythm=NS(advance=Mock(),modulation_status={}),mode=None,centers=None)
        return m,d,bus
    def advance(self,p,m,t):
        for r in m.controller.last_rows:r['sampled_monotonic_s']=t
        p.observe(m,t)
    def test_complete30s_without_motor_io_and_preserve_native_rows(self):
        m,d,b=self.motor();p=Observer();initial=[dict(r) for r in m.controller.last_rows]
        for k in range(321):self.advance(p,m,k/10.)
        self.assertTrue(p.complete);self.assertEqual(len(p.samples),301)
        self.assertEqual(p.samples[-1]['elapsed_s'],30.)
        self.assertEqual(p.samples[0]['rows'],initial)
        b.write.assert_not_called();b.read.assert_not_called()
    def test_duplicate_feedback_not_counted_and_stale_rejected(self):
        m,d,b=self.motor();p=Observer();p.observe(m,0.);p.observe(m,.1)
        self.assertEqual(len(p.samples),1)
        with self.assertRaises(ValueError):p.observe(m,.3)
    def test_invalid_feedback_and_native_drift(self):
        for key,value in [('mode',1),('torque_raw',0),('status_raw',1),('position_raw',-1),('current_raw',None),('target_speed_raw',17),('acceleration_raw',1)]:
            m,d,b=self.motor();m.controller.last_rows[0][key]=value
            with self.assertRaises(ValueError):Observer().observe(m,0.)
            b.write.assert_not_called();b.read.assert_not_called()
    def test_waiting_stop_and_near_do_not_collect(self):
        for kind in ('waiting','operator','stop','urgent','near','fault','route','aborted'):
            m,d,b=self.motor()
            if kind=='waiting':m.normal_measurement.state='waiting'
            elif kind=='operator':m.operator_stopped=True
            elif kind=='stop':m.stopping.set()
            elif kind=='urgent':m.urgent_stop.set()
            elif kind=='near':m.distance_gate.near=True
            elif kind=='fault':m.controller.state='FAULT'
            elif kind=='route':m.controller.pose_route=NS(safety_hold=True)
            else:m.normal_measurement.state='aborted'
            p=Observer();p.observe(m,0.);self.assertEqual(p.samples,[])
    def test_scope_clock_and_feedback_regression(self):
        m,d,b=self.motor();m.lab07_pair_id='presentation'
        with self.assertRaises(ValueError):Observer().observe(m,0.)
        for t in (-.1,float('nan'),2.):
            m,d,b=self.motor();p=Observer();p.observe(m,0.)
            with self.assertRaises(ValueError):p.observe(m,t)
        m,d,b=self.motor();p=Observer();p.observe(m,.1)
        m.controller.last_rows[0]['sampled_monotonic_s']=-.01
        with self.assertRaises(ValueError):p.observe(m,.2)
    def test_session_retry_preserves_evidence(self):
        m,d,b=self.motor();n,_,_=self.motor();s=Sessions();p=s.get(m);p.events.append({'test':'evidence'})
        with self.assertRaises(RuntimeError):s.get(n)
        m.finished.set();q=s.get(n);self.assertEqual(q.samples,[]);self.assertEqual(s.attempts[0][1].events,[{'test':'evidence'}])
    def test_scoped_step_suppresses_body_only_and_other_profiles_unchanged(self):
        m,d,b=self.motor();s=Sessions();original=Mock(return_value='untouched')
        scoped_step(original,s,d,m,0.);b.write.assert_not_called();d.rhythm.advance.assert_called_once_with(0.,False,exclusive=True)
        m.lab07_pair_id='presentation';self.assertEqual(scoped_step(original,s,d,m,.1),'untouched')
        original.assert_called_once_with(d,m,.1)
    def test_label_keeps_fault_and_names_observer_only(self):
        m,d,b=self.motor();s=Sessions();p=s.get(m)
        for k in range(301):self.advance(p,m,k/10.)
        text=label(lambda m:'original',s,m)
        self.assertIn('COMPLETE',text);self.assertIn('30/30',text);self.assertIn('OBSERVER ONLY',text)
        m.controller.state='FAULT';self.assertEqual(label(lambda m:'FAULT detail',s,m),'FAULT detail')
        m.controller.state='READY';m.distance_gate.near=True
        self.assertEqual(label(lambda m:'ToF HOLD',s,m),'ToF HOLD')

if __name__=='__main__':unittest.main()
