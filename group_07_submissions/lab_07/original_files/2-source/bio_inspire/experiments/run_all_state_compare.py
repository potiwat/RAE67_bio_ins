"""Export PC-only symbolic FSM/SO2-bank evidence; never starts hardware."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil

from .ahm_input_bridge import scenario, process_inputs, raw_rows
from .all_state_compare import simulate, episode_metrics, STATES
from .run_ahm_cpg_compare import protected_hashes
from .ahm_cpg_compare import ROOT, source_hashes


def save_json(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,allow_nan=False).encode()).hexdigest()
def save_csv(path,rows):
    with path.open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def run(out):
    before=protected_hashes();out.mkdir(parents=True,exist_ok=False)
    results={};stimulus_hashes=[]
    for seed in (41,42,43):
        frames=scenario(seed);inputs=process_inputs(frames)
        assert {s['emotion'] for s in inputs}==set(STATES)
        with (out/f'input_seed{seed}.jsonl').open('w',encoding='utf-8') as stream:
            for row in raw_rows(frames):stream.write(json.dumps(row,allow_nan=False)+'\n')
        stimulus_hashes.append(digest([s['stimulus'] for s in inputs]))
        pair={}
        for condition in ('C0','C1'):
            trace=simulate(inputs,condition)
            save_csv(out/f'full_seed{seed}_{condition}.csv',trace)
            pair[condition]=dict(per_state=episode_metrics(trace),
                max_phi_step=max(abs(b['phi_next']-a['phi_next']) for a,b in zip(trace,trace[1:])),
                shared_input_state_digest=digest([(r['source_id'],r['stimulus'],r['state']) for r in trace]),
                fault_rows=sum(r['fault'] for r in trace))
        assert pair['C0']['shared_input_state_digest']==pair['C1']['shared_input_state_digest']
        results[str(seed)]=pair
    fixture_path=ROOT/'bio_inspire/hardware/normal_measurement_input.json'
    fixture=json.loads(fixture_path.read_text(encoding='utf-8'))
    held_inputs=[dict(time_s=s['source_s'],source_id=s['source_id'],stimulus=s['stimulus'],emotion='normal',interaction=None,fault=False)
                 for s in fixture['samples']]
    holds={}
    for state in STATES:
        holds[state]={}
        for condition in ('C0','C1'):
            trace=simulate(held_inputs,condition,hold_state=state)
            save_csv(out/f'held_{state}_{condition}.csv',trace)
            holds[state][condition]=episode_metrics(trace)[state]
    after=protected_hashes();assert before==after
    summary=dict(scope='PC symbolic-ready FSM + production SO2 oscillator bank; no entry-motion/decoder/camera/servo simulation',
        physical_robot=False,hardware_deployed=False,full_scenario_duration_s=600.,
        seeds=[41,42,43],repeat_interpretation='deterministic robustness/replay checks; not independent human trials',
        classified_stimulus_identical_across_seeds=len(set(stimulus_hashes))==1,
        phi_mapping=dict(baseline=.1,gain=.03,bounds=[.1,.13],hardware_approval_other_states='pending'),
        controls=dict(alpha=1.1,hormone_dt_s=.05,cpg_dt_s=.05,body_time_scale=.5,happy_time_scale=3.402/3.8,afraid_time_scale=.5),
        source_teacher_hashes=source_hashes(),full_scenario=results,component_holds=holds,
        held_input_kind='real recorded Pi R08 segment, fixed-state component experiment, not a free FSM/human trial',
        held_fixture_sha256=hashlib.sha256(fixture_path.read_bytes()).hexdigest(),
        protected_runtime_files_unchanged_during_run=True,protected_file_count=len(before))
    save_json(out/'metrics.json',summary)
    sources=['bio_inspire/runtime/normal_ahm.py','bio_inspire/runtime/state_rhythms.py','bio_inspire/runtime/body_rhythm.py',
             'bio_inspire/experiments/ahm_input_bridge.py','bio_inspire/experiments/all_state_compare.py',
             'bio_inspire/experiments/run_all_state_compare.py']
    snapshots=out/'source_snapshot';snapshots.mkdir()
    for source in sources:shutil.copy2(ROOT/source,snapshots/Path(source).name)
    save_json(out/'source_hashes.json',{source:hashlib.sha256((ROOT/source).read_bytes()).hexdigest() for source in sources})
    save_json(out/'manifest.json',{str(p.relative_to(out)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in out.rglob('*') if p.is_file()})
    print(json.dumps(dict(status='PASS',states=list(STATES),synthetic_full_pairs=3,recorded_input_component_pairs=6,
                          same_classified_S_across_seeds=summary['classified_stimulus_identical_across_seeds'],
                          hardware=False,protected_file_count=len(before))))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    run(parser.parse_args().out)
