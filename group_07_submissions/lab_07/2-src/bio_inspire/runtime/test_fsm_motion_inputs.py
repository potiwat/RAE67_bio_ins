import unittest
import test_automatic_fsm as fixture
from automatic_fsm import AutomaticFSM
from unittest.mock import Mock

class Tests(unittest.TestCase):
    def test_approach_loss_does_not_clear_happy(self):
        m,b,s=fixture.Tests().motor();a=m.automatic_fsm;a.fsm.state='happy';a.applied='happy';a.approach=True;m.behavior_trial='happy';m.controller.pose_route=None
        for t in (20.1,20.8):fixture.Tests().at(m,s,t,distance_cm=None,measurement_state='no_target',range_status_raw=4)
        self.assertEqual(a.fsm.state,'happy')
    def test_body_motion_cannot_create_arrival_or_interrupt_normal_return(self):
        m,b,s=fixture.Tests().motor();a=m.automatic_fsm;a.approach=False;m.behavior_trial='normal_transition'
        fixture.Tests().at(m,s,20.1,distance_cm=43.)
        self.assertEqual(a.fsm.state,'normal')
        m.behavior_trial='normal';m.controller.pose_route=None
        fixture.Tests().at(m,s,20.2,distance_cm=43.);self.assertEqual(a.fsm.state,'normal')
        fixture.Tests().at(m,s,20.3,distance_cm=110.)
        fixture.Tests().at(m,s,20.4,distance_cm=43.);self.assertEqual(a.fsm.state,'interested')
    def test_near_and_real_clear_still_preempt_happy(self):
        m,b,s=fixture.Tests().motor();a=m.automatic_fsm;a.fsm.state='happy';a.applied='happy';m.behavior_trial='happy'
        fixture.Tests().at(m,s,20.1,distance_cm=10.);self.assertEqual(a.fsm.state,'afraid')
        fixture.Tests().at(m,s,20.2,distance_cm=40.);self.assertEqual(a.fsm.state,'normal')
    def test_approved_short_touch_pulses_become_three_presses_in_same_window(self):
        from physical_touch import reviewed_touch_debounce
        from physical_button import BufferedInput
        from angry_fsm import TouchBurst
        source=BufferedInput(reviewed_touch_debounce(.03));burst=TouchBurst();triggers=[]
        for n in range(101):
            t=n*.01;pressed=any(start<=t<start+.05 for start in (.1,.35,.6));source.sample(pressed,t)
        events=source.drain_events(1.)
        self.assertEqual(len(events),3)
        for t in events:triggers.append(burst.press(t,1.))
        self.assertEqual(triggers,[False,False,True])
        for bad in (True,.02,.01):
            with self.assertRaises(ValueError):reviewed_touch_debounce(bad)

    def test_angry_clock_waits_for_pose_instead_of_expiring_on_face_wait(self):
        from types import SimpleNamespace
        m,b,s=fixture.Tests().motor();a=AutomaticFSM(angry_enabled=True,motion_aware=True,active_timeout_s=5.)
        m.automatic_fsm=a;a.service(m,20.);a.fsm.state='angry';a.applied='angry'
        m.behavior_trial='angry_transition'
        m.controller.pose_route=SimpleNamespace(phase='lean',waiting_for_player=False,gaze_wait_elapsed_s=0.)
        fixture.Tests().at(m,s,28.)
        self.assertEqual(a.fsm.state,'angry');self.assertFalse(a.timer_ready(m))

    def test_genuine_angry_head_wait_has_bounded_failure_path(self):
        from types import SimpleNamespace
        m,b,s=fixture.Tests().motor();a=AutomaticFSM(angry_enabled=True,motion_aware=True,active_timeout_s=5.)
        m.automatic_fsm=a;a.service(m,20.);a.fsm.state='angry';a.applied='angry';m.behavior_trial='angry_transition'
        m.controller.pose_route=SimpleNamespace(phase='lean',waiting_for_player=True,gaze_wait_elapsed_s=5.,cancel=lambda:None)
        fixture.Tests().at(m,s,26.)
        self.assertEqual(a.fsm.state,'normal');self.assertEqual(a.fsm.last_winner['source_id'],'angry_head_wait_budget')

    def test_angry_level_return_cannot_defer_near_indefinitely(self):
        from types import SimpleNamespace
        m,b,s=fixture.Tests().motor();a=AutomaticFSM(angry_enabled=True,motion_aware=True,active_timeout_s=5.)
        m.automatic_fsm=a;a.service(m,20.);a.fsm.state='angry';a.applied='angry';m.behavior_trial='angry_transition'
        m.controller.pose_route=SimpleNamespace(phase='return',angry_level_started_s=20.,cancel=lambda:None)
        fixture.Tests().at(m,s,31.9)
        self.assertEqual(a.fsm.state,'angry')
        fixture.Tests().at(m,s,32.1)
        self.assertEqual(a.fsm.state,'normal');self.assertEqual(a.fsm.last_winner['source_id'],'angry_level_entry_budget')
