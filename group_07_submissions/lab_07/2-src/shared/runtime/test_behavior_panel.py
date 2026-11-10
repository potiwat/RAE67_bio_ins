import unittest
from types import SimpleNamespace
from behavior_panel import BehaviorPanel

class Tests(unittest.TestCase):
    def test_afraid_button_is_opt_in_and_preserves_stop(self):
        cv=SimpleNamespace(EVENT_LBUTTONUP=4,setMouseCallback=lambda *a:None)
        p=BehaviorPanel(cv,'window',afraid_enabled=True);p.width=600;p.top=180
        p.click(4,450,190,0,None);self.assertEqual(p.take(255),ord('f'))
        p.click(4,550,190,0,None);self.assertEqual(p.take(255),ord('h'))
    def test_cpg_slider_stages_decimal_gain_and_only_dispatches_to_motor_owner(self):
        from unittest.mock import Mock
        cv=SimpleNamespace(EVENT_LBUTTONUP=4,EVENT_LBUTTONDOWN=1,EVENT_MOUSEMOVE=0,EVENT_FLAG_LBUTTON=1,setMouseCallback=lambda *a:None)
        p=BehaviorPanel(cv,'window',cpg_amplitude=2.);p.width=320;p.top=180
        p.click(1,16,250,1,None);self.assertEqual(p.cpg_amplitude,1.)
        p.click(0,304,250,1,None);self.assertEqual(p.cpg_amplitude,3.)
        p.click(4,218,250,0,None);self.assertEqual(p.cpg_amplitude,2.4)
        p.dispatch(None)
        m=Mock();m.request_rhythm_amplitude.return_value=True
        p.dispatch(m);p.dispatch(m)
        m.request_rhythm_amplitude.assert_called_once_with(2.4)

    def test_clicks_are_one_explicit_request_and_do_not_move_from_preview(self):
        cv=SimpleNamespace(EVENT_LBUTTONUP=4,setMouseCallback=lambda *a:None)
        p=BehaviorPanel(cv,'window');p.width=320;p.top=180
        p.click(4,10,190,0,None);self.assertEqual(p.take(255),ord('m'))
        self.assertEqual(p.take(255),255)
        p.normal_key=ord('n');p.click(4,10,190,0,None);self.assertEqual(p.take(255),ord('n'))
        p.click(4,110,190,0,None);self.assertEqual(p.take(255),ord('i'))
        p.click(4,160,190,0,None);self.assertEqual(p.take(255),ord('d'))
        p.click(4,230,190,0,None);self.assertEqual(p.take(255),ord('s'))
        p.click(4,300,190,0,None);self.assertEqual(p.take(255),ord('h'))
        p.click(4,100,20,0,None);self.assertEqual(p.take(255),255)
