import math
import threading
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

import physical_distance
from bio_inspire.runtime.distance_behavior import DistanceGate
from bio_inspire.runtime import normal_ahm
from . import tof_isolation
from . import startup


def condition(sample_list):
    from .range_conditioning import RangeFilter
    bank = RangeFilter()
    return [bank.frame(cm, t, seq, error, meta) for t, seq, cm, error, meta in sample_list]


def ranges(values):
    return condition([(10+i*.1, i+1, v, None, {'measurement_state':'range', 'range_status_raw':9})
                      for i,v in enumerate(values)])


class Tests(unittest.TestCase):
    def test_existing_gate_uses_conditioned_cm_when_present(self):
        gate=tof_isolation.isolated_gate(DistanceGate)()
        frame=dict(distance_cm=9,filtered_distance_cm=50,raw_distance_cm=9,received_s=1.,error=None)
        self.assertIsNone(gate.step(frame,1.))

    def test_pulse_does_not_trigger_behavior_but_reaches_brake_immediately(self):
        a = ranges([50,51,50,9,50])
        self.assertEqual(a[3]['raw_distance_cm'],9)
        self.assertEqual(a[3]['filtered_distance_cm'],50)
        self.assertEqual(a[3]['distance_cm'],9)
        gate=tof_isolation.isolated_gate(DistanceGate)()
        events=[gate.step(q,q['received_s']) for q in a]
        self.assertNotIn('near',events)
        self.assertEqual(tof_isolation.IsolatedDistancePolicy().update(a[3],10.3)['state'],'near')

    def test_held_obstacle_and_hysteresis(self):
        gate=tof_isolation.isolated_gate(DistanceGate)()
        a=ranges([50,50,50,19,19,24,24,28,28])
        result=[gate.step(q,q['received_s']) for q in a]
        self.assertEqual(result.index('near'),4)
        self.assertEqual(result.index('clear'),8)
        self.assertLess(a[7]['distance_cm'],28)

    def test_invalid_no_target_and_gaps_never_reuse_old_range(self):
        a=condition([(1.,1,50,None,{}),(1.1,2,50,None,{}),(1.2,3,None,None,{'measurement_state':'unreliable','range_status_raw':7}),
                     (1.3,4,None,None,{'measurement_state':'no_target','range_status_raw':4}),
                     (1.4,5,12,None,{}),(1.9,6,80,None,{}),(2.,8,10,None,{})])
        self.assertEqual([q['filtered_distance_cm'] for q in a],[50,50,None,None,12,80,10])
        self.assertEqual(physical_distance.distance_input_kind(a[3],1.3),'no_target')
        self.assertEqual(physical_distance.distance_input_kind(a[5],2.1),'fault')

    def test_fsm_view_and_hormone_use_the_filtered_sample(self):
        from .range_conditioning import read_stimulus
        frame=ranges([60,60,60,19])[-1]
        now=frame['received_s']; button=NS(diagnostics=lambda:dict(stable_pressed=False,last_sample_s=now))
        lamp=NS(distance_view=frame.copy(),physical_distance=NS(latest=lambda:frame),
                physical_button=button,physical_touch=button,now=lambda:now,distance_gate=DistanceGate())
        startup.build_recovery_poll(lambda *a,**k:False)(lamp,now)
        self.assertEqual(lamp.distance_view['distance_cm'],60)
        detail={}
        self.assertEqual(read_stimulus(lamp,now,detail),0.)
        self.assertFalse(detail['near'])
        self.assertEqual(detail['tof_quality'],'range')
        self.assertEqual(frame['distance_cm'],19)

    def test_bad_tof_does_not_reset_touch_or_clear_confirmed_near(self):
        from .range_conditioning import read_stimulus
        stamp=10.; fail={'distance_cm':None,'error':'i2c','received_s':stamp}
        def gpio(active):return NS(diagnostics=lambda:dict(stable_pressed=active,last_sample_s=stamp))
        m=NS(now=lambda:stamp,physical_distance=NS(latest=lambda:fail),physical_button=gpio(False),
             physical_touch=gpio(True),distance_gate=NS(near=False))
        for c in ('C0','C1'):
            ahm=normal_ahm.NormalAHM(c)
            for t in (9.8,9.85,9.9,9.95,10.): ahm.step(t,1.)
            with patch.object(normal_ahm,'read_stimulus',read_stimulus):
                m.controller=NS(state='READY')
                v=normal_ahm.update_from_owner(ahm,m,stamp)
            self.assertEqual(v['reason'],'tracking')
            self.assertGreater(v['h'],0)
        m.physical_touch=gpio(False);m.distance_gate.near=True;details={}
        self.assertEqual(read_stimulus(m,stamp,details),1.)
        self.assertEqual(details['tof_quality'],'fault')
        self.assertEqual(read_stimulus(m,stamp+.2,{}),None)

    def test_i2c_worker_reopens_after_error_and_exits_on_close(self):
        from .range_conditioning import conditioned_source
        class Fake(physical_distance.PhysicalDistance):
            def _run(self):
                if not hasattr(self,'attempts'): self.attempts=0
                self.attempts+=1
                self._publish(40,None,1,measurement_state='range',range_status_raw=9)
                if self.attempts==1:self._publish(None,'I2C error',1)
                else:self.stop.set()
        source=conditioned_source(Fake)(clock=lambda:10.)
        source.thread.join(2.)
        self.assertFalse(source.thread.is_alive())
        self.assertEqual(source.attempts,2);self.assertEqual(source.latest()['sequence'],2)
        self.assertEqual(source.latest()['filtered_distance_cm'],40);source.close()

