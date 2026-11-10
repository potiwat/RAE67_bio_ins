import unittest
from physical_button import ButtonEdge

class Tests(unittest.TestCase):
    def test_press_release_debounce_and_no_repeat_while_held(self):
        b=ButtonEdge(.06)
        self.assertFalse(b.update(False,0));self.assertFalse(b.update(False,.07))
        self.assertFalse(b.update(True,.1));self.assertFalse(b.update(False,.12))
        self.assertFalse(b.update(True,.13));self.assertTrue(b.update(True,.20))
        self.assertFalse(b.update(True,3))
        self.assertFalse(b.update(False,4));self.assertFalse(b.update(False,4.07))
        self.assertFalse(b.update(True,5));self.assertTrue(b.update(True,5.07))
    def test_initial_held_button_never_starts_motion_until_release_and_new_press(self):
        b=ButtonEdge(.06)
        for t in (0,.1,1):self.assertFalse(b.update(True,t))
        b.update(False,2);b.update(False,2.1);b.update(True,3)
        self.assertTrue(b.update(True,3.1))

class BufferedPressTests(unittest.TestCase):
    def test_queue_overflow_is_reported_separately_from_intentional_discard(self):
        from physical_button import BufferedInput
        s=BufferedInput(.06);s.sample(False,0);s.sample(False,.07)
        for n in range(200):
            t=.1+n*.4
            for pressed,stamp in ((True,t),(True,t+.07),(False,t+.1),(False,t+.17)):s.sample(pressed,stamp)
        d=s.diagnostics()
        self.assertEqual(d['pending_count'],180);self.assertEqual(d['overflow_presses'],20)
        self.assertEqual(d['discarded_presses'],0)
    def test_drain_returns_every_source_timestamp_once_and_reports_raw_edges(self):
        from physical_button import BufferedInput
        s=BufferedInput(.06)
        for pressed,t in ((False,0),(False,.07),(True,.08),(True,.15),(False,.16),(False,.23),
                          (True,.24),(True,.31),(False,.32),(False,.39),(True,.40),(True,.47)):
            s.sample(pressed,t)
        self.assertEqual(s.drain_events(.6),[.08,.24,.40])
        self.assertEqual(s.drain_events(.61),[])
        d=s.diagnostics();self.assertEqual(d['accepted_presses'],3);self.assertEqual(d['pending_count'],0)
        self.assertEqual(len(d['raw_edges']),6)
        s.sample(True,1.);self.assertEqual(s.drain_events(1.),[])
    def test_short_raw_pulse_is_visible_even_when_rejected_by_unchanged_debounce(self):
        from physical_button import BufferedInput
        s=BufferedInput(.06)
        for pressed,t in ((False,0),(False,.07),(True,.1),(False,.12),(False,.2)):s.sample(pressed,t)
        self.assertEqual(s.drain_events(.3),[])
        d=s.diagnostics();self.assertEqual(d['accepted_presses'],0)
        self.assertAlmostEqual(d['raw_edges'][-1]['previous_duration_s'],.02)
        for n in range(100):s.sample(n%2,1+n*.01)
        self.assertLessEqual(len(s.diagnostics()['raw_edges']),24)
    def test_two_short_presses_survive_busy_motor_loop(self):
        from physical_button import BufferedInput
        s=BufferedInput(.06)
        for pressed,t in ((False,0),(False,.07),(True,.08),(True,.15),(False,.16),(False,.23),(True,.24),(True,.31)):
            s.sample(pressed,t)
        self.assertTrue(s.poll(.6));self.assertEqual(s.last_event_s,.08)
        self.assertTrue(s.poll(.61));self.assertEqual(s.last_event_s,.24)
        self.assertFalse(s.poll(.62))
    def test_sampler_stops_before_device_cleanup(self):
        from physical_button import BufferedInput
        import threading
        s=BufferedInput(.06);read_seen=threading.Event()
        def read():read_seen.set();return False
        s.start_sampling(read)
        self.assertTrue(read_seen.wait(1.))
        s.stop_sampling();self.assertFalse(s.sampler.is_alive())
