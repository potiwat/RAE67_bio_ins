"""Real runtime pipeline in the no-hardware plant, not just trajectory maths."""
import unittest
from contextlib import ExitStack
from unittest.mock import patch
from bio_inspire.runtime import sleepy_trial,angry_approach,camera_motor
from . import sleepy_smooth,test_integration as fixture
from .sleepy_coordination import sleepy_setter,coordinated_driver
from .interested_coordination import pitch_service
from .angry_coordination import coordinated_route
from shared.experiments.central_safety_controller_20261110.scenarios import contact_in_state


class Tests(unittest.TestCase):
    def test_all_six_states_auto_recover_all_three_contact_axes_without_r(self):
        from . import test_auto_release
        for state in ('normal','interested','happy','angry','afraid','sleepy'):
            for sid in (1,2,4):
                with self.subTest(state=state,id=sid),patch.object(
                        angry_approach,'AngryApproachRoute',coordinated_route(angry_approach.AngryApproachRoute)):
                    result,w=test_auto_release.AutoReleaseTests().run_case(state,sid)
                    self.assertIsNone(result['error'])
                    self.assertTrue(getattr(w,'resumed',False))
                    self.assertTrue(result['cleanup_confirmed'])
                    self.assertEqual(result['reset']['h'],0.)
                    self.assertTrue(all(v['updates']==0 for v in result['reset']['bank'].values()))
                    self.assertNotIn('OPERATOR_CLEARANCE_R',[v['event']for v in result['events']])

    def test_affected_states_still_stop_reset_and_return_on_each_contact_axis(self):
        for state in ('interested','sleepy','angry'):
            for sid in (1,2,4):
                with self.subTest(state=state,id=sid),ExitStack()as stack:
                    stack.enter_context(patch.object(angry_approach,'AngryApproachRoute',coordinated_route(angry_approach.AngryApproachRoute)))
                    def after(w):
                        a=w.motor.bus.central_feedback.brake_capture
                        if a.core.phase=='WAIT_CLEARANCE'and a.sensor_state()=='clear'and a.stopped():
                            w.motor.key(ord('r'))
                    result,w=fixture.run(contact_in_state(state,sid,after),seconds=35)
                    self.assertEqual(result['phase'],'NORMAL_PARKED',result['error'])
                    self.assertTrue(result['cleanup_confirmed'])
                    self.assertEqual(result['reset']['h'],0.)
                    self.assertTrue(all(v['updates']==0 for v in result['reset']['bank'].values()))
                    self.assertEqual(result['final_goals'],result['normal'])
                    self.assertTrue(result['source_profile_unchanged'])


if __name__=='__main__':unittest.main()
