"""Conservative Interested anticipation below the retained 34-tick lag gate.

No arm speed, acceleration, PID, endpoint, bounds, or contact authority changes.
"""
import inspect
import textwrap


def lead_scale(route,remaining,now):
    if remaining<=0:return 0.
    start=getattr(route,'trial_interested_lead_start_s',None)
    if start is None:
        route.trial_interested_lead_start_s=start=now
    u=max(0.,min(1.,(now-start)/.5))
    blend=u*u*u*(10+u*(-15+6*u))
    return min(1.,26./remaining)*blend


def pitch_service(original):
    source=textwrap.dedent(inspect.getsource(original))
    before='scale=min(1.,34/remaining) if remaining else 0.'
    if source.count(before)!=1:
        raise RuntimeError('Retained Interested compensation implementation changed')
    namespace=dict(original.__globals__,_trial_interested_lead_scale=lead_scale)
    source=source.replace(before,'scale=_trial_interested_lead_scale(route,remaining,now)',1)
    exec(compile(source,__file__,'exec'),namespace)
    return namespace[original.__name__]
