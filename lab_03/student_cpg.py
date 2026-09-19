"""Student template for Lab 03.

Complete TODO 1-3. Keep function names and return structures unchanged so the
grader and experiment runner can load this file.
"""

from __future__ import annotations

import math


TRIPOD_SIGN = {"LF": 1.0, "RM": 1.0, "LH": 1.0,
               "RF": -1.0, "LM": -1.0, "RH": -1.0}


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def so2_step(o1: float, o2: float, alpha: float, phi: float) -> tuple[float, float]:
    """Return o1(t+1), o2(t+1) using a simultaneous update."""
    # TODO 1: implement the SO(2) equations from lec5.pptx slide 18.
    raise NotImplementedError("TODO 1: implement so2_step")


def decode_tripod(o1: float, o2: float, stride_half: float,
                   lift_height: float) -> dict[str, dict[str, float | bool]]:
    """Return x_rel, lift, and contact for all six legs."""
    # TODO 2: Tripod B must use the opposite phase sign from Tripod A.
    raise NotImplementedError("TODO 2: implement decode_tripod")


def bounded_modulation(m: float, phi0: float = 0.20,
                       phi_gain: float = 0.20,
                       phi_bounds: tuple[float, float] = (0.10, 0.45),
                       stride0: float = 0.055,
                       stride_gain: float = 0.010,
                       stride_bounds: tuple[float, float] = (0.040, 0.070),
                       ) -> tuple[float, float]:
    """Map slow input m to bounded phi and stride commands."""
    # TODO 3: calculate both commands and clamp each to its own bounds.
    raise NotImplementedError("TODO 3: implement bounded_modulation")
