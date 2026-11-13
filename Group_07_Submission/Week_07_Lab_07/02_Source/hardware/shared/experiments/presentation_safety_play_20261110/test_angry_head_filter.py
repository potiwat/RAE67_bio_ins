import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock,patch
from .angry_head_filter import filtered_goal,goal_pitch


class Tests(unittest.TestCase):
    def test_step_is_monotonic_bounded_and_converges_without_overshoot(self):
        state=None;goals=[]
        for k in range(51):
            state,out=filtered_goal(state,2700,2600,20+k*.02);goals.append(out)
        self.assertEqual(goals[0],2700);self.assertEqual(goals[-1],2600)
        self.assertEqual(goals,sorted(goals,reverse=True))
        self.assertTrue(all(2600<=q<=2700 for q in goals))

    def test_stop_and_other_emotions_pass_to_original_unchanged(self):
        original=Mock(return_value=True);wrapped=goal_pitch(original)
        for state,phase,stop in (('READY','return',False),('FAULT','advance',False),('READY','advance',True)):
            route=NS(completion_behavior='angry',heading_saved=True,range_phase=phase,safety_hold=stop,_cancelled=lambda:False)
            c=NS(pose_route=route,state=state,pitch_tracking_enabled=True)
            wrapped(c,2500);self.assertEqual(original.call_args.args,(c,2500))
            self.assertFalse(hasattr(route,'trial_head_filter'))

    def test_invalid_goal_is_not_hidden_by_filter_and_no_new_uart_reads(self):
        original=Mock(return_value=True)
        route=NS(completion_behavior='angry',heading_saved=True,range_phase='advance',safety_hold=False,_cancelled=lambda:False,m=NS(now=lambda:20.))
        c=NS(pose_route=route,state='READY',pitch_tracking_enabled=True,active_pitch_window=lambda:(2200,2800),last_pitch_goal=2700,bus=NS())
        wrapped=goal_pitch(original);wrapped(c,9000)
        self.assertEqual(original.call_args.args,(c,9000))
        self.assertFalse(hasattr(route,'trial_head_filter'))
        wrapped(c,2600);self.assertEqual(original.call_args.args,(c,2700))
        self.assertEqual(c.last_pitch_goal,2700)

    def test_angry_stop_reset_and_auto_resume_still_use_existing_safety(self):
        from normal_gaze_motor import NormalGaze
        from .test_auto_release import AutoReleaseTests
        with patch.object(NormalGaze,'goal_pitch',goal_pitch(NormalGaze.goal_pitch)):
            result,w=AutoReleaseTests().run_case('angry',2)
        self.assertIsNone(result['error'])
        self.assertTrue(getattr(w,'resumed',False))
        self.assertTrue(result['cleanup_confirmed'])
        self.assertEqual(result['reset']['h'],0.)
        self.assertTrue(all(v['updates']==0 for v in result['reset']['bank'].values()))


if __name__=='__main__':unittest.main()
