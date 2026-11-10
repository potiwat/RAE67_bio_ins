import math
import unittest
from bounded_motion import BoundedMotion, MotionLimits

class Tests(unittest.TestCase):
    def test_sine_targets_respect_float_velocity_acceleration_and_outer_bounds(self):
        limits=MotionLimits(2803,2871,400.,99.,.5)
        f=BoundedMotion(2837.,0.,limits);previous_v=0.;previous_t=0.
        for n in range(1,1201):
            now=n*.05;target=2837+34*math.sin(now*2.)
            q=f.step(target,now)
            self.assertTrue(limits.low<=q<=limits.high)
            self.assertLessEqual(abs(f.velocity),limits.speed+1e-7)
            self.assertLessEqual(abs(f.velocity-previous_v)/(now-previous_t),limits.acceleration+1e-5)
            previous_v=f.velocity;previous_t=now
    def test_target_reversal_preserves_command_position_and_velocity(self):
        f=BoundedMotion(0.,0.,MotionLimits(-34,34,100.,100.,.5))
        f.step(34,.1);q,v=f.position,f.velocity
        self.assertEqual(f.step(-34,.1),q);self.assertEqual(f.velocity,v)
        f.step(-34,.2);self.assertLessEqual(abs(f.velocity-v),10.+1e-8)
    def test_invalid_and_stale_targets_rejected_without_state_change(self):
        f=BoundedMotion(0.,0.,MotionLimits(-34,34,100.,100.,.5))
        for q,t in ((35,.1),(float('nan'),.1),(2,.6),(2,-.1)):
            with self.assertRaises(ValueError):f.step(q,t)
            self.assertEqual(f.position,0.);self.assertEqual(f.velocity,0.)
    def test_boundary_stopping_does_not_wrap_or_break_acceleration_limit(self):
        f=BoundedMotion(33.,0.,MotionLimits(-34,34,100.,100.,.5));oldv=0.
        for n in range(1,301):
            f.step(34.,n*.05)
            self.assertLessEqual(f.position,34.);self.assertGreaterEqual(f.position,-34.)
            self.assertLessEqual(abs(f.velocity-oldv),5.+1e-7);oldv=f.velocity

    def test_irregular_owner_intervals_and_target_reversals_keep_limits(self):
        import random
        rng=random.Random(7);k=MotionLimits(-34,34,400.,99.,.5)
        f=BoundedMotion(0.,0.,k);now=0.;oldv=0.
        for _ in range(3000):
            dt=rng.uniform(.04,.124);now+=dt
            f.step(rng.choice((-34.,34.,rng.uniform(-34.,34.))),now)
            self.assertTrue(k.low<=f.position<=k.high)
            self.assertLessEqual(abs(f.velocity-oldv)/dt,k.acceleration+1e-6)
            oldv=f.velocity

    def test_interior_stationary_target_settles_without_rounded_command_chatter(self):
        for dt in (.08,.1,.12):
            with self.subTest(owner_interval=dt):
                f=BoundedMotion(0.,0.,MotionLimits(-34,34,400.,99.,.5));tail=[];oldv=0.
                for n in range(1,501):
                    f.step(10.,n*dt)
                    self.assertLessEqual(abs(f.velocity-oldv)/dt,99.+1e-6);oldv=f.velocity
                    if n>400:tail.append(round(f.position))
                self.assertEqual(set(tail),{10})
                self.assertAlmostEqual(f.velocity,0.,places=5)
