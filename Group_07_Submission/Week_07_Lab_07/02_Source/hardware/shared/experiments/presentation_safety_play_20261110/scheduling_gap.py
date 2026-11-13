"""Identify a measured software publishing pause, never fabricate feedback.

Eligibility alone grants no movement: the existing group stop, native hold,
bounded release probe and current-epoch clearance token still must complete.
Unknown gaps and UART faults retain their original fault policy.
"""
import math


def publish_stall_evidence(snapshot,gap_s,now):
    if not isinstance(snapshot,dict)or not all(type(x)in(int,float)and math.isfinite(x)for x in(gap_s,now))or gap_s<=0:return None
    recent=snapshot.get('recent_slow',[])
    for row in recent:
        if row.get('operation')!='_publish':continue
        duration=row.get('duration_s');end=row.get('end_s')
        if (type(duration)not in(int,float)or type(end)not in(int,float)
                or not math.isfinite(duration)or not math.isfinite(end)):continue
        if not 0<=now-end<=.1 or duration<gap_s-.05:continue
        if any(x.get('operation')in('uart_read','uart_write','uart_sync')and x.get('duration_s',0)>=.2
               and 0<=now-x.get('end_s',-math.inf)<=.2 for x in recent):return None
        return dict(cause='measured_publish_stall',gap_s=gap_s,publish=dict(row),
                    native_stop_and_fresh_probe_required=True)
    return None
