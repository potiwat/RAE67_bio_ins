import unittest,threading
from types import SimpleNamespace
from physical_button import BufferedInput
from lab07_start_gate import ButtonStartGate,validate_gate

class Tests(unittest.TestCase):
    def fixture(self):
        button=BufferedInput(.06);touch=BufferedInput(.03)
        m=SimpleNamespace(controller=SimpleNamespace(state='READY'),behavior_trial='normal',operator_stopped=False,
                          stopping=threading.Event(),urgent_stop=threading.Event(),physical_button=button,physical_touch=touch)
        self.t=1.;button.sample(False,self.t);button.sample(False,self.t+.07)
        touch.sample(False,self.t);touch.sample(False,self.t+.07);self.t+=.1
        g=ButtonStartGate();g.observe(m,self.t)
        return m,g
    def edge(self,m,g,pressed):
        self.t+=.1;m.physical_button.sample(pressed,self.t)
        self.t+=.07;m.physical_button.sample(pressed,self.t);g.observe(m,self.t)
    def test_five_releases_start_and_are_consumed(self):
        m,g=self.fixture()
        for n in range(5):
            self.edge(m,g,True);self.assertFalse(g.started)
            self.edge(m,g,False);self.assertEqual(g.count,n+1)
        self.assertTrue(g.started);self.assertEqual(g.started_s,self.t)
        self.assertFalse(m.physical_button.drain_events(self.t))
        self.edge(m,g,True)
        self.assertEqual(len(m.physical_button.drain_events(self.t)),1)
    def test_held_button_and_bounce_do_not_count_multiple_times(self):
        m,g=self.fixture();self.edge(m,g,True)
        for _ in range(20):
            self.t+=.1;m.physical_button.sample(True,self.t);g.observe(m,self.t)
        self.assertEqual(g.count,0)
        self.edge(m,g,False);self.assertEqual(g.count,1)
        self.t+=.1;m.physical_button.sample(True,self.t)
        self.t+=.01;m.physical_button.sample(False,self.t);g.observe(m,self.t)
        self.assertEqual(g.count,1)
    def test_press_held_before_ready_is_not_a_completed_start_press(self):
        m,g=self.fixture();g=ButtonStartGate()
        self.t+=.1;m.physical_button.sample(True,self.t)
        self.t+=.07;m.physical_button.sample(True,self.t);g.observe(m,self.t)
        self.edge(m,g,False)
        self.assertEqual(g.count,0)
        self.edge(m,g,True);self.edge(m,g,False)
        self.assertEqual(g.count,1)
    def test_stop_or_unready_cannot_start(self):
        for kind in ('operator_stopped','urgent_stop','unready','near'):
            m,g=self.fixture()
            for _ in range(4):self.edge(m,g,True);self.edge(m,g,False)
            if kind=='operator_stopped':m.operator_stopped=True
            elif kind=='urgent_stop':m.urgent_stop.set()
            elif kind=='near':m.distance_gate=SimpleNamespace(near=True)
            else:m.controller.state='WAIT_TOF'
            self.edge(m,g,True);self.edge(m,g,False)
            self.assertFalse(g.started)
    def test_flag_only_valid_for_recorded_five_button_mode(self):
        self.assertFalse(validate_gate({}))
        self.assertTrue(validate_gate(dict(lab07_recording_seconds=180,lab07_start_button_presses=5,physical_button_enabled=True,automatic_fsm_enabled=True)))
        for value in (True,4,6):
            with self.assertRaises(ValueError):validate_gate(dict(lab07_recording_seconds=180,lab07_start_button_presses=value))
    def test_led_stays_off_until_measurement_starts(self):
        from unittest.mock import Mock,patch
        from three_state_behavior import service_state_outputs
        m,g=self.fixture();m.lab07_start_gate=g;m.led_ring=Mock()
        previous=m.led_ring;m.last_led_behavior=None;m.state_leds_enabled=True
        service_state_outputs(m)
        previous.close.assert_called_once();self.assertIsNone(m.led_ring)
        with patch('led_ring.LedRing') as factory:
            service_state_outputs(m);factory.assert_not_called()
            g.started=True;service_state_outputs(m)
            factory.return_value.normal.assert_called_once()
            self.assertEqual(m.last_led_behavior,'normal')

if __name__=='__main__':unittest.main()
