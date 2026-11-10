"""Reproduce the observed comparison; never modify raw pilot files."""
from pathlib import Path
import json,hashlib,collections
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parent
RUNS={'C0':'20261105T124439Z_db0023c1','C1':'20261105T124913Z_86706a5d'}
data={};reports={}
def reconstructed_stimulus(rows,t0):
    # Keep brief debounced presses visible even if a complete press/release
    # occurs between two owner snapshots. ToF timing remains sampled, not
    # a claim about physical object arrival time.
    levels={k:rows[0]['digital_inputs'][k]['stable_pressed'] for k in ('button','touch')}
    levels['near']=bool(rows[0]['distance'].get('near'));events=[];seen=set();previous=levels['near']
    for row in rows:
        for name in ('button','touch'):
            for edge in row['digital_inputs'][name]['stable_edges']:
                key=(name,edge['sequence'])
                if edge['time_s']>=t0 and key not in seen:
                    seen.add(key);events.append((edge['time_s'],name,edge['pressed']))
        near=bool(row['distance'].get('near'))
        if near!=previous:events.append((row['time_s'],'near',near));previous=near
    times=[0.];values=[float(any(levels.values()))]
    for stamp,name,value in sorted(events):
        levels[name]=value;times.append(stamp-t0);values.append(float(any(levels.values())))
    times.append(rows[-1]['time_s']-t0);values.append(values[-1])
    return times,values
for condition,run in RUNS.items():
    p=ROOT/(condition+'_raw')/run
    summary=json.loads((p/'summary.json').read_text())
    rows=[json.loads(line) for line in (p/'trace.jsonl').read_text().splitlines()]
    marker=rows[0]['measurement_start'];t0=marker['started_s']
    ahm=[row['oscillator']['state_ahm'] for row in rows]
    phi=[v['phi'] for v in ahm];events={e['event_id']:e for r in rows for e in r['ros']['events']}
    baseline=marker['digital_counter_baseline']
    report=dict(run_id=run,condition=condition,classification='manual_Q_pilot_partial_not_final',
        observed_span_s=rows[-1]['time_s']-rows[0]['time_s'],first_snapshot_delay_s=rows[0]['time_s']-t0,
        configured_ceiling_s=summary['duration_s'],source_complete=summary['complete'],rows=summary['written'],
        dropped=summary['dropped'],writer_error=summary['error'],input_health_error=summary['input_health_error'],
        measurement_start=marker,initial_logged_oscillator=rows[0]['oscillator'],
        fsm_states=dict(collections.Counter(r['fsm']['state'] for r in rows)),
        controller_states=dict(collections.Counter(r['state'] for r in rows)),
        test_presses={k:v['accepted_presses']-baseline[k] for k,v in rows[-1]['digital_inputs'].items()},
        h_range=[min(v['h'] for v in ahm),max(v['h'] for v in ahm)],phi_range=[min(phi),max(phi)],
        max_adjacent_logged_phi_change=max(abs(b-a) for a,b in zip(phi,phi[1:])),
        mapping_max_error=max(abs(v['phi']-(.1+.03*(v['stimulus'] if condition=='C0' else v['h']))) for v in ahm if v['stimulus'] is not None),
        event_timeline=[dict(relative_s=e['recognized_s']-t0,**e) for e in events.values()],
        snapshot_gaps_over_05s=[dict(relative_s=b['time_s']-t0,gap_s=b['time_s']-a['time_s'],behavior=b['behavior'])
            for a,b in zip(rows,rows[1:]) if b['time_s']-a['time_s']>.5],
        metrics=json.loads((p/'metrics.json').read_text())['per_state'],
        source_hashes=summary['metadata']['source_hashes'],profile=summary['metadata']['profile'],
        raw_sha256={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in p.iterdir() if f.is_file() and f.name!='metrics.json'})
    reports[condition]=report;data[condition]=(rows,ahm,t0)

a,b=reports['C0'],reports['C1']
comparison=dict(classification='paired_manual_Q_pilot_not_final_causal_effect',
    source_hashes_match=a['source_hashes']==b['source_hashes'],
    profile_differences={k:[a['profile'].get(k),b['profile'].get(k)] for k in a['profile'].keys()|b['profile'].keys() if a['profile'].get(k)!=b['profile'].get(k)},
    initial_h_match=a['measurement_start']['initial_h']==b['measurement_start']['initial_h'],
    initial_bank_match=a['measurement_start']['initial_oscillator_bank']==b['measurement_start']['initial_oscillator_bank'],
    limitations=['Different actual human input timing/duration and automatic Approach events',
        'Q-ended shorter than 180s; preserve source incomplete flag',
        'No consecutive complete-period pairs for deltaT in these short state episodes',
        'phi adjacent-step statistics are sampled parameter changes, not motor jerk or physical smoothness'],
    conditions=reports)
(ROOT/'PAIR_P2_BUTTON_START_COMPARISON.json').write_text(json.dumps(comparison,indent=2),encoding='utf8')

fig,axes=plt.subplots(3,1,figsize=(11,8),sharex=True,constrained_layout=True)
for condition,color in [('C0','#2166ac'),('C1','#d66000')]:
    rows,ahm,t0=data[condition];t=[r['time_s']-t0 for r in rows]
    source_times,source_s=reconstructed_stimulus(rows,t0)
    axes[0].step(source_times,source_s,where='post',color=color,label=condition,alpha=.85)
    axes[1].plot(t,[v['h'] for v in ahm],color=color,label=condition)
    axes[2].step(t,[v['phi'] for v in ahm],where='post',color=color,label=condition)
axes[0].set_ylabel('S (GPIO edges + sampled Near)');axes[1].set_ylabel('H (model state)');axes[2].set_ylabel('phi (rad / model step)')
axes[2].set_xlabel('Seconds after fifth-button-release recognition')
axes[0].set_ylim(-.07,1.12);axes[1].set_ylim(-.04,1.04)
for ax in axes:ax.grid(alpha=.2);ax.legend(loc='upper right',ncols=2)
fig.suptitle('LeLamp C0/C1 hardware pilot: logged S, H and phi\nMatched initial H/CPG; different actual human input timing. Not a motor-smoothness result.',fontsize=12)
fig.savefig(ROOT/'PAIR_P2_S_H_PHI.png',dpi=180)
fig.savefig(ROOT/'PAIR_P2_S_H_PHI.pdf')
plt.close(fig)
print(json.dumps({k:v for k,v in comparison.items() if k!='conditions'},indent=2))
