import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from .angry_coordination import coordinated_route


class Base:
    def __init__(self):
        self.pending_sync_goals={2:2633,3:2950};self.endpoints=dict(self.pending_sync_goals)
        self.c=SimpleNamespace(last_rows=[dict(id=2,goal_raw=2837),dict(id=3,goal_raw=2746)],
                               last_joint_targets={},bus=object())
        self.m=SimpleNamespace(now=lambda:20.)
        self.phase='lean';self.range_phase='advance';self.safety_hold=False
    def commit_pending_head(self,goal):
        self.initial=dict(self.pending_sync_goals);self.pending_sync_goals=None;return True
    def _cancelled(self):return False
    def step(self,rows):pass


class Tests(unittest.TestCase):
    def test_launch_uses_current_command_not_full_endpoint(self):
        r=coordinated_route(Base)();r.commit_pending_head(2700)
        self.assertEqual(r.initial,{2:2837,3:2746})
        self.assertEqual(r.endpoints,{2:2633,3:2950})
        trace=[r.trial_arm_goals(20+k*.05)for k in range(81)]
        self.assertEqual(trace[-1],r.endpoints)
        for i in (2,3):
            a=[q[i]for q in trace]
            self.assertEqual(a,sorted(a,reverse=i==2))
            self.assertLessEqual(max(abs(x-y)for x,y in zip(a,a[1:])),5)

    def test_short_native_entry_budget_keeps_original_goal_and_limits(self):
        r=coordinated_route(Base)();r.started_s=10.
        r.commit_pending_head(2700)
        self.assertEqual(r.initial,r.endpoints)
        self.assertIsNone(r.trial_arm_start)
        self.assertIsNotNone(r.trial_arm_fallback)

    def test_stop_pause_and_native_range_guard_preempt_stream(self):
        for mode in ('cancelled','paused','safety_hold','finished'):
            r=coordinated_route(Base)();r.commit_pending_head(2700)
            if mode=='cancelled':r._cancelled=lambda:True
            elif mode=='paused':r.range_phase='paused'
            elif mode=='safety_hold':r.safety_hold=True
            else:r.phase='complete'
            with patch('shared.experiments.presentation_safety_play_20261110.angry_coordination.write_positions')as write:
                r.step([]);write.assert_not_called()

    def test_same_tick_goals_are_not_resent(self):
        r=coordinated_route(Base)();r.commit_pending_head(2700)
        with patch('shared.experiments.presentation_safety_play_20261110.angry_coordination.write_positions',return_value={})as write:
            r.step([]);r.step([]);self.assertEqual(write.call_count,1)


if __name__=='__main__':unittest.main()
