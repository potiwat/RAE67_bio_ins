import unittest
from types import SimpleNamespace
from .interested_coordination import lead_scale,pitch_service


class Tests(unittest.TestCase):
    def test_anticipation_starts_at_zero_and_stays_below_unchanged_lag_gate(self):
        r=SimpleNamespace();values=[lead_scale(r,204.,20+i*.01)for i in range(61)]
        self.assertEqual(values[0],0.)
        self.assertEqual(values,sorted(values))
        self.assertAlmostEqual(values[-1]*204,26.)
        self.assertLess(values[-1]*204,34.)
        self.assertLess(max(b-a for a,b in zip(values,values[1:])),.005)

    def test_near_endpoint_never_predicts_past_it_and_new_route_restarts_ramp(self):
        for distance in (0.,1.,12.,26.,60.,400.):
            r=SimpleNamespace();lead_scale(r,distance,20.)
            prediction=distance*lead_scale(r,distance,21.)
            self.assertGreaterEqual(prediction,0.)
            self.assertLessEqual(prediction,min(distance,26.))
        self.assertEqual(lead_scale(SimpleNamespace(),200.,30.),0.)

    def test_only_selected_pitch_method_is_cloned_without_changing_original(self):
        from bio_inspire.runtime.camera_motor import CameraMotor
        original=CameraMotor._apply_pitch;trial=pitch_service(original)
        self.assertIs(CameraMotor._apply_pitch,original)
        self.assertIsNot(original,trial)
        self.assertIn('_trial_interested_lead_scale',trial.__code__.co_names)
        self.assertNotIn('_trial_interested_lead_scale',original.__code__.co_names)


if __name__=='__main__':unittest.main()
