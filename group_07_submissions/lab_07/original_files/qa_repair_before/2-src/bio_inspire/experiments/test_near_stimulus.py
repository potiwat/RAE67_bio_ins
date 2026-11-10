import unittest
from bio_inspire.experiments.ahm_input_bridge import InputFrame, InputAdapter, EmotionAdapter
from bio_inspire.experiments.recorded_input_ros import CPGPair


def f(t,d=.5,**kw):return InputFrame(t,t,kw.get('button',False),kw.get('touch',False),'range',d,str(t))


class NearStimulusTests(unittest.TestCase):
    def test_approach_can_enter_interested_without_sustained_stimulus(self):
        row=EmotionAdapter().step(InputAdapter().step(f(0)))
        self.assertEqual(row['emotion'],'interested')
        self.assertTrue(row['approach'])
        self.assertEqual(row['stimulus'],0.)

    def test_near_stimulus_stays_until_clear_even_inside_approach(self):
        a=InputAdapter()
        self.assertEqual(a.step(f(0,.2))['stimulus'],1.)
        self.assertEqual(a.step(f(.05,.279))['stimulus'],1.)
        row=a.step(f(.1,.28))
        self.assertTrue(row['approach'])
        self.assertFalse(row['near'])
        self.assertEqual(row['stimulus'],0.)

    def test_button_and_touch_still_follow_debounced_held_input(self):
        for channel in ('button','touch'):
            a=InputAdapter();a.step(f(0,**{channel:True}))
            self.assertEqual(a.step(f(.1,**{channel:True}))['stimulus'],1.)
            a.step(f(.2))
            self.assertEqual(a.step(f(.3))['stimulus'],0.)

    def test_clear_stops_production_without_zeroing_accumulated_hormone(self):
        a=InputAdapter();p=CPGPair()
        for k in range(60):p.step(a.step(f(k*.05,.15))['stimulus'])
        before=p.states['C1'][2]
        row=a.step(f(3.,.5));result=p.step(row['stimulus'])
        self.assertEqual(row['stimulus'],0.)
        self.assertEqual(result['C1']['h'],before)
        self.assertAlmostEqual(result['C1']['h_next'],.96*before)
        self.assertGreater(result['C1']['h_next'],0.)
        self.assertEqual(result['C0']['phi_rad_per_update'],.2)
        self.assertGreater(result['C1']['phi_rad_per_update'],.2)

    def test_legacy_policy_is_explicit_and_unknown_names_rejected(self):
        self.assertEqual(InputAdapter(stimulus_policy='approach_or_near_v1').step(f(0))['stimulus'],1.)
        with self.assertRaises(ValueError):InputAdapter(stimulus_policy='unknown')


if __name__=='__main__':unittest.main()
