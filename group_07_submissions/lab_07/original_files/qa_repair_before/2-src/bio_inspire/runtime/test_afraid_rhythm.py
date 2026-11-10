import unittest
import math
from unittest.mock import Mock
import test_taught_crouch as fixture
from afraid_pose import enter_afraid
from afraid_rhythm import AfraidRhythm

class Tests(unittest.TestCase):
    def motor(self):
        m,b=fixture.Tests().motor();enter_afraid(m);c=m.controller
        c.tick(30.)
        for _ in range(3):
            b.pos={i:b.reg[i][42] for i in range(1,6)};c.tick(c.last_tick+.1)
        self.assertEqual(c.pose_route.phase,'held')
        b.calls.clear();return m,b

    def test_after_hold_breathes_only_body_without_exceeding_taught_cap(self):
        m,b=self.motor();d=AfraidRhythm();seen={2:[],3:[]}
        for n in range(401):
            now=31.+n*.05;d.step(m,now)
            for i in seen:seen[i].append(b.reg[i][42])
            self.assertTrue(all(i in (2,3) and a==42 for i,a,q in b.calls));b.calls.clear()
        for i in seen:
            cap=m.afraid_taught_pose[i]
            self.assertLess(min(seen[i]),cap-10)
            self.assertLessEqual(max(seen[i]),cap)
            self.assertGreaterEqual(min(seen[i]),math.floor(cap-2*4096/360))
        self.assertAlmostEqual(d.rhythm.envelope,1.)

    def test_retreat_clear_stop_fault_and_stale_wait_have_no_position_output(self):
        for case in ('retreat','clear','stop','fault','wait','urgent'):
            with self.subTest(case=case):
                m,b=self.motor();d=AfraidRhythm();d.step(m,31.);d.step(m,31.05)
                if case=='retreat':m.controller.pose_route.phase='retreat'
                elif case=='clear':m.behavior_trial='normal_transition'
                elif case=='stop':m.operator_stopped=True
                elif case=='fault':m.controller.state='FAULT'
                elif case=='wait':m.controller.state='WAIT_TOF'
                else:m.urgent_stop.set()
                b.calls.clear();d.step(m,31.1);self.assertEqual(b.calls,[])

    def test_final_float_motion_obeys_existing_limits(self):
        m,b=self.motor();d=AfraidRhythm();previous={}
        for n in range(240):
            d.step(m,31.+n*.05)
            for i,motion in d.motion.items():
                self.assertLessEqual(abs(motion.velocity),motion.limits.speed+1e-6)
                if i in previous:self.assertLessEqual(abs(motion.velocity-previous[i])/.05,motion.limits.acceleration+1e-4)
                previous[i]=motion.velocity

    def test_owner_dispatches_afraid_driver_and_keeps_happy_inactive(self):
        m,b=self.motor();m.now=lambda:31.
        m.rhythm_driver=Mock();m.afraid_rhythm_driver=AfraidRhythm()
        m._service_body_rhythm()
        m.rhythm_driver.step.assert_called_once()
        self.assertEqual(m.rhythm_view_cache['condition'],'afraid_one_sided_breathing')
