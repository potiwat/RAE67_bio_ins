"""Real sampler histories must survive a busy motion owner."""
import unittest
from types import SimpleNamespace
from physical_button import BufferedInput
from bio_inspire.runtime.normal_ahm import NormalAHM, update_from_owner


class Tests(unittest.TestCase):
    def setup_owner(self):
        self.button=BufferedInput(.06);self.touch=BufferedInput(.06)
        self.now=.08
        for source in (self.button,self.touch):
            source.sample(False,0.);source.sample(False,.08)
        self.m=SimpleNamespace(controller=SimpleNamespace(state='READY'),
            physical_button=self.button,physical_touch=self.touch,
            distance_view=dict(distance_cm=50.,received_s=.08,error=None),
            distance_gate=SimpleNamespace(near=False),now=lambda:self.now)
        self.a=NormalAHM('C1')
        update_from_owner(self.a,self.m,self.now)

    def observe(self,now):
        self.now=now;self.m.distance_view['received_s']=now
        for source in (self.button,self.touch):source.sample(source.raw_level,now)
        return update_from_owner(self.a,self.m,now)

    def test_press_release_inside_blocking_dispatch_matches_unblocked_teacher_clock(self):
        self.setup_owner()
        for pressed,t in ((True,.1),(True,.18),(False,.38),(False,.46)):
            self.button.sample(pressed,t)
        result=self.observe(.5)
        reference=NormalAHM('C1');reference.step(.08,0.)
        reference.step(.18,1.);reference.step(.46,0.)
        expected=reference.step(.5,0.)
        self.assertGreater(result['h'],0.)
        self.assertAlmostEqual(result['callback_gap_s'],.42)
        self.assertAlmostEqual(result['h'],expected['h'],places=13)
        self.assertEqual(self.button.drain_events(.5),[.1])
        # A second observation cannot replay the same pulse.
        self.assertAlmostEqual(self.observe(.55)['h'],reference.step(.55,0.)['h'],places=13)

    def test_stop_discards_pulses_without_rearming_or_replaying_them(self):
        self.setup_owner();self.m.operator_stopped=True
        for pressed,t in ((True,.1),(True,.18),(False,.38),(False,.46)):
            self.button.sample(pressed,t)
        self.assertEqual(self.observe(.5)['h'],0.)
        self.m.operator_stopped=False
        self.assertEqual(self.observe(.55)['h'],0.)

    def test_overlapping_channels_use_or_and_simultaneous_handoff(self):
        self.setup_owner()
        for source,pressed,t in ((self.button,True,.1),(self.button,True,.18),
                (self.button,False,.3),(self.touch,True,.3),
                (self.button,False,.38),(self.touch,True,.38),
                (self.touch,False,.5),(self.touch,False,.58)):
            source.sample(pressed,t)
        result=self.observe(.65)
        reference=NormalAHM('C1');reference.step(.08,0.)
        for stamp,s in ((.18,1.),(.38,1.),(.58,0.),(.65,0.)):expected=reference.step(stamp,s)
        self.assertAlmostEqual(result['h'],expected['h'],places=13)

    def test_bounded_history_overflow_resets_instead_of_inventing_a_hold(self):
        self.setup_owner()
        from collections import deque
        self.button.stable_edges=deque(self.button.stable_edges,maxlen=1)
        for pressed,t in ((True,.1),(True,.18),(False,.38),(False,.46)):
            self.button.sample(pressed,t)
        result=self.observe(.5)
        self.assertEqual(result['reason'],'input_history_overflow')
        self.assertEqual(result['h'],0.)

    def test_new_near_is_not_backdated_over_gpio_history(self):
        self.setup_owner()
        for pressed,t in ((True,.1),(True,.18),(False,.38),(False,.46)):
            self.button.sample(pressed,t)
        self.m.distance_view['distance_cm']=18.
        result=self.observe(.5)
        reference=NormalAHM('C1');reference.step(.08,0.)
        reference.step(.18,1.);reference.step(.46,0.)
        expected=reference.step(.5,1.)
        self.assertAlmostEqual(result['h'],expected['h'],places=13)
        self.assertEqual(result['stimulus'],1.)


if __name__=='__main__':unittest.main()
