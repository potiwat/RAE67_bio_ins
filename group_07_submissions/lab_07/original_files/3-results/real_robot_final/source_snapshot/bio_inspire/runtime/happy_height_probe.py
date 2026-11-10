"""Supervised Happy-only observation helpers. No bus access or auto leveling."""
import math


def handle_key(m,key):
    if getattr(m,'happy_height_probe_trial',False) is not True or key not in (ord('o'),ord('p')):return False
    c=m.controller
    if (getattr(m,'behavior_trial',None)!='happy' or c.state not in ('READY','FOLLOWING')
            or getattr(m,'operator_stopped',False) or m.stopping.is_set() or m.urgent_stop.is_set()):
        m.tune_status='Height probe waits for active Happy';return True
    step=getattr(m,'happy_height_probe_step_deg',3)
    if type(step)is not int or step not in (3,6):raise ValueError('Height probe step must be3or6')
    m.happy_height_probe_offset_ticks=round(step*4096/360) if key==ord('p') else 0
    event=dict(time_s=m.now(),key=chr(key),offset_ticks=m.happy_height_probe_offset_ticks)
    m.happy_height_probe_events=(getattr(m,'happy_height_probe_events',[])+[event])[-36:]
    return True


def head_snapshot(m):
    if getattr(m,'happy_height_probe_trial',False) is not True:return None
    h=getattr(m,'interested_head_model',None)
    reference=getattr(getattr(h,'model',None),'reference',None)
    desired=getattr(getattr(h,'visual',None),'position',None)
    if not all(type(v) in (int,float) and math.isfinite(v) for v in (reference,desired)):return None
    return dict(reference_raw=reference,visual_goal_raw=desired,visual_trim_ticks=desired-reference,
                body_entry_raw=dict(h.entry),scope='orientation_model_not_metric_Z')
