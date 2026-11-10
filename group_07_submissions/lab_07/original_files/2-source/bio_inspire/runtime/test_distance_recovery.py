import unittest
from types import SimpleNamespace
from unittest.mock import Mock
import test_taught_crouch as fixture
from distance_behavior import DistanceGate, poll_distance


class Tests(unittest.TestCase):
    def test_post_feedback_fault_restarts_unknown_release_timer(self):
        for failure in ('error','stale'):
            with self.subTest(failure=failure):
                m,b,s=self.motor();m.distance_gate.near=False;self.invalid(m,s)
                s.update(distance_cm=None,received_s=20.2,error=None,measurement_state='unreliable',range_status_raw=5)
                poll_distance(m,20.2)
                tick=m.controller.tick
                def changed(now):
                    tick(now)
                    if failure=='error':s['error']='read_failed'
                    else:s['received_s']=20.
                m.controller.tick=changed;s['received_s']=20.6;poll_distance(m,20.6)
                m.controller.tick=tick
                s.update(received_s=20.71,error=None);poll_distance(m,20.71)
                self.assertEqual(m.controller.state,'WAIT_TOF')
                s['received_s']=21.22;poll_distance(m,21.22)
                self.assertEqual(m.controller.state,'READY')

    def test_continuous_fresh_unknown_frames_recover_wait_without_near_latch(self):
        m,b,s=self.motor();m.distance_gate.near=False;self.invalid(m,s)
        for t in (20.2,20.3,20.4,20.5,20.6):
            s.update(distance_cm=None,received_s=t,error=None,measurement_state='unreliable',range_status_raw=5)
            poll_distance(m,t);self.assertEqual(m.controller.state,'WAIT_TOF')
        s['received_s']=20.71;poll_distance(m,20.71)
        self.assertEqual(m.controller.state,'READY')
        self.assertEqual(m.behavior_trial,'normal_transition')
        self.assertIsNone(m.distance_view['distance_cm'])

    def test_unknown_recovery_does_not_override_stop(self):
        m,b,s=self.motor();m.distance_gate.near=False;self.invalid(m,s)
        s.update(distance_cm=None,received_s=20.2,error=None,measurement_state='unreliable',range_status_raw=5)
        poll_distance(m,20.2);m.operator_stopped=True;b.calls.clear()
        s['received_s']=20.8;poll_distance(m,20.8)
        self.assertEqual(m.controller.state,'WAIT_TOF');self.assertEqual(b.calls,[])

    def motor(self):
        m,b=fixture.Tests().motor();m.distance_gate=DistanceGate()
        sample=dict(distance_cm=15.,received_s=20.,error=None)
        m.physical_distance=SimpleNamespace(latest=lambda:dict(sample))
        poll_distance(m,20.)
        return m,b,sample

    def invalid(self,m,sample):
        sample.update(distance_cm=None,received_s=20.1,error='invalid measurement')
        poll_distance(m,20.1)

    def test_invalid_holds_once_then_fresh_clear_returns_normal(self):
        m,b,s=self.motor();self.invalid(m,s)
        self.assertEqual(m.controller.state,'WAIT_TOF')
        self.assertFalse(m.follow_enabled)
        b.calls.clear();poll_distance(m,20.11)
        self.assertEqual(b.calls,[])
        s.update(distance_cm=40.,received_s=20.2,error=None)
        poll_distance(m,20.2)
        self.assertEqual(m.behavior_trial,'normal_transition')
        self.assertEqual(m.controller.state,'READY')
        self.assertEqual(b.reg[2][42],m.controller.normal[2])

    def test_fresh_near_resumes_crouch_without_arming(self):
        m,b,s=self.motor();self.invalid(m,s)
        s.update(distance_cm=15.,received_s=20.2,error=None);b.calls.clear()
        poll_distance(m,20.2)
        self.assertEqual(m.behavior_trial,'afraid')
        self.assertEqual(m.controller.pose_route.phase,'retreat')
        self.assertFalse(any(a==40 for i,a,q in b.calls))

    def test_invalid_never_changes_hysteresis_or_clears(self):
        m,b,s=self.motor();self.invalid(m,s)
        self.assertTrue(m.distance_gate.near)
        s.update(distance_cm=25.,received_s=20.2,error=None)
        poll_distance(m,20.2)
        self.assertEqual(m.behavior_trial,'afraid')

    def test_stop_fault_and_power_loss_prevent_recovery(self):
        for condition in ('operator','fault','power'):
            with self.subTest(condition=condition):
                m,b,s=self.motor();self.invalid(m,s)
                if condition=='operator':m.operator_stopped=True
                elif condition=='fault':m.controller.state='FAULT'
                else:
                    b.torque[2]=0
                    m.controller.tick(20.15)
                    self.assertEqual(m.controller.state,'FAULT')
                b.calls.clear();s.update(distance_cm=40.,received_s=20.2,error=None)
                poll_distance(m,20.2)
                self.assertEqual(b.calls,[])
                self.assertNotEqual(m.behavior_trial,'normal_transition')

    def test_hold_failure_is_not_recoverable_tof_wait(self):
        m,b,s=self.motor()
        def fail(*args,**kwargs):m.controller.state='FAULT'
        m._hold=fail;self.invalid(m,s)
        self.assertEqual(m.controller.state,'FAULT')
        b.calls.clear();s.update(distance_cm=40.,received_s=20.2,error=None)
        poll_distance(m,20.2);self.assertEqual(b.calls,[])

    def test_wait_blocks_touch_and_behavior_commands(self):
        m,b,s=self.motor();self.invalid(m,s)
        m.physical_touch=SimpleNamespace(poll=lambda now:True);m.touch_sequence=0
        b.calls.clear();m._poll_physical_touch(20.11,suppress=True)
        m._key(ord('n'))
        self.assertEqual(b.calls,[])
        self.assertEqual(m.controller.state,'WAIT_TOF')

    def test_operator_stop_key_during_wait_prevents_auto_return(self):
        m,b,s=self.motor();self.invalid(m,s)
        m._key(ord('h'))
        self.assertTrue(m.operator_stopped)
        b.calls.clear();s.update(distance_cm=40.,received_s=20.2,error=None)
        poll_distance(m,20.2)
        self.assertEqual(b.calls,[])

    def test_stale_sample_holds_then_clear_recovers(self):
        m,b,s=self.motor()
        poll_distance(m,20.2)
        self.assertEqual(m.controller.state,'WAIT_TOF')
        s.update(distance_cm=40.,received_s=20.3,error=None)
        poll_distance(m,20.3)
        self.assertEqual(m.behavior_trial,'normal_transition')

    def test_fresh_no_target_recovers_from_wait_without_numeric_range(self):
        m,b,s=self.motor();self.invalid(m,s)
        s.update(distance_cm=None,received_s=20.2,error=None,measurement_state='no_target',range_status_raw=4)
        poll_distance(m,20.2)
        self.assertEqual(m.behavior_trial,'normal_transition')
        self.assertFalse(m.distance_gate.near)

    def test_unknown_from_normal_cannot_resume_on_hysteresis_band(self):
        m,b,s=self.motor()
        from three_state_behavior import handle_state_key
        handle_state_key(m,ord('n'));m.distance_gate.near=False
        self.invalid(m,s)
        b.calls.clear();s.update(distance_cm=25.,received_s=20.2,error=None)
        poll_distance(m,20.2)
        self.assertEqual(m.controller.state,'WAIT_TOF')
        self.assertEqual(b.calls,[])

    def test_recovery_rechecks_distance_and_stop_after_blocking_feedback(self):
        for change in ('invalid','expired','near','stop'):
            with self.subTest(change=change):
                m,b,s=self.motor();self.invalid(m,s)
                s.update(distance_cm=40.,received_s=20.2,error=None)
                tick=m.controller.tick
                def changed_tick(now):
                    tick(now)
                    if change=='invalid':s.update(distance_cm=None,error='invalid measurement')
                    elif change=='expired':m.now=lambda:20.5
                    elif change=='near':s.update(distance_cm=10.)
                    else:m.urgent_stop.set()
                m.controller.tick=changed_tick;b.calls.clear()
                poll_distance(m,20.2)
                if change=='near':self.assertEqual(m.behavior_trial,'afraid')
                else:
                    self.assertEqual(m.controller.state,'WAIT_TOF')
                    self.assertEqual(b.calls,[])

    def test_near_observed_before_feedback_refreshes_quality_timeout(self):
        m,b,s=self.motor();self.invalid(m,s)
        s.update(distance_cm=15.,received_s=20.49,error=None)
        tick=m.controller.tick
        def changed_tick(now):
            tick(now);m.now=lambda:20.51
            s.update(distance_cm=None,received_s=20.51,error=None,measurement_state='unreliable',range_status_raw=5)
        m.controller.tick=changed_tick;b.calls.clear()
        poll_distance(m,20.49)
        self.assertEqual(m.controller.state,'WAIT_TOF')
        self.assertTrue(m.distance_gate.near)
        self.assertEqual(m.distance_gate.last_confirmed_near_s,20.49)
        self.assertEqual(b.calls,[])

