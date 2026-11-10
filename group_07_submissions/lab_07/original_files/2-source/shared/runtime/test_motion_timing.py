import unittest
from motion_timing import CommandState, JointLimits, QuinticTransition, plan_transition, TrajectoryLimitError


class TimingTests(unittest.TestCase):
    def states(self, q, v=0., a=0.):
        return {i: CommandState(q, v, a) for i in range(1, 6)}

    def limits(self, **override):
        values = dict(low=0., high=4095., max_velocity=1000., max_acceleration=1000., max_jerk=10000.)
        values.update(override)
        return {i: JointLimits(**values) for i in range(1, 6)}

    def test_interruption_preserves_command_q_v_a(self):
        first = QuinticTransition(self.states(2000.), self.states(2100.), 4.)
        interrupted = first.sample(1.4)
        second = QuinticTransition(interrupted, self.states(1900.), 5.)
        self.assertEqual(second.sample(0.), interrupted)
        self.assertNotEqual(interrupted[2].v, 0.)
        self.assertNotEqual(interrupted[2].a, 0.)
        for sid in range(1, 6):
            end = second.sample(5.)[sid]
            self.assertAlmostEqual(end.q, 1900.)
            self.assertAlmostEqual(end.v, 0.)
            self.assertAlmostEqual(end.a, 0.)

    def test_general_nonzero_endpoint_velocity_and_acceleration(self):
        start, end = self.states(2000., 5., -1.), self.states(2050., 2., 1.)
        transition = QuinticTransition(start, end, 3.)
        self.assertEqual(transition.sample(0.), start)
        self.assertEqual(transition.sample(3.), end)

    def test_analytic_limits_find_interior_peak_not_just_endpoints(self):
        transition = QuinticTransition(self.states(2000.), self.states(2100.), 1.)
        report = transition.validate(self.limits(max_velocity=150.))
        self.assertFalse(report.valid)
        self.assertAlmostEqual(report.maxima[1]['velocity'], 187.5)
        with self.assertRaises(TrajectoryLimitError):
            plan_transition(self.states(2000.), self.states(2100.), self.limits(max_velocity=150.), duration_s=1.)

    def test_no_transition_can_be_approved_without_explicit_limits(self):
        with self.assertRaises(ValueError):
            plan_transition(self.states(2000.), self.states(2010.), None, duration_s=1.)
        for duration in (0., -1., float('nan'), True):
            with self.assertRaises(ValueError):
                QuinticTransition(self.states(2000.), self.states(2010.), duration)

    def test_boundary_violation_and_intermediate_overshoot_are_rejected(self):
        transition = QuinticTransition(self.states(2000., 200.), self.states(2000.), 3.)
        self.assertFalse(transition.validate(self.limits(low=1990., high=2010.)).valid)
        good = plan_transition(self.states(2000.), self.states(2010.), self.limits(), duration_s=2.)
        self.assertTrue(good.validate(self.limits()).valid)

    def test_approved_transition_cannot_be_mutated_after_validation(self):
        transition = plan_transition(self.states(2000.), self.states(2010.), self.limits(), duration_s=2.)
        with self.assertRaises(TypeError): transition.end[1] = CommandState(5000.)
        with self.assertRaises(TypeError): transition.start[1] = CommandState(-100.)
        with self.assertRaises(TypeError): transition.coefficients[1] = (5000.,)
        with self.assertRaises(AttributeError): transition.duration_s = .01
        self.assertTrue(transition.validate(self.limits()).valid)
        self.assertEqual(transition.sample(2.)[1].q, 2010.)

    def test_exact_endpoints_checked_even_when_polynomial_cancels(self):
        # Cancellation must never turn an out-of-bounds endpoint into approval.
        try:
            transition = QuinticTransition(self.states(0., -1e14), self.states(2000.1, 1e14), 1.)
        except ValueError:
            return  # Explicit rejection of unstable coefficients is valid.
        self.assertFalse(transition.validate(self.limits(low=-1e16, high=2000., max_velocity=1e17,
                                                       max_acceleration=1e18, max_jerk=1e19)).valid)

    def test_unstable_endpoint_polynomials_are_rejected(self):
        with self.assertRaises(ValueError):
            QuinticTransition(self.states(0., -1e14), self.states(2000.1, 1e14), 1.)


if __name__ == '__main__': unittest.main()
