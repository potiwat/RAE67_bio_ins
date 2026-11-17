"""Student template for Lab 03.

Complete Step 1-3. Keep function names and return structures unchanged so the
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
    # Step 1: both new values are computed from the OLD o1, o2 (simultaneous update).
    c = math.cos(phi)
    s = math.sin(phi)
    a1 = alpha * (c * o1 + s * o2)
    a2 = alpha * (-s * o1 + c * o2)
    return math.tanh(a1), math.tanh(a2)


def decode_tripod(o1: float, o2: float, stride_half: float,
                   lift_height: float) -> dict[str, dict[str, float | bool]]:
    """Return x_rel, lift, and contact for all six legs."""
    # Step 2: Tripod B uses the opposite phase sign from Tripod A.
    # o1 is treated as foot position along the walking direction.
    # o2 drives o1 (o1 increases while o2 > 0), so a foot with s*o2 >= 0
    # is moving forward = swing (in the air); otherwise it is in stance.
    # Using ">= 0" for Tripod A and "< 0" for Tripod B means exactly one
    # tripod swings at every instant, so exactly 3 legs support the body.
    legs: dict[str, dict[str, float | bool]] = {}
    for leg, sign in TRIPOD_SIGN.items():
        x_rel = sign * stride_half * o1
        if sign > 0:
            swing = o2 >= 0.0
        else:
            swing = o2 < 0.0
        # lift rises smoothly from 0 at the swing/stance boundary
        lift = lift_height * min(1.0, abs(o2)) if swing else 0.0
        legs[leg] = {"x_rel": x_rel, "lift": lift, "contact": not swing}
    return legs


def bounded_modulation(m: float, phi0: float = 0.20,
                       phi_gain: float = 0.20,
                       phi_bounds: tuple[float, float] = (0.10, 0.45),
                       stride0: float = 0.055,
                       stride_gain: float = 0.010,
                       stride_bounds: tuple[float, float] = (0.040, 0.070),
                       ) -> tuple[float, float]:
    """Map slow input m to bounded phi and stride commands."""
    # Step 3: linear mapping, then clamp each command to its own bounds.
    phi_cmd = clamp(phi0 + phi_gain * m, phi_bounds[0], phi_bounds[1])
    stride_cmd = clamp(stride0 + stride_gain * m,
                       stride_bounds[0], stride_bounds[1])
    return phi_cmd, stride_cmd