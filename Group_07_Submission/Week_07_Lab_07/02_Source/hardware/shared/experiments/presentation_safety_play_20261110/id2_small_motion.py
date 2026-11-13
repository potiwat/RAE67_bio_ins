"""Pinned small-goal diagnostic plan; no motor access, compensation or PID."""
import math


class SmallMotionPlan:
    OFFSETS = (0, 4, 0, -4, 0, 8, 0, -8, 0)

    def __init__(self, goal, encoder, window):
        lo, hi = window
        if (type(goal) is not int or type(encoder) is not int or
            abs(goal-encoder) > 22 or
            any(not lo <= goal+d <= hi for d in self.OFFSETS)):
            raise ValueError('Small-motion entry/bounds not qualified')
        self.anchor_goal, self.anchor_q = goal, encoder
        self.goal, self.last = goal, None

    def step(self, elapsed):
        if (type(elapsed) not in (int, float) or not math.isfinite(elapsed) or
            elapsed < 0 or self.last is not None and elapsed < self.last):
            raise ValueError('Invalid diagnostic clock')
        self.last = elapsed
        stage = min(8, int(elapsed // 2))
        target = self.anchor_goal+self.OFFSETS[stage]
        self.goal += max(-1, min(1, target-self.goal))
        return dict(stage=stage, target=target, goal=self.goal, done=elapsed >= 18.)
