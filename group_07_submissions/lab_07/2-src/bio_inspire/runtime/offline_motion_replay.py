"""Replay the existing supervised behavior/CPG logic without any device.

This is an ideal one-tick-following model, NOT a servo dynamics simulator,
calibrated FK/IK, the full course FSM, or evidence of physical smoothness.
No CameraMotor constructor, worker thread, camera, GPIO, UART or PID writes.
"""
import argparse
import csv
import hashlib
import json
import math
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'shared/runtime'))
from motion_trace import MotionTrace
from normal_gaze_motor import NormalGaze
from physical_button import ButtonEdge
from visual_servo import VisualServo
from manual_tuning import trajectory_speed_limit
from bio_inspire.runtime.camera_motor import CameraMotor
from bio_inspire.runtime.body_rhythm import BodyRhythmDriver
from bio_inspire.runtime.three_state_behavior import service_state_outputs


class ReplayBus:
    """Memory transport; all feedback is explicitly synthetic, no serial fallback."""
    def __init__(self, origin):
        self.pos = dict(origin)
        self.reg = {i: {18: 12, 33: 0, 40: 0, 41: 0, 42: v, 46: 0, 64: 0, 65: 0}
                    for i, v in origin.items()}
        self.windows = {}
        self.armed = set()
        self.writes = []
        self.producer = 'startup'
        self.time_s = 0.

    def advance(self, now):
        self.time_s = now
        for i in self.pos:
            if self.reg[i][40] == 1:
                self.pos[i] = self.reg[i][42]
        self.writes = []

    def snapshot(self):
        return [dict(id=i, position_raw=self.pos[i], torque_raw=self.reg[i][40],
                     status_raw=self.reg[i][65], mode=0, speed_raw=0, moving_raw=0)
                for i in range(1, 6)]

    def read(self, sid, address, count):
        if address == 56 and count == 8:
            return self.pos[sid].to_bytes(2, 'little') + bytes(6)
        return self.reg[sid][address].to_bytes(count, 'little')

    def write(self, sid, address, data):
        value = int.from_bytes(data, 'little')
        if sid not in self.reg or address not in (40, 41, 42, 46):
            raise ValueError('Replay forbids PID/EEPROM/unknown writes')
        if address == 42:
            low, high = self.windows[sid]
            if len(data) != 2 or not low <= value <= high or not 0 <= value <= 4095:
                raise ValueError('Replay goal outside current controller window')
        if address == 40 and value != 1:
            raise ValueError('No automatic torque release')
        self.reg[sid][address] = value
        self.writes.append(dict(joint_id=sid, address=address, value=value,
                                producer=self.producer, sent_s=self.time_s,
                                readback_s=self.time_s, readback_tick=value,
                                evidence='synthetic_memory_ack_and_readback'))

    def hold_actual(self, sid):
        old = self.windows.get(sid)
        self.windows[sid] = (self.pos[sid], self.pos[sid])
        try:
            self.write(sid, 42, self.pos[sid].to_bytes(2, 'little'))
        finally:
            if old is not None:
                self.windows[sid] = old


class ReplayInput:
    def __init__(self, debounce_s):
        self.edge = ButtonEdge(debounce_s)
        self.pressed = False

    def poll(self, now):
        return self.edge.update(self.pressed, now)


class ReplayLed:
    """Only keeps a label; never imports SPI/GPIO libraries."""
    state = None
    def normal(self): self.state = 'normal'
    def interested(self): self.state = 'interested'
    def sleepy(self): self.state = 'sleepy'
    def happy(self): self.state = 'happy'
    def close(self): self.state = None


