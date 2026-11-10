import unittest
import test_deep_sleepy as fixture
from three_state_behavior import handle_state_key
from body_rhythm import BodyRhythmDriver
class Tests(unittest.TestCase):
    def test_one_native_goal_and_delayed_cpg3(self):
        m,b=fixture.DeepSleepyTests().motor();c=m.controller;c.sleepy_native_fold_enabled=True
        handle_state_key(m,ord('s'));d=BodyRhythmDriver(sleepy_amplitude_deg=2.,time_scale=.5);b.calls.clear()
        for n in range(81):
            d.step(m,20+n*.05)
        goals=[q for sid,a,q in b.calls if sid==3 and a==42]
        self.assertEqual(goals,[c.sleepy_body_reference[3]+68])
        self.assertEqual(b.reg[3][46],9)
        self.assertGreater(len([q for sid,a,q in b.calls if sid==2 and a==42]),1)
        b.pos[3]=goals[0];c.last_rows=b.snapshot();d.step(m,28.)
        self.assertEqual(b.reg[3][46],c.motion_speed)
        d.step(m,30.)
        self.assertEqual(c.sleepy_native_fold['phase'],'breathing')

    def test_midfold_exit_holds_before_restoring_fast_speed(self):
        from sleepy_trial import finish_sleepy_native_fold
        m,b=fixture.DeepSleepyTests().motor();c=m.controller;c.sleepy_native_fold_enabled=True
        handle_state_key(m,ord('s'));d=BodyRhythmDriver(sleepy_amplitude_deg=2.)
        d.step(m,20.);b.calls.clear();finish_sleepy_native_fold(c)
        self.assertEqual([(i,a) for i,a,q in b.calls],[(3,42),(3,46)])
        self.assertEqual(b.reg[3][46],c.motion_speed)
        self.assertFalse(c.sleepy_native_fold['restore_required'])
    def test_waits_if_still_moving_at8_and_sends_no_new_body3_goal(self):
        m,b=fixture.DeepSleepyTests().motor();c=m.controller;c.sleepy_native_fold_enabled=True
        handle_state_key(m,ord('s'));d=BodyRhythmDriver(sleepy_amplitude_deg=2.);d.step(m,20.)
        c.last_rows=b.snapshot();c.last_rows[2]['moving_raw']=1;b.calls.clear();d.step(m,28.)
        self.assertEqual(c.sleepy_native_fold['phase'],'folding')
        self.assertEqual(b.reg[3][46],9)
        self.assertFalse(any(i==3 and a==42 for i,a,q in b.calls))

    def test_rejected_interested_does_not_cancel_fold(self):
        m,b=fixture.DeepSleepyTests().motor();c=m.controller;c.sleepy_native_fold_enabled=True
        handle_state_key(m,ord('s'));d=BodyRhythmDriver(sleepy_amplitude_deg=2.);d.step(m,20.)
        m.yaw_clearance_confirmed=False;b.calls.clear();handle_state_key(m,ord('i'));d.step(m,21.)
        self.assertEqual(m.behavior_trial,'sleepy')
        self.assertEqual(c.sleepy_native_fold['phase'],'folding')
        self.assertEqual(b.reg[3][46],9)
