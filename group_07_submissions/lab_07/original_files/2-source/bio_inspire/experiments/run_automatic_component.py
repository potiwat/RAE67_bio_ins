"""Run matched PC models and export a filming plan; never opens hardware."""
import argparse,json,hashlib,zipfile,xml.etree.ElementTree as ET
from pathlib import Path
from .automatic_component import component,select_duration,duration_checks,filming_plan,verify_pair,STATES
from .ahm_cpg_compare import source_hashes,ROOT

def save(p,value):p.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
def protected():
    paths=[p for name in ('bio_inspire/runtime','shared/runtime') for p in (ROOT/name).glob('*.py')]
    paths.extend(ROOT/'bio_inspire/hardware'/name for name in ('boot_ready_c1.json','lab07_button_start_C0_180s.json','lab07_button_start_C1_180s.json'))
    return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}

def run(out):
    out=Path(out);before=protected();out.mkdir(parents=True,exist_ok=False)
    measure,checks=select_duration();plan=filming_plan(measure)
    candidates={str(t):duration_checks(t) for t in (30.,40.,45.,50.,60.)}
    results=[]
    for pair in range(1,4):
        for state in STATES:
            matched={}
            for condition in ('C0','C1'):
                r=component(state,condition,measure,include_rows=True)
                inputs=r.pop('inputs');rows=r.pop('trace')
                name=f'P{pair}_{state}_{condition}'
                with (out/(name+'.jsonl')).open('x',encoding='utf8') as stream:
                    for row in rows:stream.write(json.dumps(row,separators=(',',':'),allow_nan=False)+'\n')
                if condition=='C0':
                    with (out/f'P{pair}_{state}_S.jsonl').open('x',encoding='utf8') as stream:
                        for row in inputs:stream.write(json.dumps(row,separators=(',',':'),allow_nan=False)+'\n')
                r['pair']=pair;matched[condition]=r;results.append(r)
            verify_pair(matched['C0'],matched['C1'])
    schedule=[dict(state=state,slot_start_s=n*(15+measure),settling_end_s=n*(15+measure)+15,
                   slot_end_s=(n+1)*(15+measure),S_on_s=n*(15+measure)+15+measure/3,
                   S_off_s=n*(15+measure)+15+2*measure/3,
                   hardware_policy='Must reach approved pose before measure; abort/mark invalid on timeout or real safety override, never force or relabel samples')
              for n,state in enumerate(STATES)]
    save(out/'component_schedule.json',dict(origin='PC_schedule_not_deployed',start='M then fifth physical button release, same existing gate',slots=schedule,
        live_safety='Real ToF/STOP/camera/bus/angle guards must override scripted inputs in future hardware adapter',
        resets='Independent per-state components; only reinitialize paused zero-envelope bank, never reset a moving rhythm'))
    save(out/'filming_plan.json',plan)
    assert protected()==before,'Protected runtime/profile changed during PC run'
    summary=dict(status='PASS',scope='PC held-state SO2/AHM model; not motion entry/decoder/servo simulation',
        physical_robot=False,hardware_deployed=False,hardware_adapter_ready=False,
        model_runs=len(results),deterministic_pairs=3,repeat_interpretation='Exact deterministic replay checks, not three independent hardware/human observations',
        selected_measurement_s=measure,settling_allowance_s=15,minimum_period_count=min(r['period_count'] for r in checks),
        minimum_delta_t_count=min(r['delta_t_count'] for r in checks),candidate_checks=candidates,filming_plan=plan,
        teacher_model_sources=source_hashes(),protected_files_unchanged=True,protected_hashes=before,results=results)
    save(out/'verification.json',summary)
    sources=['bio_inspire/experiments/automatic_component.py','bio_inspire/experiments/run_automatic_component.py','bio_inspire/experiments/all_state_compare.py','bio_inspire/runtime/normal_ahm.py','bio_inspire/runtime/body_rhythm.py']
    save(out/'source_hashes.json',{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sources})
    save(out/'manifest.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()})
    print(json.dumps({k:summary[k] for k in ('status','scope','model_runs','selected_measurement_s','minimum_period_count','minimum_delta_t_count','hardware_adapter_ready','protected_files_unchanged','filming_plan')},indent=2))
    return summary

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True)
    run(parser.parse_args().out)
