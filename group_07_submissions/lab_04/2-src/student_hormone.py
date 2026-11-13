"""Lab04: complete the two TODOs. Use only the Python standard library."""
import math

def receptor(h, h_min=0.0, h_max=1.0):
    if not all(math.isfinite(v) for v in (h, h_min, h_max)):
        raise ValueError("Values must be finite")
    if h_max <= h_min:
        raise ValueError("Invalid range")

    r = (h - h_min) / (h_max - h_min)
    return max(0.0, min(1.0, r))

def step(h, stimulus, dt, prod, clear, bind):
    if not math.isfinite(stimulus) or not 0.0 <= stimulus <= 1.0:
        return {
            "h": 0.0, "r": 0.0, "raw": 0.0,
            "p": 0.0, "c": 0.0, "b": 0.0, "fault": 1
        }

    h_old = h
    r_old = receptor(h_old)

    p = prod * stimulus
    c = clear * h_old
    b = bind * r_old

    raw = h_old + dt * (p - c - b)
    h_new = max(0.0, min(1.0, raw))
    r_new = receptor(h_new)

    return {
        "h": h_new, "r": r_new, "raw": raw,
        "p": p, "c": c, "b": b, "fault": 0
    }