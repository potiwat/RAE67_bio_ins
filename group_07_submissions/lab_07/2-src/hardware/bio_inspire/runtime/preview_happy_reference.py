"""Export offline design figures; never imports a camera/transport or opens GUI."""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'shared/runtime'))
from bio_inspire.runtime.happy_path import HappyReferencePath, CpgPhaseProgress, JointLoopPreview
from bio_inspire.runtime.body_rhythm import BodyRhythm
from motion_timing import CommandState, QuinticTransition


def export_preview(output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    path = HappyReferencePath()
    progress = [n/1000 for n in range(1001)]
    targets = [path.sample(u) for u in progress]
    figure, axes = plt.subplots(1, 2, figsize=(12, 6))
    figure.suptitle('HAPPY DESIGN REFERENCE — NOT A CALIBRATED HEAD OR MOTOR PATH')
    axes[0].plot([t.position[0] for t in targets[:501]], [t.position[1] for t in targets[:501]], label='first: viewer-left lobe')
    axes[0].plot([t.position[0] for t in targets[500:]], [t.position[1] for t in targets[500:]], label='then: viewer-right lobe')
    for u in (.05, .15, .3, .4, .55, .65, .8, .9):
        a, b = path.sample(u), path.sample(u+.015)
        axes[0].annotate('', xy=b.position, xytext=a.position, arrowprops=dict(arrowstyle='->', color='black'))
    axes[0].scatter([0], [0], color='black', s=25)
    axes[0].set(xlabel="Viewer's horizontal axis (dimensionless; right is +)",
                ylabel='Reference height (dimensionless; up is +)', title='1: left lobe → 2: right lobe (same heights)')
    axes[0].set_aspect('equal', adjustable='datalim')
    axes[0].grid(alpha=.25)
    axes[1].plot(progress, [t.position[0] for t in targets], label='reference x')
    axes[1].plot(progress, [t.position[1] for t in targets], label='reference y')
    axes[1].set(xlabel='One CPG cycle progress (not seconds)', ylabel='Dimensionless position',
                title='Shape is separate from pace; no pause at each drawn point')
    axes[1].grid(alpha=.25)
    axes[1].legend()
    figure.tight_layout(rect=(0, .03, 1, .94))
    figure.text(.5, .015, 'Concept shape only: no raw-to-URDF zero, camera calibration, IK, collision or wire clearance inferred.', ha='center', fontsize=9)
    figure.savefig(output / 'happy_reference.png', dpi=140)
    plt.close(figure)

    template_path=ROOT/'bio_inspire/hardware/happy_loop_template.json'
    template=json.loads(template_path.read_text())
    joint_loop=JointLoopPreview.from_template(template)
    joint_samples=[joint_loop.sample(u) for u in progress]
    figure,axes=plt.subplots(3,1,figsize=(11,8),sharex=True)
    figure.suptitle('TAUGHT JOINT-SPACE PREVIEW — NOT SENT TO MOTORS')
    for index,axis in enumerate(axes):
        axis.plot(progress,[q[index] for q in joint_samples])
        axis.set_ylabel(f'ID{index+1} raw reference')
        axis.grid(alpha=.25)
    axes[-1].set_xlabel('One CPG cycle progress; body commands share the same phase')
    figure.tight_layout(rect=(0,.03,1,.95))
    figure.text(.5,.015,'Equal left/right joint references do not prove equal Cartesian heights. ID4/5 gaze is not solved here.',ha='center',fontsize=9)
    figure.savefig(output/'happy_joint_reference.png',dpi=140);plt.close(figure)
    joint_report=dict(status='offline_joint_space_preview_not_deployed',
        source_template=str(template_path.relative_to(ROOT)),
        source_template_sha256=hashlib.sha256(template_path.read_bytes()).hexdigest(),
        references=[dict(progress=u,raw_reference=list(q)) for u,q in zip(progress,joint_samples)],
        exact_ranges_raw={'1':[joint_loop.center_yaw-joint_loop.yaw_span,joint_loop.center_yaw+joint_loop.yaw_span],
                          '2':[joint_loop.upper[0],joint_loop.lower[0]],'3':[joint_loop.upper[1],joint_loop.lower[1]]},
        head_goals=None,actual_head_path=None,hardware_validated=False,
        limitation='Taught anchors are observations, not approved full-loop command bounds; entry, final gaze and physical path require separate validation.')
    (output/'happy_joint_reference_summary.json').write_text(json.dumps(joint_report,indent=2,allow_nan=False),encoding='utf-8')

    # Same retained oscillator and accepted time scales; diagram only, no goals.
    rhythm = BodyRhythm(phi=.1, time_scale=.5)
    tracker = CpgPhaseProgress()
    phase_trace = []
    for n in range(601):
        now = n/20
        rhythm.advance(now, active=not 8 <= now <= 12, exclusive=8 <= now <= 12)
        phase_trace.append(dict(time_s=now, progress=tracker.advance(rhythm.o1, rhythm.o2, rhythm.updates, now),
                                output_masked=8 <= now <= 12))
    # Unit-test illustration only, explicitly unrelated to selected hardware PID,
    # speed register or target poses. Demonstrates nonzero v/a at interruption.
    states = lambda q, v=0., a=0.: {i: CommandState(q, v, a) for i in range(1, 6)}
    original = QuinticTransition(states(2000.), states(2100.), 4.)
    cut_s = 1.4
    replacement = QuinticTransition(original.sample(cut_s), states(1900.), 5.)
    times = [n/100 for n in range(641)]
    samples = [original.sample(t)[1] if t <= cut_s else replacement.sample(t-cut_s)[1] for t in times]
    figure, axes = plt.subplots(3, 1, figsize=(11, 8), sharex=True)
    figure.suptitle('QUINTIC INTERRUPTION ILLUSTRATION — SYNTHETIC TEST VALUES, NOT HARDWARE SETTINGS')
    for axis, field, label in zip(axes, ('q', 'v', 'a'), ('Command ticks', 'Command ticks/s', 'Command ticks/s²')):
        axis.plot(times, [getattr(sample, field) for sample in samples])
        axis.axvline(cut_s, color='red', linestyle='--', label='request changes while moving')
        axis.set_ylabel(label)
        axis.grid(alpha=.25)
    axes[0].legend()
    axes[2].set_xlabel('Synthetic example time (s); floating commands only, not measured/quantized')
    figure.tight_layout(rect=(0, 0, 1, .95))
    figure.savefig(output / 'transition_reference.png', dpi=140)
    plt.close(figure)

    raw_source = ROOT / 'shared/hardware/pose_observations_20261102.json'
    report = dict(status='offline_reference_only_not_deployed',
                  path=dict(frame='player_view_reference', units='dimensionless',
                            convention='theta=2*pi*CPG_progress; x=-sin(theta); y=sin(2*theta)+sin(theta)^2',
                            exact_ellipses=False, hardware_validated=False, motor_goals=None),
                  calibration='N/A: raw/model zero-sign-offset and camera/head relationship incomplete',
                  source_raw_sha256=hashlib.sha256(raw_source.read_bytes()).hexdigest(),
                  raw_source=str(raw_source.relative_to(ROOT)), raw_source_changed=False,
                  phase_evidence=phase_trace,
                  transition=dict(example='synthetic unit-test data; not a proposed profile',
                                  continuity='q/v/a preserved at interruption; jerk continuity is not guaranteed',
                                  quantized_limits='not yet validated', actual_motion='N/A'),
                  remaining=['Migrate command-frame producers', 'Calibrate/verify ID4 and raw/model/head mapping',
                             'Constrained physical path/gaze solving', 'Quantization and final summed limits',
                             'Hardware validation of shape, gaze and dynamics'])
    (output / 'happy_reference_summary.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    return report


if __name__ == '__main__':
    result = export_preview(ROOT / 'bio_inspire/hardware/offline_motion_baseline')
    print(json.dumps(dict(status=result['status'], output='bio_inspire/hardware/offline_motion_baseline', motor_goals=None)))
