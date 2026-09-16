"""Student starter for Lab 02.

Complete the TODO sections, then compare the behaviour with the reference
implementation in lab02.py.  Do not copy threshold values into a real robot
until its range and mechanical limits have been checked.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Parameters:
    threshold_m: float = 0.35
    enter_threshold_m: float = 0.32
    exit_threshold_m: float = 0.38
    beta: float = 0.25
    target_distance_m: float = 0.35
    kp: float = 2.0
    command_min: float = -0.6
    command_max: float = 0.6


class StudentController:
    def __init__(self, condition: str, parameters: Parameters | None = None) -> None:
        self.condition = condition
        self.p = parameters or Parameters()
        self.state = "FAR"
        self.filtered_distance: float | None = None

    def update_filter(self, raw_distance_m: float) -> float:
        """TODO 1: implement the low-pass recurrence from slide 14."""
        raise NotImplementedError

    def update_state_single_threshold(self, distance_m: float) -> str:
        """TODO 2: set NEAR below T and FAR otherwise."""
        raise NotImplementedError

    def update_state_hysteresis(self, distance_m: float) -> str:
        """TODO 3: change state only at T_enter or T_exit."""
        raise NotImplementedError

    def proportional_command(self, distance_m: float) -> float:
        """TODO 4: calculate Kp * error and clamp the command."""
        raise NotImplementedError

    def safe_command(self) -> float:
        """The simulator uses zero command for an invalid or stale sample."""
        return 0.0


if __name__ == "__main__":
    print("Open this file and complete TODO 1-4 before connecting it to the lab loop.")
