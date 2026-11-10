"""Bounded, PC-only matched-input held-state protocol. No actuator adapter."""
import hashlib,json,math,statistics
from .all_state_compare import simulate
from .ahm_cpg_compare import output_periods

STATES=('normal','interested','happy','angry','afraid','sleepy')
DT=.05
SETTLE_S=15.

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,allow_nan=False,separators=(',',':')).encode()).hexdigest()

def inputs_for(state,measure_s):
    if state not in STATES or type(measure_s) not in (int,float) or measure_s not in (30.,40.,45.,50.,60.):
        raise ValueError('Expected one of six states and a reviewed measurement duration')
    total=SETTLE_S+measure_s
    return [dict(time_s=k*DT,source_id=f'{state}_{k:05d}',emotion=state,interaction=None,fault=False,
                 stimulus=float(SETTLE_S+measure_s/3<=k*DT<SETTLE_S+2*measure_s/3))
            for k in range(round(total/DT))]

def component(state,condition,measure_s,include_rows=False):
    inputs=inputs_for(state,measure_s);trace=simulate(inputs,condition,hold_state=state)
    measured=[r for r in trace if r['time_s']>=SETTLE_S and r['envelope']>=1.-1e-9 and not r['fault']]
    periods=output_periods([(r['time_s'],r['o1']) for r in measured])
    values=[r['period_s'] for r in periods];changes=[abs(b-a) for a,b in zip(values,values[1:])]
    metrics=dict(period_count=len(values),delta_t_count=len(changes),
                 frequency_hz=1/statistics.mean(values) if values else None,
                 delta_t_mean_s=statistics.mean(changes) if changes else None,
                 delta_t_max_s=max(changes) if changes else None,periods=periods)
    first=trace[0]
    result=dict(state=state,condition=condition,settling_allowance_s=SETTLE_S,measurement_s=measure_s,
                input_sha256=digest(inputs),input_count=len(inputs),
                initial={k:first[k] for k in ('h','o1','o2','updates')},metrics=metrics,
                max_phi_step=max(abs(b['phi_next']-a['phi_next']) for a,b in zip(trace,trace[1:])))
    if include_rows:result.update(inputs=inputs,trace=trace)
    return result

def duration_checks(measure_s):
    return [dict(state=state,condition=c,period_count=(r:=component(state,c,measure_s))['metrics']['period_count'],
                 delta_t_count=r['metrics']['delta_t_count']) for state in STATES for c in ('C0','C1')]

def select_duration():
    # Prefer one-minute blocks (15s preparation +45s measured) rather than
    # declaring the shortest logical run adequate for loaded physical entry.
    for measure_s in (45.,60.):
        checks=duration_checks(measure_s)
        if all(r['period_count']>=4 and r['delta_t_count']>=3 for r in checks):return measure_s,checks
    raise ValueError('No candidate has enough valid periods; do not schedule hardware')

def filming_plan(measure_s):
    inputs_for('normal',measure_s)
    seconds=len(STATES)*(SETTLE_S+measure_s)
    return dict(component_trials=6,component_seconds_per_trial=seconds,human_trials=6,human_seconds_per_trial=600,
                total_clips=12,total_hardware_minutes=(6*seconds+6*600)/60,
                order=[['C0','C1'],['C1','C0'],['C0','C1']],
                physical_adapter_ready=False,physical_robot_tested=False,
                note='Nominal planned recording time excludes setup, rest and invalid/repeated trials; PC-only duration validation.')

def verify_pair(a,b):
    if a['condition']!='C0' or b['condition']!='C1':raise ValueError('Expected C0 then C1 evidence')
    for key in ('input_sha256','initial','state','settling_allowance_s','measurement_s'):
        if a[key]!=b[key]:raise ValueError('Pair mismatch: '+key)
