"""PC-only evidence exporter. Run as python -B -m bio_inspire.experiments.run_ahm_cpg_compare."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import shutil

from . import ahm_cpg_compare as model


def hashes(paths):
    return {str(p.relative_to(model.ROOT)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(paths) if p.is_file()}


def protected_hashes():
    return hashes([*model.ROOT.glob('bio_inspire/runtime/*.py'),
                   *model.ROOT.glob('shared/runtime/*.py'),
                   *model.ROOT.glob('shared/hardware/*pid*.json'),
                   model.ROOT/'bio_inspire/hardware/afraid_pose_trial.json',
                   model.ROOT/'shared/hardware/PID_SELECTED_TH.md'])


def json_write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def configuration(repeats):
    return dict(experiment_id='lab07_ahm_cpg_phi_only_v1', platform='PC numerical simulation',
                conditions={'C0': 'direct R_used=S (Lab05 B1)', 'C1': 'hormone R_used=H_k (Lab05 B2)'},
                duration_s=model.DURATION, dt_s=model.DT, warmup_s=10.,
                warmup_initial=[.1, 0.], warmup_command={'alpha': 1.1, 'phi_rad_per_update': .2},
                shared_cpg_initial=list(model.warmup()), hormone_initial=0., alpha=1.1,
                hormone_rates={'production': .8, 'clearance': .6, 'binding': .2},
                mapping={'phi_baseline': .2, 'phi_gain': .2, 'phi_bounds': [.1, .45], 'mode': 'phi-only'},
                stimulus={'kind': 'Lab05 step', 'on_start_s': 10., 'off_start_s': 20., 'low': 0., 'high': 1.},
                timing='command at t_k uses old H/R; simultaneous CPG update; hormone end-state at t_(k+1)',
                output_metrics={'frequency': '1/mean complete rising-zero-crossing periods; linear crossing interpolation',
                                'delta_t': 'abs(T_n - T_(n-1)); all adjacent periods include transitions',
                                'segment_membership': 'both crossing endpoints inside segment',
                                'command_latency': 'first phi >= baseline + 10% of step after on',
                                'command_recovery': 'first phi within 10% of step from baseline after off, sustained 1s'},
                repeats_per_condition=repeats, randomness='none; repeats test replay, not independent statistical trials',
                claim_boundary='No physical robot, actuator dynamics, FSM, live sensors, ROS or hardware motion measured',
                source_hashes=model.source_hashes(), python=platform.python_version(),
                created_utc=datetime.now(timezone.utc).isoformat())


def plot_comparison(output, traces):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    colors = {'C0': '#2166ac', 'C1': '#c05a12'}
    labels = {'C0': 'C0 direct stimulus', 'C1': 'C1 via hormone'}
    fig, axes = plt.subplots(4, 1, figsize=(12, 10), sharex=True, layout='constrained')
    c0 = traces['C0']
    axes[0].step([r['t_s'] for r in c0[:-1]], [r['stimulus'] for r in c0[:-1]], where='post', color='#303740', label='Shared S')
    axes[0].set_ylabel('Stimulus S')
    axes[0].set_ylim(-.08, 1.15)
    for name, rows in traces.items():
        commands = rows[:-1]
        ts = [r['t_s'] for r in commands]
        axes[1].step(ts, [r['r_used'] for r in commands], where='post', color=colors[name], label=labels[name])
        axes[2].step(ts, [r['phi_rad_per_update'] for r in commands], where='post', color=colors[name], label=labels[name])
        axes[3].plot([r['t_s'] for r in rows], [r['o1'] for r in rows], color=colors[name], linewidth=1.3, label=labels[name])
    axes[1].set_ylabel('R used (C1 = H)')
    axes[2].set_ylabel('phi (rad/update)')
    axes[3].set_ylabel('CPG output o1')
    axes[3].set_xlabel('Simulation time (s)')
    for ax in axes:
        ax.axvspan(10, 20, color='#c6d6c9', alpha=.25)
        ax.grid(alpha=.2)
        ax.legend(loc='upper right', fontsize=9)
        ax.set_xlim(0, 30)
    fig.suptitle('SIMULATION — same stimulus, same SO(2), only modulation path differs', fontsize=14)
    for suffix in ('png', 'svg'):
        fig.savefig(output/f'ahm_cpg_comparison.{suffix}', dpi=160)
    plt.close(fig)

    fig, axes = plt.subplots(2, 1, figsize=(12, 7), sharex=True, layout='constrained')
    for name, rows in traces.items():
        periods = model.output_periods([(r['t_s'], r['o1']) for r in rows])
        axes[0].plot([p['end_s'] for p in periods], [p['frequency_hz'] for p in periods], '.-', color=colors[name], label=labels[name])
        axes[1].plot([b['end_s'] for a, b in zip(periods, periods[1:])],
                     [abs(b['period_s']-a['period_s']) for a, b in zip(periods, periods[1:])],
                     '.-', color=colors[name], label=labels[name])
    axes[0].set_ylabel('1 / cycle period (Hz)')
    axes[1].set_ylabel('Adjacent period change (s)')
    axes[1].set_xlabel('End of measured cycle (simulation s)')
    for ax in axes:
        ax.axvspan(10, 20, color='#c6d6c9', alpha=.25)
        ax.grid(alpha=.2)
        ax.legend(loc='upper right')
        ax.set_xlim(0, 30)
    fig.suptitle('SIMULATION — frequency and period change measured from o1', fontsize=14)
    for suffix in ('png', 'svg'):
        fig.savefig(output/f'cpg_output_metrics.{suffix}', dpi=160)
    plt.close(fig)


def write_report(output, metrics, repeats, plots):
    a, b = metrics['C0'], metrics['C1']
    def fmt(v):
        return 'N/A' if v is None else f'{v:.6f}'
    rows = []
    for label, key in [('max Δφ / update (rad)', 'phi_max_step_rad'),
                       ('ΔT mean, all adjacent periods (s)', 'delta_t_mean_s'),
                       ('ΔT max, all adjacent periods (s)', 'delta_t_max_s'),
                       ('Command latency, 10% (s)', 'command_latency_10pct_s'),
                       ('Command recovery, 10% sustained1s (s)', 'command_recovery_10pct_s')]:
        rows.append(f'| {label} | {fmt(a[key])} | {fmt(b[key])} |')
    for segment in model.SEGMENTS:
        rows.append(f"| Frequency {segment}, complete periods (Hz) | {fmt(a['segments'][segment]['frequency_hz'])} | {fmt(b['segments'][segment]['frequency_hz'])} |")
    text = f'''# ผลจำลอง Lab07: ปรับจังหวะตรง เทียบกับผ่าน AHM

**ผลจำลองจากสิ่งกระตุ้นเดียวกัน ไม่ใช่ผลทดลองบนโคม**

C0 ใช้ R=S ตาม Lab05 B1; C1 ใช้ H/R จาก production–clearance–binding ตาม B2 สมการและฟังก์ชัน hormone_step/mapped_parameters/step_cpg เรียกจากไฟล์ Lab05 ที่เก็บไว้จริง ไม่ใช้ decoder หกขา ไม่เปลี่ยนโค้ดมอเตอร์ ท่าทาง หรือ PID

## Protocol

- ทั้งคู่ใช้ alpha1.1, dt.05s, phi=clip(.2+.2R,.1,.45), H0=0, rates(.8,.6,.2)
- Warm-upร่วม10s แล้วเริ่มสถานะCPGเดียวกัน สังเกต30s; S=0ช่วง0–10s,1ช่วง10–20s,0ช่วง20–30s
- C1ใช้Hต้นintervalสร้างphi แล้วจึงอัปเดตฮอร์โมนไว้รอบถัดไป ส่วนC0ใช้Sทันที ไม่มีการresetCPGตอนSเปลี่ยน
- คงmodel timeจริงตามLab05 ไม่มีtime_scale.5จากงานหายใจฮาร์ดแวร์ จึงห้ามใช้ความถี่นี้แทนความถี่โคมปัจจุบัน
- ทำซ้ำ{repeats}รอบต่อcondition รวม{2*repeats}รอบ เป็นdeterministic replay ไม่ใช่independent trials ไม่รายงานp-value/SEMหรือความแปรปรวนเป็นหลักฐานความทนทาน
- step inputเป็นunit experimentของLab05 ยังไม่ใช่scenarioคน10นาที และยังไม่กำหนดbutton/Touch/ToF→S

## ผล

| Metric | C0 direct | C1 hormone |
|---|---:|---:|
{chr(10).join(rows)}

จำนวนคาบครบในpre/on/off: C0={a['segments']['pre']['period_count']}/{a['segments']['on']['period_count']}/{a['segments']['off']['period_count']}; C1={b['segments']['pre']['period_count']}/{b['segments']['on']['period_count']}/{b['segments']['off']['period_count']} ใช้เฉพาะคาบที่ทั้งสองจุดตัดอยู่ภายในsegment ส่วนΔTรวมทั้งrunใช้ทุกคาบรวมที่คร่อมการเปลี่ยนinput

## การตีความ

AHMลดการกระโดดสูงสุดของพารามิเตอร์phiได้ชัด แต่มีlatencyและหางการคืนbaseline ขณะที่ΔTสูงสุดจากo1ลดลง และΔTเฉลี่ยรวมแทบไม่ต่าง จึงไม่ควรสรุปว่าAHMดีขึ้นทุกmetric หรือค่าmaxΔphiลดลงกี่เท่าแล้วความสมูททางกายภาพดีขึ้นเท่านั้น

ΔTภายในช่วงon/offของC1อาจมากกว่าC0 เพราะความถี่กำลังค่อยเปลี่ยน ส่วนC0กระโดดแล้วคงที่ ความต่างนี้ไม่ขัดกับผลmaxΔTรวมซึ่งรวมช่วงข้ามtransition ต้องรายงานทั้งค่าเฉลี่ย/ค่าสูงสุดและนิยามหน้าต่าง

กราฟphiแสดงการเปลี่ยนพารามิเตอร์; ความถี่และΔTคำนวณจากrising zero crossingsของo1พร้อมlinear interpolation ไม่แปลงphiเป็นHzตรง ๆ ไม่ใช้physicaljerkหรือencoderจากsimulationนี้

## แหล่งและไฟล์

- Lab02: แนวทางแยกinput/filter/controller/output, boundsและcontrolledcomparison ไม่เติมfilterให้ต่างกันระหว่างC0/C1
- Lab03/04/05: SO(2), hormone, phi-only mapping; teacher commit fa528b169f1127ee3e0e9fae3d721546bf1b82d2 และgroup snapshotที่เก็บในLab07/worksheet_review/section4_sources
- config.json บันทึกsourcehashes/initialstates/metricdefinitions; source_snapshotเก็บsourceของrunner/modelและcourseที่ใช้
- C0_r01..C1_r{repeats:02d}/trace.csv มี601state rowsและ600commands, input_trace.csvมี600inputintervals; periods.csvเก็บคาบจากo1
- verification.json ตรวจinputคู่เดียวกัน, replayและprotectedfiles; manifest.jsonเก็บSHA256ของไฟล์ผล
- กราฟ {'ahm_cpg_comparison.png/.svg และ cpg_output_metrics.png/.svg' if plots else 'ไม่ได้สร้างในรอบ --no-plots'}

## งานถัดไป

กำหนดmappinginputจริง→S และprotocol10นาที จากนั้นเชื่อมROS2และAHMกับUARTownerเดิมโดยคงท่ากับPIDที่รับไว้ การกระตุกของมอเตอร์ยังเป็นข้อจำกัดที่ต้องแยกรายงานจากความต่อเนื่องของCPG
'''
    (output/'REPORT_TH.md').write_text(text, encoding='utf-8')


def run_experiment(output_dir, repeats=3, make_plots=True):
    if type(repeats) is not int or not 1 <= repeats <= 20:
        raise ValueError('repeats must be an integer in 1..20')
    output = Path(output_dir).resolve()
    if not output.is_relative_to(model.ROOT):
        raise ValueError('output must remain inside the Lamp workspace')
    before = protected_hashes()
    output.mkdir(parents=True, exist_ok=False)
    config = configuration(repeats)
    json_write(output/'config.json', config)
    traces, summaries, trial_reports = {}, {}, []
    input_digests, trace_digests = {}, {}
    for condition in ('C0', 'C1'):
        for repeat in range(1, repeats+1):
            name = f'{condition}_r{repeat:02d}'
            trial = output/name
            trial.mkdir()
            trace = model.simulate(condition)
            metrics = model.analyze(trace)
            model.write_csv(trial/'trace.csv', trace)
            model.write_csv(trial/'input_trace.csv', [dict(input_id=k, t_s=r['t_s'], stimulus=r['stimulus'], valid=not r['fault']) for k, r in enumerate(trace[:-1])])
            periods = model.output_periods([(r['t_s'], r['o1']) for r in trace])
            model.write_csv(trial/'periods.csv', periods, ['start_s', 'end_s', 'period_s', 'midpoint_s', 'frequency_hz'])
            json_write(trial/'metrics.json', metrics)
            trial_reports.append(dict(trial=name, states=len(trace), intervals=len(trace)-1, period_count=metrics['period_count']))
            input_digests[name] = hashlib.sha256((trial/'input_trace.csv').read_bytes()).hexdigest()
            trace_digests[name] = hashlib.sha256((trial/'trace.csv').read_bytes()).hexdigest()
            traces[condition], summaries[condition] = trace, metrics
    verification = dict(trials=trial_reports,
                        paired_stimulus_identical=len(set(input_digests.values())) == 1,
                        deterministic_repeats_identical=all(len({trace_digests[f'{c}_r{r:02d}'] for r in range(1, repeats+1)}) == 1 for c in ('C0', 'C1')),
                        protected_files_unchanged=before == protected_hashes(),
                        protected_file_hashes=before, input_sha256=input_digests, trace_sha256=trace_digests,
                        independent_repeats=False, physical_robot_tested=False)
    if not all(verification[key] for key in ('paired_stimulus_identical', 'deterministic_repeats_identical', 'protected_files_unchanged')):
        json_write(output/'verification.json', verification)
        raise RuntimeError('experiment integrity check failed')
    json_write(output/'verification.json', verification)
    json_write(output/'summary.json', summaries)
    model.write_csv(output/'metrics_summary.csv', [dict(condition=c, **{k: v for k, v in m.items() if k != 'segments'}) for c, m in summaries.items()])
    snapshots = output/'source_snapshot'
    snapshots.mkdir()
    for p in (model.COURSE_PATH, model.CONTRACT_PATH, model.REFERENCE_PATH, Path(model.__file__), Path(__file__)):
        shutil.copyfile(p, snapshots/p.name)
    if make_plots:
        plot_comparison(output, traces)
    write_report(output, summaries, repeats, make_plots)
    entries = {str(p.relative_to(output)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest()
               for p in sorted(output.rglob('*')) if p.is_file()}
    json_write(output/'manifest.json', dict(experiment_id=config['experiment_id'], files=entries,
                                          provenance='hashes of bytes actually generated; manifest excludes itself'))
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True, help='new output directory inside workspace; never overwritten')
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--no-plots', action='store_true')
    args = parser.parse_args()
    print(run_experiment(args.out, args.repeats, not args.no_plots))


if __name__ == '__main__':
    main()
