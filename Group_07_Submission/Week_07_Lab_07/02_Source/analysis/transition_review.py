"""Happy ID1 encoder periods from measured midline crossings with hysteresis."""
import numpy as np
from .review_pair import GAP, DEG

def n(v):return float(v) if v not in (None,"","N/A") else np.nan
def numeric(rows,key):return np.asarray([n(v[key]) for v in rows])
def physical_cross(rows,key,mid,lo,hi):
    cross=[];group=0;low=False;pending=None
    for a,b in zip(rows,rows[1:]):
        ta,tb=n(a["t"]),n(b["t"]);va,vb=n(a[key]),n(b[key])
        if not (0<tb-ta<=GAP) or not np.isfinite([va,vb]).all():
            low=False;pending=None;group+=1;continue
        if va<=lo:low=True;pending=None
        if low and va<mid<=vb:pending=ta+(mid-va)*(tb-ta)/(vb-va)
        if low and pending is not None and vb>=hi:cross.append((pending,group));pending=None;low=False
    return [(a,b) for (a,g),(b,h) in zip(cross,cross[1:]) if g==h]
def encoder_periods(cond, ctrl, joints, starts):
    leave=next(n(e["recognized_s"]) for e in starts if e["condition"]==cond and e["from_state"]=="happy" and e["to_state"]=="normal" and e["status"]=="transition" and 59<n(e["recognized_s"])<77)
    enter=next(n(e["recognized_s"]) for e in starts if e["condition"]==cond and e["event"]=="touch" and e["source_id"]=="study_touch_42.0" and e["status"]=="transition")
    first=27.
    last=leave
    j=[v for v in joints if int(v["joint"])==1 and v["fsm"]=="happy" and v["behavior"]=="happy" and enter-.3<=n(v["t"])<=leave and v["status"]=="0" and v["torque"]=="1"]
    # Baseline center and hysteresis are estimated from repeated, fully developed high-input dance.
    # Crossings outside the measured dance are not considered.
    cal=[v for v in j if 45<=n(v["t"])<59]
    k="encoder_deg"
    qlo,qhi=np.quantile(numeric(cal,k),[.1,.9]);mid=(qlo+qhi)/2
    assert qhi-qlo>6*DEG
    periods=physical_cross(j,k,mid,qlo+.2*(qhi-qlo),qlo+.8*(qhi-qlo))
    stages=(("PRE",first,42.),("ON",42.,59.),("OFF",59.,last))
    result=[]
    for a,b in periods:
        if not first<=a<b<=last:
            continue
        stage=next((name for name,lo,hi in stages if lo<=a and b<=hi),"CROSS_EDGE")
        result.append(dict(signal="encoder_ID1", start_s=a, end_s=b, stage=stage))
    return result
