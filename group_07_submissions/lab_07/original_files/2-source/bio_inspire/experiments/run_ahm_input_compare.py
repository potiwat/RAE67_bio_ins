"""Replay synthetic logical button/touch/ToF through shared adapter and AHM/CPG.

All time and emotion entry readiness are simulated. No physical device imports.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil

from . import ahm_cpg_compare as model
from . import ahm_input_bridge as bridge
from . import run_ahm_cpg_compare as evidence


def metrics(rows):
    periods=model.output_periods([(r['t_s'],r['o1']) for r in rows])
    phi=[r['phi_rad_per_update'] for r in rows[:-1]]
    jumps=[abs(b-a) for a,b in zip(phi,phi[1:])]
    return dict(**model.period_metrics(periods),phi_max_step_rad=max(jumps,default=0.),
                phi_total_variation_rad=sum(jumps),fault_count=sum(r['fault'] for r in rows[:-1]),
                command_latency_s=None,latency_reason='multiple input episodes; step10/20 latency not applicable',
                physical_smoothness=None)


def plot_result(out, processed, traces):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    colors={'C0':'#2166ac','C1':'#c05a12'}
    states=['normal','interested','happy','afraid','sleepy','angry']
    fig,axes=plt.subplots(4,1,figsize=(13,10),sharex=True,layout='constrained')
    times=[r['time_s'] for r in processed]
    axes[0].step(times,[states.index(r['emotion']) for r in processed],where='post',color='#424955')
    axes[0].set_yticks(range(6),states)
    axes[0].set_ylabel('Symbolic FSM')
    axes[1].step(times,[r['stimulus'] for r in processed],where='post',color='#303740')
    axes[1].set_ylabel('Shared S')
    for c,rows in traces.items():
        commands=rows[:-1]
        axes[2].plot(times,[r['phi_rad_per_update'] for r in commands],color=colors[c],label=f'{c} '+('direct' if c=='C0' else 'hormone'))
        periods=model.output_periods([(r['t_s'],r['o1']) for r in rows])
        axes[3].plot([p['end_s'] for p in periods],[p['frequency_hz'] for p in periods],color=colors[c],label=c)
    axes[2].set_ylabel('phi (rad/update)')
    axes[3].set_ylabel('CPG cycle frequency (Hz)')
    axes[3].set_xlabel('Simulation time (s)')
    for ax in axes:
        ax.grid(alpha=.2);ax.set_xlim(0,600)
    axes[2].legend();axes[3].legend()
    fig.suptitle('SIMULATION — 600 s logical inputs; shared FSM, direct vs hormone CPG',fontsize=14)
    for ext in ('png','svg'):fig.savefig(out/f'input_ahm_overview.{ext}',dpi=150)
    plt.close(fig)

    fig,axes=plt.subplots(3,1,figsize=(12,8),sharex=True,layout='constrained')
    mask=[r for r in processed if 125<=r['time_s']<=175]
    axes[0].step([r['time_s'] for r in mask],[r['stimulus'] for r in mask],where='post',color='#303740')
    axes[0].set_ylabel('Shared S')
    for c,rows in traces.items():
        window=[r for r in rows[:-1] if 125<=r['t_s']<=175]
        axes[1].step([r['t_s'] for r in window],[r['phi_rad_per_update'] for r in window],where='post',color=colors[c],label=c)
        axes[2].plot([r['t_s'] for r in window],[r['o1'] for r in window],color=colors[c],label=c,linewidth=1.1)
    axes[1].set_ylabel('phi (rad/update)');axes[1].legend()
    axes[2].set_ylabel('CPG o1');axes[2].legend()
    axes[2].set_xlabel('Simulation time (s)')
    for ax in axes:ax.grid(alpha=.2);ax.set_xlim(125,175)
    fig.suptitle('SIMULATION — touch pulses and three-press burst; no extra stimulus hold',fontsize=13)
    for ext in ('png','svg'):fig.savefig(out/f'input_ahm_touch_detail.{ext}',dpi=150)
    plt.close(fig)


def run_experiment(output_dir,seeds=(41,42,43),make_plots=True):
    if not isinstance(seeds,(tuple,list)) or not 1<=len(seeds)<=10 or any(type(s) is not int for s in seeds) or len(set(seeds))!=len(seeds):
        raise ValueError('1..10 distinct integer seeds required')
    out=Path(output_dir).resolve()
    if not out.is_relative_to(model.ROOT):raise ValueError('output must be inside workspace')
    before=evidence.protected_hashes()
    out.mkdir(parents=True,exist_ok=False)
    config=evidence.configuration(len(seeds))
    config.update(experiment_id='lab07_logical_input_ahm_cpg_v1',duration_s=600.,seeds=list(seeds),
                  stimulus=dict(kind='approved logical input OR',formula='S=1 iff debounced button OR debounced touch OR approach OR near; else0; invalid=null',
                                hold_policy='no added pulse stretch; falling digital input also debounced',
                                near_enter_m=.20,near_exit_m=.28,approach_enter_m=.80,approach_exit_m=.95,
                                no_target_clear_s=.5,debounce_s=.06,stale_s=.12),
                  symbolic_fsm=dict(source='existing hardware-free AngryFSM and TouchBurst',ready='instantaneous symbolic entry; physical motion durations not modeled',
                                    interested_s=5.,happy_s=7.,angry_s=5.,sleep_idle_s=10.),
                  scenario='synthetic600s:button20/90/560;touch130/150/170/580 andburst155/155.4/155.8;approach190..230;near260..280/320..350/390..400;no_target280..285',
                  randomness='paired seeds add distance noise +/- .01m; noise remains away from thresholds; classified stimulus may be identical across seeds',
                  source_policy='logical samples already active-high; noGPIOraw levels, camera or motor behavior simulated')
    config['output_metrics']={'frequency':'rising crossings ofo1;1/mean completeperiods',
                              'delta_t':'absolute consecutiveperiodchange across600s',
                              'latency':'not reported by30sstep metric for this multiepisodeprotocol',
                              'physical_motion':'N/A'}
    evidence.json_write(out/'config.json',config)
    all_states=set();summaries=[];trial_records=[];stimulus_hashes={};raw_hashes={}
    reference_stimulus=None;across_seed_same=True
    for seed in seeds:
        frames=bridge.scenario(seed)
        # This v1 experiment preserves its original published protocol.
        processed=bridge.process_inputs(frames,stimulus_policy='approach_or_near_v1')
        replay=bridge.process_inputs(frames,stimulus_policy='approach_or_near_v1')
        if processed!=replay:raise RuntimeError('input/FSM replay differs')
        all_states.update(r['emotion'] for r in processed)
        inputs=out/f'input_seed{seed}';inputs.mkdir()
        model.write_csv(inputs/'raw_inputs.csv',bridge.raw_rows(frames))
        processed_rows=[{k:v for k,v in row.items() if k!='events'}|{'events_json':json.dumps(row['events'],separators=(',',':'))} for row in processed]
        model.write_csv(inputs/'processed_inputs.csv',processed_rows)
        raw_hashes[str(seed)]=hashlib.sha256((inputs/'raw_inputs.csv').read_bytes()).hexdigest()
        values=[r['stimulus'] for r in processed]
        if reference_stimulus is None:reference_stimulus=values
        else:across_seed_same=across_seed_same and values==reference_stimulus
        shared_digest=hashlib.sha256(json.dumps([dict(t_s=r['time_s'],source_id=r['source_id'],stimulus=r['stimulus'],emotion=r['emotion'],interaction=r['interaction']) for r in processed],allow_nan=False).encode()).hexdigest()
        traces={}
        for condition in ('C0','C1'):
            trace=model.simulate_samples(condition,values)
            replay_trace=model.simulate_samples(condition,values)
            if trace!=replay_trace:raise RuntimeError('CPG replay differs')
            trial=f'{condition}_seed{seed}';path=out/trial;path.mkdir()
            joined=[dict(row,source_id=processed[k]['source_id'],emotion=processed[k]['emotion'],interaction=processed[k]['interaction']) if k<len(processed)
                    else dict(row,source_id=None,emotion=None,interaction=None) for k,row in enumerate(trace)]
            model.write_csv(path/'trace.csv',joined)
            periods=model.output_periods([(r['t_s'],r['o1']) for r in trace])
            model.write_csv(path/'periods.csv',periods,['start_s','end_s','period_s','midpoint_s','frequency_hz'])
            summary=dict(condition=condition,seed=seed,**metrics(trace))
            evidence.json_write(path/'metrics.json',summary);summaries.append(summary)
            stimulus_hashes[trial]=shared_digest
            trial_records.append(dict(trial=trial,states=len(trace),intervals=len(trace)-1,observed_emotions=sorted({r['emotion'] for r in joined if r['emotion'] is not None})))
            traces[condition]=trace
        if seed==seeds[0] and make_plots:plot_result(out,processed,traces)
    evidence.json_write(out/'summary.json',summaries)
    model.write_csv(out/'metrics_summary.csv',summaries)
    verify=dict(paired_input_and_fsm_identical=all(stimulus_hashes[f'C0_seed{s}']==stimulus_hashes[f'C1_seed{s}'] for s in seeds),
                replay_verified=True,protected_files_unchanged=before==evidence.protected_hashes(),
                protected_file_hashes=before,states_observed=sorted(all_states),input_intervals_per_seed=12000,
                physical_robot_tested=False,human_scenario_completed=False,classified_stimulus_identical_across_seeds=across_seed_same,
                raw_input_sha256=raw_hashes,paired_input_fsm_sha256=stimulus_hashes,trials=trial_records)
    evidence.json_write(out/'verification.json',verify)
    if not verify['paired_input_and_fsm_identical'] or not verify['protected_files_unchanged']:raise RuntimeError('integrity check failed')
    snapshots=out/'source_snapshot';snapshots.mkdir()
    sources=[model.COURSE_PATH,model.CONTRACT_PATH,model.REFERENCE_PATH,Path(model.__file__),Path(bridge.__file__),Path(__file__),Path(evidence.__file__),
             model.ROOT/'bio_inspire/runtime/lab_fsm.py',model.ROOT/'bio_inspire/runtime/angry_fsm.py']
    for p in sources:shutil.copyfile(p,snapshots/p.name)
    a,b=summaries[0],summaries[1]
    counts=Counter(r['emotion'] for r in processed)
    report=f'''# Lab07: input → AHM → CPG บนคอม

**ผลจำลอง ไม่ใช่การทดลองคนหรือมอเตอร์จริง**

## สิ่งที่เชื่อมแล้ว

ปุ่ม/Touchที่ผ่านdebounceหรือระยะapproach/nearให้S=1;ไม่มีinputเหล่านี้ให้0 ใช้ORไม่บวกน้ำหนัก ไม่ยืดpulseเพิ่ม และไม่ใช้ชื่ออารมณ์เป็นตัวสร้างS ทั้งC0/C1รับข้อมูลและFSMเดียวกัน C0ใช้R=S;C1ใช้AHMอาจารย์rates.8/.6/.2ปรับphiผ่านmappingเดิม

ToF no_targetเป็นข้อมูลว่าไม่มีวัตถุ ไม่ใช่faultและไม่ใส่ระยะปลอม ถ้าno_targetต่อเนื่อง.5sให้clear ระยะจริงใช้near20/clear28cmและapproach80/exit95cm ส่วนข้อมูลinvalid/staleจริงทำให้S=nullและใช้fallbackของcoursemodel

ใช้FSM6stateเดิมแบบpurePython: normal/interested/happy/afraid/sleepy/angry;touch3ครั้งใน2sเข้าAngryและNearรอจนAngryครบ5s การเข้าท่าถูกสมมติว่าพร้อมทันที จึงไม่ใช้เวลาการเปลี่ยนstateในชุดนี้แทนlatencyของท่ามอเตอร์

## การทดลอง

จำลอง600sต่อrunที่dt.05s จำนวน{len(seeds)}pairedseeds รวม{len(seeds)*2}runs บันทึกrawinputs12000intervalsต่อseedและCPG12001statesต่อcondition มีภาพรวม600sและภาพTouchdetail125–175sถ้าเปิดplot

seedsเติมnoiseระยะ±.01mไกลจากthreshold ผลclassifiedSเหมือนกันทุกseed={across_seed_same} จึงไม่ถือว่าผลสามรอบเป็นอิสระหรือพิสูจน์ความทนทานต่อnoiseใกล้threshold ทุกคู่ใช้rawเดียวกันและตรวจexactreplayซ้ำ

พบstateครบ: {', '.join(sorted(all_states))} จำนวนsamplesตามstateในseedสุดท้าย: {dict(counts)} ตัวเลขนี้เป็นsimulation ไม่ใช่เวลารันทดสอบกับผู้เล่น

## ผลseedแรก

| Metric | C0 direct | C1 hormone |
|---|---:|---:|
| maxΔphi ต่อupdate(rad) | {a['phi_max_step_rad']:.6f} | {b['phi_max_step_rad']:.6f} |
| ความถี่เฉลี่ยจากคาบo1ครบทั้ง600s(Hz) | {a['frequency_hz']:.6f} | {b['frequency_hz']:.6f} |
| maxΔTของคาบติดกัน(s) | {a['delta_t_max_s']:.6f} | {b['delta_t_max_s']:.6f} |
| meanΔTของคาบติดกัน(s) | {a['delta_t_mean_s']:.6f} | {b['delta_t_mean_s']:.6f} |

ไม่ใช้commandlatency10/20sของstepทดลองเดิมกับprotocolหลายเหตุการณ์นี้ ค่าเฉลี่ยความถี่ทั้งrunรวมidleยาวไม่แทนความถี่ขณะTouch/nearแต่ละช่วง ดูperiods.csvหรือกราฟประกอบ

เมื่อTouchสั้นAHMสะสมได้น้อยกว่าToFที่ค้างในระยะนาน ผลนี้เป็นผลของmappingที่เลือก ไม่ใช่บั๊กหรือเหตุผลให้เพิ่มน้ำหนัก/ยืดpulseโดยไม่ตกลงก่อน CPGยังมีในทุกstateรวมSleepyโดยคงphaseต่อเนื่อง สถานะไม่เป็นตัวเลือกปิดCPGในแบบจำลองนี้

## หลักฐานและสิ่งที่ยังเหลือ

raw_inputs.csvเก็บlogicalbutton/touch,ToFkind/distance,เวลาจำลองและsource_id;processed_inputs.csvเก็บS/เหตุการณ์/FSM;trace.csvเก็บH/R/phi/o1/o2และเวลาเดิม/ถัดไป ส่วนconfig/source_snapshot/manifest/verificationเก็บที่มาคำนวณและhashes

โค้ดนี้ยังไม่อ่านGPIO/I2CบนPi ไม่ส่งROSหรือUART และไม่แก้ท่าทาง/PIDจริง ขั้นต่อไปคือliveinputadapterที่คงsource-time/qualitycontractนี้และROSoutputadapterที่ใช้UARTownerเดิม ก่อนทดสอบrobotและhuman10นาทีจริง
'''
    (out/'REPORT_TH.md').write_text(report,encoding='utf-8')
    manifest={p.relative_to(out).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file()}
    evidence.json_write(out/'manifest.json',dict(experiment_id=config['experiment_id'],files=manifest))
    return out


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--no-plots',action='store_true')
    args=parser.parse_args()
    print(run_experiment(args.out,make_plots=not args.no_plots))