class ReplayMotor(CameraMotor):
    def __init__(self, profile, now):
        # Intentionally do not call live constructor: it opens UART and a worker.
        self._time = now
        self.now = lambda: self._time
        normal = {int(k): v for k, v in profile['normal_raw'].items()}
        origin = {int(k): v for k, v in profile['origin_raw'].items()}
        self.bus = ReplayBus(origin)
        self.bus.time_s = now
        self.controller = NormalGaze(
            self.bus, origin, normal, tracking_speed=profile['speed_raw'],
            tracking_acceleration=profile['acceleration_raw'], yaw_range_deg=profile['yaw_range_deg'],
            manual_tuning=profile.get('manual_tuning', False), command_margin_ticks=profile.get('command_margin_ticks', 0),
            pitch_probe=profile.get('pitch_probe_enabled', False),
            pitch_tracking=profile.get('vertical_tracking_enabled', False), pitch_range_deg=profile.get('pitch_range_deg', 3),
            motion_speed=profile.get('motion_speed_raw', 1),
            normal_tolerances={int(k): v for k, v in profile.get('normal_tolerances_ticks', {}).items()},
            pitch_up_deg=profile.get('gaze_pitch_up_deg'))
        c = self.controller
        self.lock = threading.Lock()
        self.stopping = threading.Event()
        self.urgent_stop = threading.Event()
        self.behavior_trial = 'normal'
        self.pending_behavior = None
        self.operator_stopped = False
        self.gaze_enabled = profile.get('gaze_enabled', True)
        self.pitch_enabled = profile.get('vertical_tracking_enabled', False)
        self.yaw_follow_enabled = profile.get('yaw_follow_enabled', True)
        self.pitch_direction = profile.get('pitch_direction', 1)
        self.pitch_clearance_confirmed = self.yaw_clearance_confirmed = True
        self.follow_enabled = self.held = self.joint_mode = self.sleepy_trial_active = False
        self.state_leds_enabled = profile.get('state_leds_enabled', False)
        self.led_ring = ReplayLed()
        self.head_probe_active = self.head4_probe_enabled = False
        self.tune_pending = self.tune_job = None
        self.tune_status = ''
        self.tuning_enabled = False
        self.interested_roll_due = self.route_completion_seen = None
        self.touch_required_for_happy = profile.get('touch_required_for_happy', False)
        self.happy_yaw_enabled = profile.get('happy_yaw_enabled', False)
        self.touch_sequence = self.button_sequence = 0
        self.physical_touch = ReplayInput(profile.get('touch_debounce_s', .06))
        self.physical_button = ReplayInput(profile.get('button_debounce_s', .06))
        self.rhythm_pending = None
        self.rhythm_normal_gaze_started = False
        self.rhythm_view_cache = {}
        self.visual = VisualServo(c.yaw_window[0] + c.command_margin_ticks, c.yaw_window[1] - c.command_margin_ticks,
                                  trajectory_speed_limit(c.tracking_speed), c.tracking_acceleration * 8.7 * 4096 / 360,
                                  profile.get('filter_beta', .25), profile.get('deadband_px', 6), 160., .5)
        self.pitch_visual = VisualServo(*c.pitch_window, trajectory_speed_limit(c.motion_speed),
                                        8.7 * 4096 / 360, profile.get('filter_beta', .25),
                                        profile.get('deadband_px', 6), 90., .5) if self.pitch_enabled else None
        self.rhythm_driver = BodyRhythmDriver(
            normal_amplitude_deg=profile.get('cpg_normal_amplitude_deg', 1.),
            normal_amplitude_mode=profile.get('cpg_normal_amplitude_mode', 'fixed'),
            variation_seed=profile.get('cpg_variation_seed', 0),
            interested_amplitude_deg=profile.get('cpg_interested_amplitude_deg', 1.),
            phi=profile.get('cpg_phi_rad', .2), active_joint_ids=tuple(profile.get('cpg_active_joint_ids', [2, 3])),
            time_scale=profile.get('cpg_time_scale', 1.), sleepy_amplitude_deg=profile.get('cpg_sleepy_amplitude_deg', 0.),
            happy_amplitude_deg=profile.get('cpg_happy_amplitude_deg', 0.),
            happy_time_scale=profile.get('cpg_happy_time_scale', .75), happy_body_excursion_deg=profile.get('happy_body_excursion_deg')) if profile.get('cpg_trial_enabled') else None
        c.interest_head_tracking = self.gaze_enabled and self.pitch_enabled
        c.interest_pitch_window_request = c.pitch_window
        c.set_direction(profile.get('yaw_direction', 1))
        c.start(now)

    def _key(self, key):
        self.ensure_fake_led()
        return super()._key(key)

    def ensure_fake_led(self):
        if self.led_ring is None:
            self.led_ring = ReplayLed()

    def service(self, now, face, events):
        self._time = now
        self.bus.advance(now)
        for event in events:
            kind = event['kind']
            if kind in ('touch', 'button'):
                getattr(self, 'physical_' + kind).pressed = event['pressed']
            elif kind == 'state':
                self.bus.producer = 'state_request'
                self._key(ord(dict(normal='n', interested='i', sleepy='s', happy='d')[event['state']]))
            elif kind == 'stop':
                self.bus.producer = 'operator_stop'
                self._key(ord('h'))
        status, error_xy = face['status'], face['error_xy']
        # Default is an explicitly synthetic continuous centered-face stream.
        # An explicit face event is ONE sample: keep its timestamp and identity.
        captured = face.get('captured_s', now)
        age = now - captured
        obs = dict(status=status, captured_s=captured,
                   source_id=face.get('source_id', f'synthetic_stream_{int(now * 1000000)}'))
        fresh = 0 <= age <= .5 and status in ('TRACKING', 'ACQUIRED')
        self.latest_result = dict(state=self.behavior_trial, observation=obs,
                                  intent=dict(mode='FOLLOW' if status in ('TRACKING', 'ACQUIRED') else 'SEARCH', error_xy=error_xy))
        self.controller.face_ready_for_interest = fresh
        self.bus.producer = 'controller_route'
        self.controller.tick(now)
        self.bus.producer = 'physical_input'
        touched = self._poll_physical_touch(now)
        self._poll_physical_button(now, suppress=touched)
        self.bus.producer = 'pending_state_request'
        self._service_behavior_request()
        self.bus.producer = 'route_gaze_setup'
        self._service_interested_gaze()
        self._finish_button_route()
        self.bus.producer = 'interested_roll'
        self._service_interested_roll()
        self.bus.producer = 'visual_servo'
        self._apply(self.latest_result, now)
        self.bus.producer = 'body_rhythm'
        self._service_body_rhythm()
        self.ensure_fake_led()
        self.bus.producer = 'state_outputs'
        service_state_outputs(self)
        return fresh


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _validate(events, clocks):
    if not clocks or len(clocks) > 20000 or any(not _finite(t) for t in clocks) or any(a >= b for a, b in zip(clocks, clocks[1:])):
        raise ValueError('Require 1..20000 strictly increasing finite nonnegative virtual times')
    if len(events) > 10000:
        raise ValueError('Too many replay events')
    for event in events:
        if not isinstance(event, dict) or not _finite(event.get('time_s')) or not clocks[0] <= event['time_s'] <= clocks[-1]:
            raise ValueError('Event must be within replay interval')
        kind = event.get('kind')
        if kind == 'state' and event.get('state') in ('normal', 'interested', 'sleepy', 'happy'):
            continue
        if kind in ('touch', 'button') and type(event.get('pressed')) is bool:
            continue
        if kind == 'stop':
            continue
        if kind == 'face' and event.get('status') in ('TRACKING', 'ACQUIRED', 'LOST', 'WAITING'):
            xy = event.get('error_xy', [0., 0.])
            if _finite(event.get('age_s', 0.)) and isinstance(xy, (list, tuple)) and len(xy) == 2 and all(type(x) in (int, float) and math.isfinite(x) and -1 <= x <= 1 for x in xy):
                continue
        raise ValueError('Invalid replay event')


