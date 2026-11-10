import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from body_rhythm import BodyRhythm
from state_rhythms import StateRhythms, apply_bank_phi
from normal_ahm import validate_trial_config
import test_taught_crouch as fixture


class Tests(unittest.TestCase):
    def drivers(self):
        a,b=Mock(),Mock()
        for driver in (a,b):driver.rhythm=BodyRhythm(phi=.1,time_scale=.5)
        mod=Mock();mod.step.return_value=dict(phi=.13,h=.8,stimulus=1.,condition='C1')
        return StateRhythms(a,b,normal_ahm=mod,ahm_scope='all_states'),mod

    def test_all_six_states_receive_one_shared_hormone_without_phase_reset(self):
        d,mod=self.drivers();m,b=fixture.Tests().motor()
        for n,state in enumerate(('normal','interested','happy','sleepy','afraid','angry')):
            m.behavior_trial=state
            before=[r.updates for r in (d.happy.rhythm,d.afraid.rhythm)]
            d.step(m,20+n)
            for r in (d.breathing.rhythm,d.happy.rhythm,d.afraid.rhythm):self.assertEqual(r.phi,.13)
            self.assertEqual(before,[r.updates for r in (d.happy.rhythm,d.afraid.rhythm)])
            self.assertEqual(d.rhythm.status()['state_ahm']['state'],state)
        self.assertEqual(mod.step.call_count,6)

    def test_stop_restores_every_bank_member_and_never_writes_goals(self):
        d,mod=self.drivers();m,b=fixture.Tests().motor();m.behavior_trial='normal'
        d.step(m,20.);m.operator_stopped=True;b.calls.clear();d.step(m,20.1)
        self.assertEqual(b.calls,[])
        self.assertEqual([d.breathing.rhythm.phi,d.happy.rhythm.phi,d.afraid.rhythm.phi],[.1]*3)
        d.reset_normal_ahm(20.2)
        self.assertEqual(d.rhythm.status()['state_ahm']['applied'],False)

    def test_bank_setter_validates_before_any_mutation(self):
        bank={name:BodyRhythm(phi=.1) for name in ('body','happy','afraid')}
        apply_bank_phi(bank,.12)
        self.assertEqual([r.phi for r in bank.values()],[.12]*3)
        with self.assertRaises(ValueError):apply_bank_phi(bank,.14)
        self.assertEqual([r.phi for r in bank.values()],[.12]*3)

    def test_unknown_scope_rejected_and_default_profile_unchanged(self):
        with self.assertRaises(ValueError):StateRhythms(Mock(),Mock(),ahm_scope='other')
        with self.assertRaises(ValueError):validate_trial_config(dict(ahm_scope='all_states'))
        self.assertIsNone(validate_trial_config({}))

    def test_real_hormone_carries_across_all_state_changes_then_stop_resets(self):
        from normal_ahm import NormalAHM
        from unittest.mock import patch
        d,_=self.drivers();d.normal_ahm=NormalAHM('C1');m,b=fixture.Tests().motor()
        old=-1.
        with patch('bio_inspire.runtime.normal_ahm.read_stimulus',return_value=1.):
            for n,state in enumerate(('normal','interested','happy','sleepy','afraid','angry')):
                m.behavior_trial=state;d.step(m,20+n*.05)
                self.assertGreater(d.normal_ahm.h,old);old=d.normal_ahm.h
            m.operator_stopped=True;d.step(m,20.3)
        self.assertEqual(d.normal_ahm.h,0.)

    def test_real_six_state_decoders_keep_reviewed_bounds_and_stop(self):
        from small_happy_trial import SmallHappyTrial
        from afraid_rhythm import AfraidRhythm
        from afraid_pose import enter_afraid
        from visual_servo import VisualServo
        for state in ('normal','interested','happy','sleepy','afraid','angry'):
            with self.subTest(state=state):
                m,b=fixture.Tests().motor();c=m.controller;c.set_direction(1)
                m.visual=VisualServo(c.yaw_window[0],c.yaw_window[1],399.,296.,.25,6.,160.,.5)
                m.happy_yaw_base=c.normal[1];m.happy_body_acceleration_raw=3
                if state=='afraid':
                    enter_afraid(m);c.tick(30.)
                    for _ in range(3):
                        b.pos={i:b.reg[i][42] for i in range(1,6)};c.tick(c.last_tick+.1)
                else:m.behavior_trial=state
                mod=Mock();mod.step.return_value=dict(phi=.13,h=.8,stimulus=1.,condition='C1')
                d=StateRhythms(SmallHappyTrial(time_scale=.75,expanded=True,roll_deg=8),AfraidRhythm(),normal_ahm=mod,ahm_scope='all_states')
                for n in range(121):
                    now=31+n*.05
                    m.latest_result=dict(observation=dict(status='TRACKING',captured_s=now,source_id=n),intent=dict(mode='FOLLOW',error_xy=(0.,0.)))
                    d.step(m,now)
                    for i,address,value in b.calls:
                        if address==42:self.assertTrue(b.windows[i][0]<=value<=b.windows[i][1])
                    b.calls.clear()
                m.urgent_stop.set();d.step(m,38.);self.assertEqual(b.calls,[])
