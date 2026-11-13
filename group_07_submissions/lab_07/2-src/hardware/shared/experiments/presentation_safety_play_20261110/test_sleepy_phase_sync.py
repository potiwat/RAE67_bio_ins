import unittest
from unittest.mock import patch
from bio_inspire.runtime.body_rhythm import BodyRhythmDriver
from bio_inspire.runtime import sleepy_trial
from . import test_sleepy_coordination as fixture
from .sleepy_phase_sync import SleepyPlan,phase_driver,fold_weight,phase_ready


class Tests(unittest.TestCase):
    def motor(self):return fixture.Tests().motor()

    def test_different_angle_axes_use_normalized_encoder_progress(self):
        m,b=self.motor();c=m.controller;p=SleepyPlan(c,b.reg[2][42],20.)
        q=p.step(c.last_rows,20.05)
        self.assertEqual(q,p.source)
        # Same percentage of travel at different raw distances must not
        # look like a leader solely because the head travels twice as far.
        rows=[dict(r)for r in c.last_rows]
        for r in rows:
            if r['id']in(3,5):
                i=r['id'];r['position_raw']=p.actual[i]+p.sign[i]*p.length[i]*.25
        p.step(rows,20.1)
        self.assertAlmostEqual(p.pair.skew,0.)

    def test_exact_endpoints_with_unchanged_native_profiles_and_no_extra_offset(self):
        m,b=self.motor();c=m.controller
        driver=phase_driver(BodyRhythmDriver)(sleepy_amplitude_deg=2.)
        with patch.object(sleepy_trial,'sleepy_native_fold_weight',fold_weight(sleepy_trial.sleepy_native_fold_weight)):
            for k in range(241):
                driver.step(m,20+k*.05)
                for i in(2,3,5):b.pos[i]=b.reg[i][42]
                c.last_rows=b.snapshot()
            p=c.sleepy_phase_sync_plan
            self.assertTrue(p.commands_done)
            self.assertEqual(b.reg[5][42],p.target[5])
            self.assertEqual(p.target[3],c.sleepy_body_reference[3]+137)
            self.assertEqual(c.sleepy_native_fold['phase'],'breathing')
            self.assertEqual(b.reg[5][46],25)
            self.assertEqual(b.reg[3][46],c.motion_speed)

    def test_cpg_handoff_waits_for_fold_head_without_changing_oscillator(self):
        m,b=self.motor();c=m.controller;p=SleepyPlan(c,b.reg[2][42],20.)
        c.sleepy_phase_sync_plan=p
        self.assertFalse(phase_ready(c))
        p.commands_done=True
        self.assertFalse(phase_ready(c))
        head=next(r for r in c.last_rows if r['id']==5)
        head.update(position_raw=p.target[5],speed_raw=0,moving_raw=0)
        self.assertTrue(phase_ready(c))

    def test_stop_preempts_fold_without_new_goal_writes(self):
        m,b=self.motor();d=phase_driver(BodyRhythmDriver)(sleepy_amplitude_deg=2.)
        d.step(m,20.);m.operator_stopped=True;b.calls.clear();d.step(m,21.)
        self.assertEqual(b.calls,[]);self.assertEqual(d.active_joint_ids,(2,3))

    def test_real_runtime_sleepy_contact_still_auto_returns_to_normal(self):
        from . import sleepy_coordination
        from .test_auto_release import AutoReleaseTests
        with patch.object(sleepy_coordination,'coordinated_driver',phase_driver),patch.object(
                sleepy_trial,'sleepy_native_fold_weight',fold_weight(sleepy_trial.sleepy_native_fold_weight)):
            r,w=AutoReleaseTests().run_case('sleepy',2)
        self.assertIsNone(r['error']);self.assertTrue(getattr(w,'resumed',False))
        self.assertTrue(r['cleanup_confirmed']);self.assertEqual(r['reset']['h'],0.)


if __name__=='__main__':unittest.main()
