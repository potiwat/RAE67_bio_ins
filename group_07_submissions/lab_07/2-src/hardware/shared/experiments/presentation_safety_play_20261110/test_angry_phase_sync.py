import unittest
from unittest.mock import patch
from .angry_phase_sync import PhasePlan,coordinated_route


class Tests(unittest.TestCase):
    def plan(self):return PhasePlan({2:2837,3:2746},{2:2848,3:2766},{2:2632,3:2951},20.)
    def test_only_leader_is_slowed_and_blocked_joint_reference_keeps_advancing(self):
        p=self.plan();q=[]
        for k in range(1,41):
            # ID2 remains obstructed, ID3 has advanced40 ticks. No command
            # backs off the obstructed joint or hides its growing error.
            q.append(p.step({2:2848,3:2806},20+k*.05))
        self.assertGreater(p.velocity[2],p.velocity[3])
        self.assertGreater(p.progress[2],p.progress[3])
        self.assertTrue(all(b[2]<=a[2]and b[3]>=a[3]for a,b in zip(q,q[1:])))
        self.assertLess(q[-1][2],q[0][2]-50)

    def test_symmetric_progress_has_no_offset_and_converges_to_exact_endpoints(self):
        p=self.plan();actual={2:2848,3:2766};trace=[]
        for k in range(1,161):
            q=p.step(actual,20+k*.05);trace.append(q)
            actual={2:q[2]+11,3:q[3]+20}
        self.assertEqual(trace[-1],p.target)
        self.assertLessEqual(max(abs(b[i]-a[i])for a,b in zip(trace,trace[1:])for i in(2,3)),3)
        self.assertTrue(all(p.target[2]<=q[2]<=p.source[2]and p.source[3]<=q[3]<=p.target[3]for q in trace))

    def test_slow_tick_cannot_cause_catchup_jump(self):
        p=self.plan();q=p.step(p.anchor,22.)
        self.assertLessEqual(max(abs(q[i]-p.source[i])for i in(2,3)),1)

    def test_constant_rate_has_no_half_tick_rounding_velocity_alternation(self):
        p=self.plan();p.progress={2:.5,3:.5};p.velocity={2:60.,3:60.}
        trace=[p.step(p.anchor,20+k*.05)for k in range(1,21)]
        for a,b in zip(trace,trace[1:]):
            self.assertEqual(a[2]-b[2],3);self.assertEqual(b[3]-a[3],3)

    def test_real_runtime_contact_still_stops_resets_and_auto_resumes(self):
        from bio_inspire.runtime import angry_approach
        from .test_auto_release import AutoReleaseTests
        with patch.object(angry_approach,'AngryApproachRoute',coordinated_route(angry_approach.AngryApproachRoute)):
            r,w=AutoReleaseTests().run_case('angry',2)
        self.assertIsNone(r['error']);self.assertTrue(getattr(w,'resumed',False))
        self.assertTrue(r['cleanup_confirmed']);self.assertEqual(r['reset']['h'],0.)

    def test_contact_during_active_phase_plan_preempts_it_on_all_three_axes(self):
        from bio_inspire.runtime import angry_approach
        from .test_auto_release import AutoReleaseTests
        for sid in (1,2,4):
            with self.subTest(id=sid),patch.object(angry_approach,'AngryApproachRoute',coordinated_route(angry_approach.AngryApproachRoute)):
                def during(w):
                    route=getattr(w.motor.controller,'pose_route',None)
                    plan=getattr(route,'trial_phase_plan',None)
                    if (not w.triggered and plan is not None and
                            min(plan.progress.values())>=40 and route.range_phase=='advance'):
                        w.triggered=True;w.trigger_time=w.clock()
                        w.trigger_state=w.motor.behavior_trial
                        w.plant.contact.add(sid);w.active_plan_contact=True
                r,w=AutoReleaseTests().run_case('angry',sid,extra=during)
                self.assertTrue(getattr(w,'active_plan_contact',False))
                self.assertEqual(w.trigger_state,'angry_transition')
                self.assertIsNone(r['error']);self.assertTrue(getattr(w,'resumed',False))
                self.assertTrue(r['cleanup_confirmed'])
                self.assertEqual(r['reset']['h'],0.)


if __name__=='__main__':unittest.main()
