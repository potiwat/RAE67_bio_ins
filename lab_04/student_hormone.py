"""Lab04: artificial hormone receptor and Euler step. Standard library only."""
import math


def _clamp(value, low, high):
    return max(low, min(high, value))


def receptor(h, h_min=0.0, h_max=1.0):
    """Normalize then clamp to [0,1]. Reject nonfinite values or invalid range."""
    for value in (h, h_min, h_max):
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("receptor inputs must be finite numbers")
    if h_max <= h_min:
        raise ValueError("receptor requires h_max > h_min")
    return _clamp((h - h_min) / (h_max - h_min), 0.0, 1.0)


def step(h, stimulus, dt, prod, clear, bind):
    """Return dict with h,r,raw,p,c,b,fault.

    Invalid stimulus (NaN, infinity, outside [0,1]): reset to h=r=0,
    set raw=p=c=b=0 and fault=1. Valid: use OLD h and receptor(h)
    for all rates; update once, clamp h, read NEW receptor, fault=0.
    dt and rates have already been validated by the runner.
    """
    valid = (
        isinstance(stimulus, (int, float))
        and not isinstance(stimulus, bool)
        and math.isfinite(stimulus)
        and 0.0 <= stimulus <= 1.0
    )
    if not valid:
        return {"h": 0.0, "r": 0.0, "raw": 0.0,
                "p": 0.0, "c": 0.0, "b": 0.0, "fault": 1}

    h_old = h
    r_old = receptor(h_old)
    p = prod * stimulus
    c = clear * h_old
    b = bind * r_old
    raw = h_old + dt * (p - c - b)
    h_new = _clamp(raw, 0.0, 1.0)
    return {"h": h_new, "r": receptor(h_new), "raw": raw,
            "p": p, "c": c, "b": b, "fault": 0}
