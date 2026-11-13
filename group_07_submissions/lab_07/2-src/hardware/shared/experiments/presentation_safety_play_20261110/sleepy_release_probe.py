"""Opt-in use of the already reviewed ID2 local32tick probe envelope.

Do not clip a local movement test at the Normal endpoint before proving any
movement. Same pins, cap400, Speed600/ACC8, one-tick ramp, encoder/effort
limits, fresh4tick movement proof and6s timeout remain in the base classes.
This cannot certify the whole path back to Normal is clear.
"""


def fullspan_plan(base):
    class FullSpanNormalProbe(base):
        def _target(self):
            if self.target_normal:
                return min(self.command_window[1],max(self.command_window[0],
                    self.anchor_goal+self.source_sign*self.command_excursion))
            return super()._target()
    return FullSpanNormalProbe
