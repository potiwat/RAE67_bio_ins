import unittest
from angry_fsm import AngryFSM
from small_happy_trial import SmallHappyTrial

class Tests(unittest.TestCase):
    def test_happy7_other_active5(self):
        for state,timeout in [('happy',7.),('interested',5.),('angry',5.)]:
            f=AngryFSM(0.,active_timeout_s=5.,happy_timeout_s=7.)
            f.state=state
            self.assertIsNone(f.step(timeout-.01,[]))
            self.assertEqual(f.step(timeout,[])['new_state'],'normal')
    def test_roll8_exact_limit(self):
        d=SmallHappyTrial(expanded=True,roll_deg=8)
        self.assertEqual(d.roll_ticks,91)
        with self.assertRaises(ValueError):SmallHappyTrial(expanded=False,roll_deg=8)

    def test_motion_aware_happy_clock_starts_when_ready(self):
        f=AngryFSM(0.,active_timeout_s=5.,happy_timeout_s=7.,motion_aware=True)
        f.state='happy'
        f.step(10.,[],ready=False);f.step(11.,[],ready=True)
        self.assertIsNone(f.step(17.99,[],ready=True))
        self.assertEqual(f.step(18.,[],ready=True)['new_state'],'normal')
    def test_eight_degree_roll_commands_and_feedback_share_limits(self):
        import test_small_happy_trial as fixture
        m,b,_=fixture.Tests().fixture();d=SmallHappyTrial(expanded=True,roll_deg=8)
        requested=[]
        for n in range(301):
            now=n*.05;m.latest_result['observation']['captured_s']=now;d.step(m,now)
            b.pos={i:b.reg[i][42] for i in b.pos};m.controller.last_rows=b.snapshot()
            if n>50:requested.append(d.rhythm.status()['requested_targets_float'][4]-m.controller.normal[4])
        self.assertLess(min(requested),-85);self.assertGreater(max(requested),85)
        self.assertEqual(d.limiters[4].limits.low,m.controller.normal[4]-91)
        self.assertEqual(d.limiters[4].limits.high,m.controller.normal[4]+91)
        self.assertLessEqual(m.controller.behavior_joint_windows[4][0],m.controller.normal[4]-91)
