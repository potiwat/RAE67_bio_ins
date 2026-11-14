"""Student CPG implementation for Lab 03.

Function names and return structures stay unchanged so the grader and
experiment runner can load this file.
"""

from __future__ import annotations

import math


TRIPOD_SIGN = {"LF": 1.0, "RM": 1.0, "LH": 1.0,
               "RF": -1.0, "LM": -1.0, "RH": -1.0}


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def so2_step(o1: float, o2: float, alpha: float, phi: float) -> tuple[float, float]:
    """Return o1(t+1), o2(t+1) using a simultaneous update."""
    cosine = math.cos(phi)
    sine = math.sin(phi)
    activation_1 = alpha * (cosine * o1 + sine * o2)
    activation_2 = alpha * (-sine * o1 + cosine * o2)
    return math.tanh(activation_1), math.tanh(activation_2)


def decode_tripod(o1: float, o2: float, stride_half: float,
                   lift_height: float) -> dict[str, dict[str, float | bool]]:
    """Return x_rel, lift, and contact for all six legs."""
    legs: dict[str, dict[str, float | bool]] = {}
    for leg, sign in TRIPOD_SIGN.items():
        phase_1 = sign * o1
        phase_2 = sign * o2
        legs[leg] = {
            "x_rel": stride_half * phase_1,
            "lift": lift_height * max(0.0, phase_2),
            "contact": phase_2 <= 0.0,
        }
    return legs


def bounded_modulation(m: float, phi0: float = 0.20,
                       phi_gain: float = 0.20,
                       phi_bounds: tuple[float, float] = (0.10, 0.45),
                       stride0: float = 0.055,
                       stride_gain: float = 0.010,
                       stride_bounds: tuple[float, float] = (0.040, 0.070),
                       ) -> tuple[float, float]:
    """Map slow input m to bounded phi and stride commands."""
    phi = clamp(phi0 + phi_gain * m, phi_bounds[0], phi_bounds[1])
    stride = clamp(stride0 + stride_gain * m, stride_bounds[0], stride_bounds[1])
    return phi, stride
