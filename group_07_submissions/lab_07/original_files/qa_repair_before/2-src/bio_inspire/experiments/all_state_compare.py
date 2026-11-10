"""PC logical FSM + production SO2-bank comparison; no motion entry model.

Symbolic ready is immediate. No camera, servo dynamics, LED or motor output.
The three real BodyRhythm oscillators share the runtime bank phi installer.
Per-episode metrics never stitch state changes or masked/envelope gaps.
"""
import statistics
from bio_inspire.runtime.body_rhythm import BodyRhythm
from bio_inspire.runtime.state_rhythms import apply_bank_phi
from bio_inspire.runtime.normal_ahm import NormalAHM
from .ahm_cpg_compare import output_periods

STATES=('normal','interested','happy','sleepy','afraid','angry')


def simulate(inputs,condition,hold_state=None):
    if not 1<=len(inputs)<=12000:raise ValueError('Expected1..12000 bounded input intervals')
    if hold_state is not None and hold_state not in STATES:raise ValueError('Unknown held state')
    bank={name:BodyRhythm(phi=.1,time_scale=scale) for name,scale in
          (('body',.5),('happy',3.402/3.8),('afraid',.5))}
    hormone=NormalAHM(condition);rows=[]
    for k,sample in enumerate(inputs):
        t=k*.05;state=hold_state or sample['emotion']
        if state not in STATES:raise ValueError('Unknown FSM state')
        owner='happy' if state=='happy' else 'afraid' if state=='afraid' else 'body'
        command=hormone.step(t,sample['stimulus'],enabled=not sample['fault'])
        fault=bool(sample['fault'] or command['reason']!='tracking')
        for name,rhythm in bank.items():
            rhythm.advance(t,name==owner and not fault,exclusive=name!=owner or fault)
        apply_bank_phi(bank,command['phi'])
        r=bank[owner]
        rows.append(dict(time_s=t,source_time_s=sample['time_s'],source_id=sample['source_id'],
            state=state,fsm_state=sample['emotion'],interaction=sample.get('interaction'),fault=fault,
            owner=owner,stimulus=sample['stimulus'],h=command['h'],r_used=command['r_used'],
            phi_next=command['phi'],o1=r.o1,o2=r.o2,envelope=r.envelope,
            updates=r.updates,dt_s=r.dt_s,time_scale=r.time_scale))
    return rows


def episode_metrics(rows):
    groups={state:[] for state in STATES};segment=[];last=None
    for row in rows:
        key=(row['state'],row['owner']) if row['envelope']>=1.-1e-9 else None
        if key!=last or key is None:
            if segment:groups[last[0]].append(segment)
            segment=[]
        if key is not None:segment.append(row)
        last=key
    if segment:groups[last[0]].append(segment)
    result={}
    for state,segments in groups.items():
        periods=[];changes=[];by_episode=[]
        for segment in segments:
            samples=[];prior=None
            for r in segment:
                if r['updates']==prior:continue
                samples.append((r['updates']*r['dt_s']/r['time_scale'],r['o1']));prior=r['updates']
            p=output_periods(samples);values=[v['period_s'] for v in p]
            periods.extend(values);changes.extend(abs(b-a) for a,b in zip(values,values[1:]))
            by_episode.append(dict(start_s=segment[0]['time_s'],end_s=segment[-1]['time_s'],periods=p))
        result[state]=dict(episodes_with_full_envelope=len(segments),period_count=len(periods),
            frequency_hz=1/statistics.mean(periods) if periods else None,
            delta_t_count=len(changes),delta_t_mean_s=statistics.mean(changes) if changes else None,
            delta_t_max_s=max(changes) if changes else None,episodes=by_episode,
            missing_rule='N/A when no complete periods or no adjacent periods within one continuous episode')
    return result
