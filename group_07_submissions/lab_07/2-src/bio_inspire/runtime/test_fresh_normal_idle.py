import unittest
from types import SimpleNamespace
from automatic_fsm import AutomaticFSM
from angry_fsm import AngryFSM
class Tests(unittest.TestCase):
    def test_fresh_start_default_normal_is_timer_ready(self):
        a=AutomaticFSM(motion_aware=True,sleep_after_s=10.,angry_enabled=True)
        a.fsm=AngryFSM(0.,motion_aware=True,sleep_after_s=10.)
        m=SimpleNamespace(controller=SimpleNamespace(pose_route=None),pending_behavior=None)
        self.assertTrue(a.timer_ready(m))
        a.fsm.step(0.,[],ready=a.timer_ready(m))
        self.assertEqual(a.fsm.step(10.,[],ready=a.timer_ready(m))['new_state'],'sleepy')
    def test_explicit_transition_is_still_not_ready(self):
        a=AutomaticFSM();a.fsm=AngryFSM(0.)
        m=SimpleNamespace(controller=SimpleNamespace(pose_route=None),pending_behavior=None,behavior_trial='normal_transition')
        self.assertFalse(a.timer_ready(m))
