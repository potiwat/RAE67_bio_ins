"""Observed o1 wall-clock metrics; never stitch states, masks or clock gaps."""
import argparse,hashlib,json,math,statistics
from pathlib import Path
from .ahm_cpg_compare import output_periods
STATES=('normal','interested','happy','sleepy','afraid','angry')
def analyze(rows):
    groups={s:[] for s in STATES};segment=[];prior=None;key=None;valid=0;gaps=0;faults=0;coverage={s:0 for s in STATES}
    for row in rows:
        t=row.get('time_s');r=row.get('oscillator') or {};state=row.get('behavior')
        if state in coverage:coverage[state]+=1
        good=(type(t) in (float,int) and math.isfinite(t) and state in STATES
              and row.get('state') in ('READY','FOLLOWING') and row.get('pose_phase') not in ('look','return','lean','tilt')
              and type(r.get('o1')) in (int,float) and math.isfinite(r['o1']) and r.get('envelope',0)>=1.-1e-9)
        gap=prior is not None and (type(t) not in (float,int) or not math.isfinite(t) or not 0<t-prior<=.5)
        if gap:gaps+=1
        if row.get('state') in ('FAULT','STOPPED','WAIT_TOF'):faults+=1
        current=state if good else None
        reset=bool(segment and type(r.get('updates'))is int and type(segment[-1][2])is int and r['updates']<segment[-1][2])
        if current!=key or gap or current is None or reset:
            if segment:groups[key].append(segment)
            segment=[]
        if current is not None:
            valid+=1
            if not segment or r.get('updates')!=segment[-1][2]:segment.append((t,r['o1'],r.get('updates')))
        key=current;prior=t if type(t) in (int,float) and math.isfinite(t) else None
    if segment:groups[key].append(segment)
    result={}
    for state,episodes in groups.items():
        periods=[];changes=[]
        for episode in episodes:
            values=[p['period_s'] for p in output_periods([(t,v) for t,v,u in episode])]
            periods+=values;changes.extend(abs(b-a) for a,b in zip(values,values[1:]))
        result[state]=dict(episode_count=len(episodes),period_count=len(periods),
            frequency_hz=1/statistics.mean(periods) if periods else None,delta_t_count=len(changes),
            delta_t_mean_s=statistics.mean(changes) if changes else None)
    return dict(per_state=result,state_coverage_rows=coverage,valid_samples=valid,clock_gaps=gaps,hold_fault_rows=faults,
        limitation='Observed CPG o1, not physical motion frequency; no pooled frequency across different emotions; null means N/A')
def main():
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);args=p.parse_args()
    path=args.directory/'trace.jsonl';summary=json.loads((args.directory/'summary.json').read_text(encoding='utf8'))
    if hashlib.sha256(path.read_bytes()).hexdigest()!=summary['trace_sha256']:raise ValueError('Trace hash differs')
    if path.stat().st_size>64*1024*1024:raise ValueError('Oversized trace')
    with path.open(encoding='utf8') as stream:rows=[json.loads(line) for line in stream]
    metrics=analyze(rows)
    span=(rows[-1]['time_s']-rows[0]['time_s']) if rows else 0.
    result={**metrics,'recording':summary,'formal_eligible':bool(summary['complete'] and summary['duration_s']==600 and summary.get('metadata',{}).get('origin')=='live_robot' and span>=600 and not metrics['hold_fault_rows'] and not metrics['clock_gaps'])}
    out=args.directory/'metrics.json'
    with out.open('x',encoding='utf8') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(out)
if __name__=='__main__':main()
