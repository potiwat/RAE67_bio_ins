"""Lab 04 receptor and hormone update using the Python standard library."""
import math

def receptor(h, h_min=0.0, h_max=1.0):
    """Normalize then clamp to [0,1]. Reject nonfinite values or invalid range."""
    values = (h, h_min, h_max)
    if not all(isinstance(value, (int, float)) and math.isfinite(value)
               for value in values):
        raise ValueError("receptor inputs must be finite numbers")
    if h_max <= h_min:
        raise ValueError("h_max must be greater than h_min")
    normalized = (h - h_min) / (h_max - h_min)
    return min(1.0, max(0.0, normalized))

def step(h, stimulus, dt, prod, clear, bind):
    """Return dict with h,r,raw,p,c,b,fault.

    Invalid stimulus (NaN, infinity, outside [0,1]): reset to h=r=0,
    set raw=p=c=b=0 and fault=1. Valid: use OLD h and receptor(h)
    for all rates; update once, clamp h, read NEW receptor, fault=0.
    dt and rates have already been validated by the runner.
    """
    valid_stimulus = (
        isinstance(stimulus, (int, float))
        and math.isfinite(stimulus)
        and 0.0 <= stimulus <= 1.0
    )
    if not valid_stimulus:
        return {"h": 0.0, "r": 0.0, "raw": 0.0, "p": 0.0,
                "c": 0.0, "b": 0.0, "fault": 1}

    h_old = h
    r_old = receptor(h_old)
    production = prod * stimulus
    clearance = clear * h_old
    binding = bind * r_old
    raw = h_old + dt * (production - clearance - binding)
    h_new = min(1.0, max(0.0, raw))
    return {"h": h_new, "r": receptor(h_new), "raw": raw,
            "p": production, "c": clearance, "b": binding, "fault": 0}