def replay_motion(profile, events, clock_s):
    """Virtual clocks, memory-only feedback; physical readings remain None.

    Default face input is a synthetic continuous centered stream. Each explicit
    face event replaces it with one timestamped sample that ages until replaced.
    These are already-selected observations, not detector/identity association.
    No wrong-player/camera watchdog coverage is claimed.
    Requests between ticks are recognized at the next supplied virtual tick.
    """
    _validate(events, clock_s)
    profile = json.loads(json.dumps(profile, allow_nan=False))
    fingerprint = hashlib.sha256(json.dumps(profile, sort_keys=True).encode()).hexdigest()
    trace = MotionTrace(min(100000, len(clock_s) * 5))
    motor = ReplayMotor(profile, clock_s[0])
    queue = iter(sorted(events, key=lambda event: event['time_s']))
    pending = next(queue, None)
    face = dict(status='TRACKING', age_s=0., error_xy=[0., 0.])
    face_sequence = 0
    for tick_id, now in enumerate(clock_s):
        recognized = []
        while pending is not None and pending['time_s'] <= now:
            recognized.append(pending)
            if pending['kind'] == 'face':
                face_sequence += 1
                face = dict(status=pending['status'], error_xy=pending.get('error_xy', [0., 0.]),
                            captured_s=pending['time_s'] - pending.get('age_s', 0.),
                            source_id=f'face_event_{face_sequence}')
            pending = next(queue, None)
        fresh = motor.service(now, face, recognized)
        rhythm = motor.rhythm_driver.rhythm.status() if motor.rhythm_driver else {}
        route = getattr(motor.controller, 'pose_route', None)
        for sid in range(1, 6):
            writes = [w for w in motor.bus.writes if w['joint_id'] == sid]
            goals = [w for w in writes if w['address'] == 42]
            trace.record(dict(tick_id=tick_id, time_s=now, clock='virtual_seconds',
                producer=goals[-1]['producer'] if goals else 'no_position_write', joint_id=sid,
                profile_sha256=fingerprint, source_id=f'replay_tick_{tick_id}',
                behavior=motor.behavior_trial, controller_state=motor.controller.state,
                route_phase=getattr(route, 'phase', None), operator_stopped=motor.operator_stopped,
                controller_error=motor.controller.last_error, face_fresh=fresh,
                face_source_id=motor.latest_result['observation']['source_id'],
                face_captured_s=motor.latest_result['observation']['captured_s'],
                touch_sequence=motor.touch_sequence, button_sequence=motor.button_sequence,
                cpg_updates=rhythm.get('updates'), cpg_o1=rhythm.get('o1'), cpg_o2=rhythm.get('o2'),
                cpg_envelope=rhythm.get('envelope'), cpg_time_scale=rhythm.get('time_scale'),
                generated_float_tick=None, generated_float_missing_reason='legacy_producers_round_before_bus',
                sent_tick=goals[-1]['value'] if goals else None, sent_s=now if goals else None,
                readback_tick=motor.bus.reg[sid][42], readback_s=now, readback_kind='synthetic_memory',
                model_position_tick=motor.bus.pos[sid], model_sample_s=now,
                model_kind='ideal_previous_tick_goal', actual_tick=None, actual_s=None,
                measured_latency_s=None, missing_reason='hardware_not_connected',
                writes=writes, recognized_events=recognized))
    return trace.events


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', type=Path, default=ROOT / 'bio_inspire/hardware/normal_gaze_trial.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'bio_inspire/hardware/offline_motion_baseline')
    parser.add_argument('--plot', action='store_true', help='Export command plot with local matplotlib; no camera')
    args = parser.parse_args()
    profile = json.loads(args.profile.read_text(encoding='utf-8-sig'))
    events = [dict(time_s=8., kind='state', state='sleepy'),
              dict(time_s=16., kind='button', pressed=True), dict(time_s=17., kind='button', pressed=False),
              dict(time_s=27., kind='touch', pressed=True), dict(time_s=28., kind='touch', pressed=False),
              dict(time_s=38., kind='state', state='sleepy'), dict(time_s=46., kind='state', state='normal'),
              dict(time_s=54., kind='face', status='TRACKING', error_xy=[0., .5], age_s=1.),
              dict(time_s=57., kind='stop')]
    rows = replay_motion(profile, events, [i / 20 for i in range(1201)])
    args.output.mkdir(parents=True, exist_ok=True)
    trace = MotionTrace(len(rows))
    for row in rows:
        trace.record(row)
    trace.export(args.output / 'trace.json')
    columns = ['tick_id', 'time_s', 'joint_id', 'behavior', 'controller_state', 'route_phase',
               'producer', 'sent_tick', 'readback_tick', 'model_position_tick', 'actual_tick',
               'cpg_o1', 'cpg_o2', 'cpg_envelope', 'face_fresh', 'missing_reason']
    with (args.output / 'trace.csv').open('w', newline='', encoding='utf-8-sig') as output:
        writer = csv.DictWriter(output, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            writer.writerow({k: 'N/A' if row[k] is None else row[k] for k in columns})
    report = dict(evidence='OFFLINE_COMMANDS_NOT_HARDWARE', profile_sha256=rows[0]['profile_sha256'],
                  model='ideal previous-tick goal follower; no inertia/friction/PID/dynamics',
                  behaviors=sorted({r['behavior'] for r in rows}),
                  faults=sorted({r['controller_error'] for r in rows if r['controller_state'] == 'FAULT'}),
                  clocks='virtual_seconds; no wall/UART timing measurement', events=events,
                  limits=['Not full FSM/AHM', 'No face detector or identity association',
                          'No physical safety certification', 'Float targets unavailable at legacy bus boundary'], joints={})
    report['multiple_position_producers_same_tick'] = [
        dict(tick_id=row['tick_id'], time_s=row['time_s'], joint_id=row['joint_id'],
             position_writes=[w for w in row['writes'] if w['address'] == 42])
        for row in rows if len({w['producer'] for w in row['writes'] if w['address'] == 42}) > 1]
    for sid in range(1, 6):
        goals = [r['readback_tick'] for r in rows if r['joint_id'] == sid]
        report['joints'][sid] = dict(min_command_tick=min(goals), max_command_tick=max(goals),
                                     max_adjacent_command_step_ticks=max(abs(a-b) for a,b in zip(goals, goals[1:])),
                                     actual_motion='N/A')
    (args.output / 'summary.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    if args.plot:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        figure, axes = plt.subplots(6, 1, figsize=(13, 11), sharex=True)
        figure.suptitle('OFFLINE COMMAND REPLAY — NOT MEASURED MOTOR MOTION')
        for sid in range(1, 6):
            joint = [r for r in rows if r['joint_id'] == sid]
            axes[sid-1].plot([r['time_s'] for r in joint], [r['readback_tick'] for r in joint], linewidth=1.)
            axes[sid-1].set_ylabel(f'ID{sid}\nraw ticks')
            axes[sid-1].grid(alpha=.25)
        joint = [r for r in rows if r['joint_id'] == 1]
        axes[5].plot([r['time_s'] for r in joint], [r['cpg_o1'] for r in joint], label='SO(2) o1')
        axes[5].plot([r['time_s'] for r in joint], [r['cpg_envelope'] for r in joint], label='output envelope')
        axes[5].set_xlabel('Virtual time (s); ideal previous-tick follower, no actuator dynamics')
        axes[5].legend(loc='upper right')
        axes[5].grid(alpha=.25)
        for event in events:
            for axis in axes:
                axis.axvline(event['time_s'], color='gray', alpha=.25, linewidth=.7)
        figure.tight_layout(rect=(0, 0, 1, .97))
        figure.savefig(args.output / 'command_replay.png', dpi=130)
        plt.close(figure)
    print(json.dumps(dict(output=str(args.output), rows=len(rows), behaviors=report['behaviors'], faults=report['faults'])))


if __name__ == '__main__':
    main()
