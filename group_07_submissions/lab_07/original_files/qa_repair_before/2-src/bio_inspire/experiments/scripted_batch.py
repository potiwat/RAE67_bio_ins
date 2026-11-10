"""Six fast logical C0/C1 replays of the Pi's exact scripted input grid.

Not servo dynamics/vision simulation. FSM is symbolically ready immediately;
real motion readiness/timing must be measured separately on the robot.
"""
import csv
import hashlib
import json
from pathlib import Path
from bio_inspire.runtime.automatic_trial import AutomaticTrial,schedule,schedule_sha256
from bio_inspire.runtime.angry_fsm import AngryFSM,TouchBurst
from bio_inspire.runtime.body_rhythm import BodyRhythm
from bio_inspire.runtime.state_rhythms import apply_bank_phi
from .all_state_compare import episode_metrics

def simulate_pair(pair):
    inputs=[];trial=AutomaticTrial('C0');trial.start(0.)
    fsm=AngryFSM(0.,active_timeout_s=5.,sleep_after_s=10.,motion_aware=True,happy_timeout_s=7.)
    burst=TouchBurst()
    for k in range(12000):
        t=k*.05;trial.advance(t);events=[]
        def add(kind,stamp):events.append(dict(kind=kind,source_s=stamp,source_id=f'{pair}_{kind}_{k:05d}'))
        if trial.distance_event:add(trial.distance_event,t)
        if trial.near and fsm.state!='afraid':add('near',t)
        if not trial.near and fsm.state=='afraid':add('clear',t)
        blocked=trial.near or fsm.state in ('afraid','angry')
        if blocked:burst.clear()
        for channel,port in trial.sources.items():
            for stamp in port.drain_events(t):
                add(channel,stamp)
                if channel=='touch' and not blocked and burst.press(stamp,t):add('touch_burst',stamp)
        winner=fsm.step(t,events,ready=True,held=any(p.edge.stable for p in trial.sources.values()))
        inputs.append(dict(time_s=t,state=fsm.state,interaction=None if winner is None else winner['kind']))
    result=[]
    for condition in ('C0','C1'):
        ahm=AutomaticTrial(condition).replay;ahm.start(0.)
        bank={name:BodyRhythm(phi=.1,time_scale=scale) for name,scale in (('body',.5),('happy',3.402/3.8),('afraid',.5))}
        rows=[]
        for source in inputs:
            t=source['time_s'];state=source['state'];owner='happy' if state=='happy' else 'afraid' if state=='afraid' else 'body'
            command=ahm.step(t)
            for name,r in bank.items():r.advance(t,name==owner,exclusive=name!=owner)
            apply_bank_phi(bank,command['phi']);r=bank[owner]
            rows.append(dict(**source,condition=condition,pair_id=pair,owner=owner,stimulus=command['stimulus'],
                h=command['h'],r_used=command['r_used'],phi_next=command['phi'],o1=r.o1,o2=r.o2,
                updates=r.updates,envelope=r.envelope,time_scale=r.time_scale,dt_s=.05))
        result.append(rows)
    return result

def main():
    import argparse,time
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
    if any(out.iterdir()):raise FileExistsError('Keep previous simulation evidence unchanged')
    started=time.perf_counter();runs=[]
    for pair in ('P1','P2','P3'):
        a,b=simulate_pair(pair)
        assert [(r['stimulus'],r['state']) for r in a]==[(r['stimulus'],r['state']) for r in b]
        assert (a[0]['h'],a[0]['o1'],a[0]['o2'])==(b[0]['h'],b[0]['o1'],b[0]['o2'])
        for condition,rows in (('C0',a),('C1',b)):
            path=out/f'{pair}_{condition}.csv'
            with path.open('w',encoding='utf-8-sig',newline='') as f:
                w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
            runs.append(dict(pair_id=pair,condition=condition,count=len(rows),states=sorted({r['state'] for r in rows}),
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),metrics=episode_metrics(rows)))
    source=Path(__file__).resolve().parents[2]
    sources=['bio_inspire/runtime/automatic_trial.py','bio_inspire/runtime/body_rhythm.py','bio_inspire/runtime/state_rhythms.py',
             'bio_inspire/runtime/angry_fsm.py','bio_inspire/runtime/lab_fsm.py','bio_inspire/experiments/scripted_batch.py']
    summary=dict(status='PASS',trials=6,pairs=3,simulated_seconds_per_trial=600,wall_seconds=time.perf_counter()-started,
        scope='Logical immediate-ready FSM plus production SO2 bank; no servo dynamics, motion decoder or camera simulation',
        repeat_interpretation='deterministic repeated replay verification, not independent stochastic/human trials',
        schedule=schedule(),schedule_sha256=schedule_sha256(),input_initials_equal_per_pair=True,
        hardware_trial_complete=False,source_hashes={n:hashlib.sha256((source/n).read_bytes()).hexdigest() for n in sources},runs=runs)
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k not in ('runs','source_hashes','schedule')},indent=2))

if __name__=='__main__':main()
