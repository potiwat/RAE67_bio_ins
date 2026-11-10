"""Normal-only hardware adaptation, measured against retained teacher AHM."""
import math
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from bio_inspire.runtime.normal_ahm import NormalAHM, read_stimulus, validate_trial_config
from bio_inspire.experiments.ahm_cpg_compare import course_model, RATES, DT


class Tests(unittest.TestCase):
    def test_teacher_parity_old_input_and_hormone_clock_not_stretched(self):
        a=NormalAHM('C1');h=0.
        a.step(0.,1.)
        for k in range(1,41):
            h=course_model()['hormone_step'](h,1.,DT,RATES)['h']
            r=a.step(k*.05,1.)
            self.assertAlmostEqual(r['h'],h,places=13)
            self.assertAlmostEqual(r['phi'],.1+.03*h)
        before=r['h']
        # A new S cannot be backdated over the elapsed interval.
        r=a.step(2.1,0.)
        expected=before
        for _ in range(2):expected=.96*expected+.04
        self.assertAlmostEqual(r['h'],expected)
        r=a.step(2.15,0.)
        self.assertAlmostEqual(r['h'],expected*.96)
        self.assertGreater(r['h'],0.)

    def test_c0_c1_common_bounds_and_no_new_s_retroactively(self):
        direct=NormalAHM('C0');hormone=NormalAHM('C1')
        self.assertEqual(direct.step(0.,0.)['phi'],.1)
        hormone.step(0.,0.)
        self.assertEqual(direct.step(.05,1.)['phi'],.13)
        self.assertEqual(hormone.step(.05,1.)['phi'],.1)
        self.assertAlmostEqual(hormone.step(.1,1.)['h'],.04)
        for a in (direct,hormone):
            for k in range(3,303):self.assertTrue(.1<=a.step(k*.05,1.)['phi']<=.13)

    def test_fault_stop_gap_and_invalid_clock_restore_baseline(self):
        a=NormalAHM('C1');a.step(0.,1.);self.assertGreater(a.step(.1,1.)['h'],0)
        self.assertEqual(a.step(.15,None)['phi'],.1)
        self.assertEqual(a.step(.2,1.,enabled=False)['h'],0)
        a.step(.25,1.)
        self.assertEqual(a.step(2.,1.)['reason'],'history_gap')
        for stamp in (0.,math.nan,math.inf):
            with self.assertRaises(ValueError):a.step(stamp,1.)
        with self.assertRaises(ValueError):NormalAHM('other')

    def test_fractional_input_change_does_not_rewrite_open_interval(self):
        a=NormalAHM('C1');a.step(0.,0.);a.step(.03,1.)
        self.assertEqual(a.step(.05,1.)['h'],0.)
        self.assertAlmostEqual(a.step(.1,1.)['h'],.04)

    def test_sampler_snapshot_uses_clock_observed_after_snapshot(self):
        src=Mock();src.diagnostics.return_value=dict(stable_pressed=True,last_sample_s=1.00001,sampler_error=None)
        m=SimpleNamespace(physical_touch=src,physical_button=src,now=lambda:1.00002,
            distance_view=dict(distance_cm=50.,received_s=1.,error=None),distance_gate=SimpleNamespace(near=False))
        self.assertEqual(read_stimulus(m,1.),1.)

    def test_latest_worker_cache_used_after_blocking_motion_not_old_fsm_view(self):
        src=Mock();src.diagnostics.return_value=dict(stable_pressed=False,last_sample_s=1.,sampler_error=None)
        distance=Mock();distance.latest.return_value=dict(distance_cm=30.,received_s=1.,error=None)
        m=SimpleNamespace(physical_touch=src,physical_button=src,physical_distance=distance,
            distance_view=dict(distance_cm=18.,received_s=.55,error=None),distance_gate=SimpleNamespace(near=False))
        self.assertEqual(read_stimulus(m,1.),0.)
        distance.latest.assert_called_once()

    def test_bounded_owner_dispatch_gap_preserves_hormone_with_fresh_inputs(self):
        a=NormalAHM('C1');a.step(0.,1.);before=a.step(.1,1.)['h']
        r=a.step(.5,0.)  # a normal route may block 400ms, sensor worker remains fresh
        expected=before
        for _ in range(8):expected=.96*expected+.04
        self.assertAlmostEqual(r['h'],expected)
        self.assertNotEqual(r['reason'],'history_gap')

    def test_recoverable_wait_does_not_erase_h_if_worker_input_now_fresh(self):
        from bio_inspire.runtime.normal_ahm import update_from_owner
        src=Mock();src.diagnostics.return_value=dict(stable_pressed=False,last_sample_s=.15,sampler_error=None)
        m=SimpleNamespace(controller=SimpleNamespace(state='WAIT_TOF'),physical_touch=src,physical_button=src,
            distance_view=dict(distance_cm=35.,received_s=.15,error=None),distance_gate=SimpleNamespace(near=False))
        a=NormalAHM('C1');a.step(0.,1.);before=a.step(.1,1.)['h']
        self.assertGreater(update_from_owner(a,m,.15)['h'],before)

    def test_closing_reset_is_pure_no_driver_step_or_output(self):
        from state_rhythms import StateRhythms
        happy,afraid=Mock(),Mock()
        for driver in (happy,afraid):driver.rhythm=SimpleNamespace(modulation_status={})
        mod=NormalAHM('C1');mod.step(0.,1.);mod.step(.1,1.)
        d=StateRhythms(happy,afraid,normal_ahm=mod)
        d.breathing.rhythm.set_normal_ahm_phi(.12)
        d.reset_normal_ahm(.15)
        self.assertEqual(mod.h,0.)
        self.assertEqual(d.breathing.rhythm.phi,.1)
        happy.step.assert_not_called();afraid.step.assert_not_called()

    def test_shared_sampler_is_not_drained_and_near_only(self):
        def source(held):
            s=Mock();s.diagnostics.return_value=dict(stable_pressed=held,last_sample_s=1.,sampler_error=None)
            return s
        m=SimpleNamespace(physical_touch=source(False),physical_button=source(False),
            distance_view=dict(distance_cm=50.,received_s=1.,error=None),distance_gate=SimpleNamespace(near=False))
        self.assertEqual(read_stimulus(m,1.),0.)  # approach is not S
        m.distance_gate.near=True;m.distance_view['distance_cm']=25.
        self.assertEqual(read_stimulus(m,1.),1.)
        m.distance_view['distance_cm']=28.
        self.assertEqual(read_stimulus(m,1.),0.)
        m.distance_gate.near=False;m.physical_touch.diagnostics.return_value['stable_pressed']=True
        self.assertEqual(read_stimulus(m,1.),1.)
        m.physical_touch.diagnostics.return_value['stable_pressed']=False
        m.distance_view=dict(distance_cm=None,received_s=1.,error=None,measurement_state='no_target',range_status_raw=4)
        m.distance_gate.near=True
        self.assertEqual(read_stimulus(m,1.),0.)
        self.assertIsNone(read_stimulus(m,1.2))
        for s in (m.physical_touch,m.physical_button):
            s.poll.assert_not_called();s.drain_events.assert_not_called()

    def test_sampler_timestamp_tracks_samples_not_only_changes(self):
        from physical_button import BufferedInput
        s=BufferedInput(.06);s.sample(False,0.);s.sample(False,.1)
        self.assertEqual(s.diagnostics()['last_sample_s'],.1)

    def test_router_only_normal_modulates_and_preserves_phase_and_stop(self):
        from state_rhythms import StateRhythms
        from test_taught_crouch import Tests as Fixture
        m,b=Fixture().motor();m.behavior_trial='normal'
        mod=Mock();mod.step.return_value=dict(phi=.13,h=.8,stimulus=0.,condition='C1')
        happy,afraid=Mock(),Mock()
        for driver in (happy,afraid):driver.rhythm=SimpleNamespace(modulation_status={})
        d=StateRhythms(happy,afraid,normal_ahm=mod)
        d.step(m,20.);self.assertEqual(d.breathing.rhythm.phi,.13)
        for mode in ('interested','sleepy','angry','happy','afraid'):
            m.behavior_trial=mode;d.step(m,20.1)
            self.assertEqual(d.breathing.rhythm.phi,.1)
        m.behavior_trial='normal';d.step(m,20.2);updates=d.breathing.rhythm.updates
        m.operator_stopped=True;b.calls.clear();d.step(m,20.3)
        self.assertEqual(b.calls,[])
        self.assertGreater(d.breathing.rhythm.updates,updates)
        self.assertEqual(d.breathing.rhythm.phi,.1)

    def test_phi_setter_bounds_no_phase_reset_and_legacy_disabled(self):
        from body_rhythm import BodyRhythm
        a=BodyRhythm(phi=.1,time_scale=.5);a.advance(0.,True);a.advance(.2,True)
        previous=(a.o1,a.o2,a.updates,a.envelope)
        a.set_normal_ahm_phi(.115)
        self.assertEqual(previous,(a.o1,a.o2,a.updates,a.envelope))
        for v in (.099,.131,math.nan,True):
            with self.assertRaises(ValueError):a.set_normal_ahm_phi(v)
        with self.assertRaises(ValueError):BodyRhythm(phi=.13)

    def test_trial_config_requires_existing_owner_inputs_and_clock(self):
        self.assertIsNone(validate_trial_config({}))
        c=dict(normal_ahm_condition='C1',all_states_cpg_enabled=True,automatic_fsm_enabled=True,
               physical_button_enabled=True,physical_touch_enabled=True,physical_tof_enabled=True)
        self.assertEqual(validate_trial_config(c),'C1')
        for key in ('automatic_fsm_enabled','all_states_cpg_enabled','physical_touch_enabled'):
            with self.assertRaises(ValueError):validate_trial_config({**c,key:False})
        with self.assertRaises(ValueError):validate_trial_config({**c,'normal_ahm_condition':'bad'})


if __name__=='__main__':unittest.main()
