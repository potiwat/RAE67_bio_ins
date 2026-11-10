import unittest
from types import SimpleNamespace
import test_afraid_pose as afraid_fixture


class Tests(unittest.TestCase):
    def test_lab_hysteresis_and_freshness(self):
        from distance_behavior import DistanceGate
        g=DistanceGate()
        def sample(cm,t):return dict(distance_cm=cm,received_s=t,error=None)
        self.assertIsNone(g.step(sample(30,1.),1.))
        self.assertEqual(g.step(sample(20,1.1),1.1),'near')
        self.assertIsNone(g.step(sample(25,1.2),1.2));self.assertTrue(g.near)
        self.assertEqual(g.step(sample(28,1.3),1.3),'clear')
        self.assertEqual(g.step(sample(10,1.3),1.5),'fault')
        self.assertEqual(g.step(sample(None,2.),2.),'fault')

    def test_tof_enters_fold_and_clear_returns_without_touch(self):
        from distance_behavior import DistanceGate,poll_distance
        m,b=afraid_fixture.Tests().motor();m.afraid_fold_down=True
        m.distance_gate=DistanceGate();sample=dict(distance_cm=15.,received_s=20.,error=None)
        m.physical_distance=SimpleNamespace(latest=lambda:dict(sample))
        self.assertTrue(poll_distance(m,20.))
        self.assertEqual(m.behavior_trial,'afraid')
        self.assertEqual(b.reg[3][42],m.controller.normal[3]+68)
        sample.update(distance_cm=30.,received_s=20.1)
        self.assertTrue(poll_distance(m,20.1))
        self.assertEqual(m.behavior_trial,'normal_transition')

    def test_public_f_queue_reaches_afraid_handler(self):
        m,b=afraid_fixture.Tests().motor();m.keys=[]
        m.key(ord('f'));self.assertEqual(m.keys,[ord('f')])

    def test_distance_priority_consumes_touch_without_entering_happy(self):
        m,b=afraid_fixture.Tests().motor();m.touch_sequence=0
        m.physical_touch=SimpleNamespace(poll=lambda now:True)
        b.calls.clear();m._poll_physical_touch(20.,suppress=True)
        self.assertEqual(m.last_touch_event['status'],'ignored_distance_priority')
        self.assertEqual(b.calls,[])

    def test_queued_normal_cannot_unfold_when_current_tof_is_near(self):
        from distance_behavior import DistanceGate,poll_distance
        m,b=afraid_fixture.Tests().motor();m.afraid_fold_down=True;m.distance_gate=DistanceGate()
        m.physical_distance=SimpleNamespace(latest=lambda:dict(distance_cm=10.,received_s=20.,error=None))
        poll_distance(m,20.);b.calls.clear()
        m._key(ord('n'))
        self.assertEqual(m.behavior_trial,'afraid')
        self.assertFalse(any(a==42 for i,a,q in b.calls))

    def test_receipt_during_poll_is_not_mistaken_for_future_data(self):
        from distance_behavior import DistanceGate,poll_distance
        m,b=afraid_fixture.Tests().motor();m.distance_gate=DistanceGate()
        m.now=lambda:20.002
        m.physical_distance=SimpleNamespace(latest=lambda:dict(distance_cm=15.,received_s=20.001,error=None))
        poll_distance(m,20.)
        self.assertNotEqual(m.controller.state,'FAULT')
        self.assertEqual(m.behavior_trial,'afraid')

    def test_invalid_tof_waits_and_does_not_unfold_as_clear(self):
        from distance_behavior import DistanceGate,poll_distance
        m,b=afraid_fixture.Tests().motor();m.distance_gate=DistanceGate()
        m.physical_distance=SimpleNamespace(latest=lambda:dict(distance_cm=None,received_s=20.,error='invalid measurement'))
        poll_distance(m,20.)
        self.assertEqual(m.controller.state,'WAIT_TOF')
        self.assertIn('ToF',m.controller.last_error)

    def test_no_target_does_not_hold_normal_or_block_startup(self):
        from distance_behavior import DistanceGate,poll_distance
        for state in ('READY','NORMAL_STARTUP'):
            m,b=afraid_fixture.Tests().motor();m.controller.state=state;m.distance_gate=DistanceGate()
            m.physical_distance=SimpleNamespace(latest=lambda:dict(distance_cm=None,received_s=20.,error=None,measurement_state='no_target',range_status_raw=4))
            b.calls.clear();poll_distance(m,20.)
            self.assertEqual(m.controller.state,state);self.assertEqual(b.calls,[])

    def test_no_target_clears_afraid_without_fabricated_centimeters(self):
        from distance_behavior import DistanceGate,poll_distance
        m,b=afraid_fixture.Tests().motor();m.distance_gate=DistanceGate()
        sample=dict(distance_cm=15.,received_s=20.,error=None)
        m.physical_distance=SimpleNamespace(latest=lambda:dict(sample))
        poll_distance(m,20.)
        sample.update(distance_cm=None,measurement_state='no_target',range_status_raw=4)
        poll_distance(m,20.)
        self.assertEqual(m.behavior_trial,'normal_transition')
        self.assertIsNone(m.distance_view['distance_cm'])

    def test_unreliable_completed_frame_preserves_state_without_hold(self):
        from distance_behavior import DistanceGate,poll_distance
        for near in (False,True):
            m,b=afraid_fixture.Tests().motor();m.distance_gate=DistanceGate();m.distance_gate.near=near
            if near:
                from afraid_pose import enter_afraid
                enter_afraid(m)
            sample=dict(distance_cm=None,received_s=20.,error=None,measurement_state='unreliable',range_status_raw=7)
            m.physical_distance=SimpleNamespace(latest=lambda:dict(sample));b.calls.clear()
            poll_distance(m,20.)
            self.assertEqual(m.distance_gate.near,near)
            self.assertNotIn(m.controller.state,('FAULT','WAIT_TOF'))
            self.assertEqual(b.calls,[])

    def test_quality_warning_cannot_latch_near_forever(self):
        from distance_behavior import DistanceGate
        g=DistanceGate()
        g.step(dict(distance_cm=10.,received_s=20.,error=None),20.)
        sample=dict(distance_cm=None,received_s=20.2,error=None,measurement_state='unreliable',range_status_raw=5)
        self.assertIsNone(g.step(sample,20.2));self.assertTrue(g.near)
        sample['received_s']=20.5
        self.assertEqual(g.step(sample,20.5),'clear');self.assertFalse(g.near)

    def test_valid_hysteresis_band_refreshes_near_confirmation(self):
        from distance_behavior import DistanceGate
        g=DistanceGate()
        g.step(dict(distance_cm=10.,received_s=20.,error=None),20.)
        g.step(dict(distance_cm=25.,received_s=20.4,error=None),20.4)
        sample=dict(distance_cm=None,received_s=20.8,error=None,measurement_state='unreliable',range_status_raw=7)
        self.assertIsNone(g.step(sample,20.8));self.assertTrue(g.near)
        sample['received_s']=20.9
        self.assertEqual(g.step(sample,20.9),'clear')
