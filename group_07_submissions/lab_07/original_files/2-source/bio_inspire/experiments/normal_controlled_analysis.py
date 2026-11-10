"""Paired pilot analysis; distinguish controller oscillation from joint motion."""
import math
import statistics
from .ahm_cpg_compare import output_periods, period_metrics


def verify_pair(a,b):
    if a.get('condition')!='C0' or b.get('condition')!='C1' or not a.get('completed') or not b.get('completed'):
        raise ValueError('Completed C0/C1 recordings required')
    for key in ('nominal_input','common_initial_o1','common_initial_o2','cpg_dt_s','cpg_time_scale','amplitude_deg_limit'):
        if key not in a or a[key]!=b.get(key):raise ValueError('Unpaired reference/configuration: '+key)


def cpg_samples(rows):
    """State o1 is at update index k, not at delayed log receipt time.

    Repeated state snapshots are deduplicated; absent logged model nodes are
    counted. Crossings spanning absent nodes are linearly interpolated.
    """
    samples=[];last=None;missing=0
    for row in rows:
        r=row['rhythm'];index=r['updates']
        if type(index)is not int or index<0 or last is not None and index<last:
            raise ValueError('CPG update index reversed/invalid')
        if last==index:continue
        t=index*r['dt_s']/r['time_scale'];value=r['o1']
        if not math.isfinite(t) or not math.isfinite(value):raise ValueError('Nonfinite CPG state')
        if last is not None:missing+=index-last-1
        samples.append((t,value));last=index
    return samples,missing


def summarize(data):
    rows=data['trace']
    if (not rows or any(r['controller_state'] not in ('READY','FOLLOWING') or r['behavior']!='normal'
                       or r['live_near'] for r in rows)):
        raise ValueError('Unhealthy/non-Normal trace')
    samples,missing=cpg_samples(rows);periods=output_periods(samples)
    phis=[r['rhythm']['normal_ahm']['phi'] for r in rows]
    intervals=[b['time_s']-a['time_s'] for a,b in zip(rows,rows[1:])]
    joints={}
    for sid in (2,3):
        actual=[next(v['position_raw'] for v in r['rows'] if v['id']==sid)
                for r in rows if r['elapsed_s']>=5.]
        goals=[r['command_goals'][str(sid)] for r in rows if r['elapsed_s']>=5.]
        joints[str(sid)]=dict(actual_range_ticks=[min(actual),max(actual)],
            actual_peak_to_peak_deg=(max(actual)-min(actual))*360/4096,
            command_range_ticks=[min(goals),max(goals)],
            command_peak_to_peak_deg=(max(goals)-min(goals))*360/4096)
    return dict(condition=data['condition'],trace_count=len(rows),last_elapsed_s=rows[-1]['elapsed_s'],
        max_phi_step=max(abs(b-a) for a,b in zip(phis,phis[1:])),phi_range=[min(phis),max(phis)],
        cpg_o1_metrics=period_metrics(periods),cpg_periods=periods,
        logged_unique_cpg_nodes=len(samples),unlogged_cpg_nodes=missing,
        skipped_nominal_parameter_indices=data['skipped_schedule_updates'],
        median_record_interval_s=statistics.median(intervals),
        initial_feedback_raw={str(r['id']):r['position_raw'] for r in rows[0]['rows']},
        joints=joints,physical_frequency_measured=False,physical_jerk_measured=False,
        metric_clock='o1 state at updates*dt/time_scale; linear rising zero crossings')
