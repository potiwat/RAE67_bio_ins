"""Student starter for Lab 02.

Complete TODO 1-4, then run lab02.py with --controller-source student.
The simulator calls these methods through StudentControllerAdapter. Each update
method must return its new value; the adapter keeps state and filtered_distance
in sync. Do not copy parameters into a real robot without checking its limits.
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
        """TODO 1: low-pass filter."""
        if self.filtered_distance is None:
            self.filtered_distance = raw_distance_m
        else:
            b = self.p.beta
            self.filtered_distance = b * raw_distance_m + (1 - b) * self.filtered_distance
        return self.filtered_distance

    def update_state_single_threshold(self, distance_m: float) -> str:
        """TODO 2: NEAR below T, FAR otherwise."""
        return "NEAR" if distance_m < self.p.threshold_m else "FAR"

    def update_state_hysteresis(self, distance_m: float) -> str:
        """TODO 3: change state only at T_enter or T_exit."""
        if self.state == "FAR" and distance_m <= self.p.enter_threshold_m:
            return "NEAR"
        if self.state == "NEAR" and distance_m >= self.p.exit_threshold_m:
            return "FAR"
        return self.state

    def proportional_command(self, distance_m: float) -> float:
        """TODO 4: Kp * error, clamped."""
        error = self.p.target_distance_m - distance_m
        u = self.p.kp * error
        return max(self.p.command_min, min(self.p.command_max, u))

    def safe_command(self) -> float:
        """The simulator uses zero command for an invalid or stale sample."""
        return 0.0


if __name__ == "__main__":
    print("Complete TODO 1-4, then run lab02.py --controller-source student.")