"""Measured CPG and encoder periods, effective drive and the Lab 7 worksheet metrics."""
import csv
import gzip
import hashlib
import json
import math
from statistics import mean
import numpy as np
from . import review_pair as baseline
from .window_quality import DURATION

STATES = baseline.STATES
CONDITIONS = ("C0", "C1")
IDENTITY_KEYS = ("desktop_sha256", "study_sha256", "manifest_sha256", "profile_sha256", "script_sha256")
TEST_START, RELEASE = 42., 59.
MODEL_DT = .05


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path, rows):
    if not rows:
        return
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(dict.fromkeys(k for row in rows for k in row)))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: "N/A" if v is None else v for k, v in row.items()})


def obj(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def identity_key(identity):
    return tuple(identity[k] for k in IDENTITY_KEYS)


def mean_held_h(time, values, start, end):
    """Time mean of the recorded hormone using the last sample until the next AHM observation."""
    if start < time[0] or end > time[-1] or start >= end:
        raise ValueError("Cycle extends outside hormone observations")
    i, j = np.searchsorted(time, [start, end], side="right")
    edges = np.r_[start, time[i:j], end]
    return float(np.dot(np.diff(edges), values[i-1:j])/(end-start))


def complete_episodes(rows, scales):
    """Split by state, bank, route mask, envelope, clock gaps and model resets."""
    active = []
    last_key = None
    last_t = None
    last_update = None
    for r in rows:
        state,bank = r["fsm"], r["selected"]
        time = float(r[bank+"_t"])
        index = int(r[bank+"_updates"])
        good = (r["valid"]=="1" and r["reason"]=="tracking" and state==r["behavior"]
                and baseline.BANK.get(state)==bank and r["route"] not in ("look","return","lean","tilt")
                and float(r[bank+"_envelope"]) >= 1.-1e-9 and 0<=time<DURATION)
        key = (state,bank)
        split = (active and (not good or key!=last_key or index<last_update
                             or not 0<=time-last_t<=baseline.GAP))
        if split:
            yield last_key,active
            active=[]
        if good and (not active or index!=last_update):
            active.append((index*MODEL_DT/scales[bank], float(r[bank+"_o1"]), time, index))
        last_key,last_t,last_update=key,time,index
    if active:
        yield last_key,active


def output_periods(samples):
    """Rising zero crossings, linear time interpolation, complete periods only."""
    crossings = []
    for index, ((ta, a), (tb, b)) in enumerate(zip(samples, samples[1:])):
        if not all(math.isfinite(v) for v in (ta, a, tb, b)) or tb <= ta:
            raise ValueError('finite samples with strictly increasing times required')
        if a < 0 <= b:
            crossings.append(ta + (-a)/(b-a)*(tb-ta))
        elif index == 0 and a == 0 and b > 0:
            crossings.append(ta)
    return [dict(start_s=a, end_s=b, period_s=b-a, midpoint_s=(a+b)/2,
                 frequency_hz=1/(b-a)) for a, b in zip(crossings, crossings[1:])]


def study_run(d, pair, cond, controls, native, motor_periods, identity, summary, event_rows):
    with gzip.open(d/"trace.jsonl.gz","rb") as f:
        data=f.read()
    assert hashlib.sha256(data).hexdigest()==summary["trace_sha256"]
    scales={}
    for line in data.splitlines():
        row=json.loads(line)
        if not 0<=row["t"]<DURATION:
            continue
        bank=row["selected"];scale=row["out"].get("time_scale")
        if row["fsm"]==row["behavior"] and bank==baseline.BANK.get(row["fsm"]) and isinstance(scale,(int,float)):
            scales.setdefault(bank,set()).add(scale)
    assert set(scales)==set(baseline.BANK.values()) and all(len(v)==1 for v in scales.values())
    scales={k:v.pop() for k,v in scales.items()}
    del data
    ht=np.array([float(r["t"]) for r in controls])
    hv=np.array([float(r["H"]) for r in controls])
    assert np.all(np.diff(ht)>0)
    lo,hi=identity["happy_phi_low"],identity["happy_phi_high"]
    happy_rows=[r for r in controls if TEST_START<=float(r["t"])<66
                and r["valid"]=="1" and r["fsm"]==r["behavior"]=="happy" and r["selected"]=="happy"]
    assert happy_rows
    for r in happy_rows:
        drive=float(r["S"] if cond=="C0" else r["H"])
        assert math.isclose(float(r["R"]),drive,abs_tol=2e-8)
        assert math.isclose(float(r["happy_phi"]),lo+(hi-lo)*drive,abs_tol=2e-8)
    cycles=[];stats=[]
    for episode,((state,bank),nodes) in enumerate(complete_episodes(controls,scales),1):
        previous=None
        model=np.array([v[0] for v in nodes])
        wall=np.array([v[2] for v in nodes])
        for cycle in output_periods([(v[0],v[1]) for v in nodes]):
            t0,t1=cycle["start_s"],cycle["end_s"]
            a,b=np.interp([t0,t1],model,wall)
            period=cycle["period_s"]
            cycles.append(dict(pair=pair,condition=cond,state=state,episode=episode,bank=bank,
                               start_s=float(a),end_s=float(b),mean_H=mean_held_h(ht,hv,a,b),
                               T_cpg_s=period,f_cpg_Hz=1/period,
                               delta_T_s=abs(period-previous) if previous is not None else None,
                               T_observed_s=float(b-a),clock_scale=scales[bank]))
            previous=period
    for state in STATES:
        part=[v for v in cycles if v["state"]==state]
        periods=[v["T_cpg_s"] for v in part];deltas=[v["delta_T_s"] for v in part if v["delta_T_s"] is not None]
        stats.append(dict(pair=pair,condition=cond,state=state,complete_cycles=len(periods),
                          adjacent_pairs=len(deltas),M1_Hz=1/mean(periods) if periods else None,
                          M2_s=mean(deltas) if deltas else None,max_delta_T_s=max(deltas) if deltas else None))
    swings=[]
    for v in motor_periods:
        if v["signal"]!="encoder_ID1":continue
        a,b=float(v["start_s"]),float(v["end_s"])
        swings.append(dict(pair=pair,condition=cond,start_s=a,end_s=b,mean_H=mean_held_h(ht,hv,a,b),
                           T_dance_s=b-a,swings_per_min=60/(b-a),stage=v["stage"]))
    milestones=[]
    dec=[r for r in happy_rows if float(r["t"])>=RELEASE]
    for ref in (1.,.5,.1):
        r=min(dec,key=lambda q:abs(float(q["H"])-ref))
        milestones.append(dict(pair=pair,condition=cond,t_s=float(r["t"]),H=float(r["H"]),
                               R=float(r["R"]),phi=float(r["happy_phi"]),S=float(r["S"]),level_ref=ref))
    pre=next(r["fsm"] for r in reversed(controls) if float(r["t"])<TEST_START)
    enter=next(v for v in event_rows if v["condition"]==cond and v["source_id"]=="study_touch_42.0" and v["status"]=="transition")
    leave=next(v for v in event_rows if v["condition"]==cond and v["from_state"]=="happy" and v["to_state"]=="normal" and 59<float(v["recognized_s"])<77)
    assert all(abs(float(r["H"]))<=1 and 0<=float(r["R"])<=1 for r in happy_rows)
    return dict(pair=pair,condition=cond,ctrl=controls,points=happy_rows,cycles=cycles,stats=stats,swings=swings,
                levels=milestones,pre=pre,source_state=enter["from_state"],leave=float(leave["recognized_s"]),
                seed=summary["seed_at_start"],id=identity,scales=scales,audit=native)
