"""Independent checks on recorded evidence, derived views and replay; stdlib."""
import csv
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUN = ROOT / 'results/group07_offline_20261026'
REPLAY = ROOT / 'results/group07_replay_seed42_20261026'
EXPECTED = {'button_01', 'touch_01', 'approach_01', 'clear_01', 'near_01', 'clear_02', 'button_02'}
TOPICS = {'/lamp/input/button', '/lamp/input/touch', '/lamp/input/distance',
          '/lamp/interaction', '/lamp/emotion', '/lamp/servo_command', '/lamp/rgb_command'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def csv_rows(path):
    with path.open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def verify_manifest(folder):
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    for name, expected in manifest['sha256'].items():
        assert sha(folder / name) == expected, f'Hash mismatch: {folder}/{name}'
    return len(manifest['sha256'])


def main():
    checks = {'original_manifest_files': verify_manifest(RUN),
              'replay_manifest_files': verify_manifest(REPLAY),
              'derived_manifest_files': verify_manifest(ROOT / 'review_csv')}
    summary = json.loads((RUN / 'summary.json').read_text(encoding='utf-8'))
    assert len(summary) == 6
    details, paired_sources = [], {}
    for m in summary:
        name = f"{m['condition']}_r{m['repeat']:02}"
        folder = RUN / name
        inputs = csv_rows(folder / 'input_trace.csv')
        commands = csv_rows(folder / 'command_trace.csv')
        combined = csv_rows(ROOT / 'review_csv' / (name + '_trace_7topics.csv'))
        assert len(inputs) == 3303 and len(commands) == len(combined) == 1101
        assert m['published'] == m['received'] + m['transport_dropped'] + m['censored_after_trial']
        assert m['received'] == m['accepted'] + m['discarded_out_of_order']
        assert sum(bool(c['fault_channels']) for c in commands) == m['fault_ticks']
        source = [(r['sequence'], r['channel'], r['value'], r['sample_time_s'], r['source_time_s'], r['input_id']) for r in inputs]
        if m['condition'] == 'C0':
            paired_sources[m['seed']] = source
            assert {c['emotion'] for c in commands} == {'normal', 'interested', 'happy', 'afraid', 'sleepy'}
        else:
            assert paired_sources[m['seed']] == source
        assert len(m['source_outcomes']) == 10
        primary = [s for s in m['source_outcomes'] if s['primary_expected_both']]
        assert {s['input_id'] for s in primary} == EXPECTED
        assert sum(s['pass_1s_both'] is True for s in primary) == m['primary_pass_1s_both_count']
        for s in m['source_outcomes']:
            motion, rgb = s['first_motion_s'], s['first_rgb_s']
            if motion is None or rgb is None:
                assert s['both_latency_s'] is None and s['pass_1s_both'] is None
            else:
                assert abs(max(motion, rgb) - s['source_time_s'] - s['both_latency_s']) < 1e-8
        previous = [0., 0., 0.]
        accepted = {(r['channel'], r['sequence']): r for r in inputs if r['status'] == 'accepted'}
        for k, (command, row) in enumerate(zip(commands, combined)):
            assert TOPICS <= row.keys()
            t = float(command['time_s'])
            assert abs(t - k * .02) < 1e-8 and float(row['time_s']) == t
            assert row['/lamp/emotion'] == command['emotion'] and row['/lamp/interaction'] == command['interaction']
            pose = [float(command[key]) for key in ('tilt_rad', 'extend_rad', 'nod_rad')]
            color = [float(command[key]) for key in ('rgb_r', 'rgb_g', 'rgb_b', 'rgb_a')]
            assert json.loads(row['/lamp/servo_command']) == pose
            assert json.loads(row['/lamp/rgb_command']) == color
            assert all(math.isfinite(x) and abs(x) <= bound + 1e-8 for x, bound in zip(pose, (.35, .25, .30)))
            assert all(abs(a - b) <= .016 + 1e-8 for a, b in zip(pose, previous))
            assert all(0 <= x <= 1 for x in color) and color[3] == 1.
            previous = pose
            assert not row['physical_motion_onset_s'] and not row['physical_rgb_onset_s']
            for channel in ('button', 'touch', 'distance'):
                seq = row[channel + '_sequence']
                if seq:
                    receipt = accepted[channel, seq]
                    assert float(receipt['receipt_time_s']) <= t + 1e-9
                    assert row['/lamp/input/' + channel] == receipt['value']
                    # A newer accepted sequence must not already be available.
                    assert not any(c == channel and int(s) > int(seq) and float(v['receipt_time_s']) <= t + 1e-9
                                   for (c, s), v in accepted.items())
        details.append({'trial': name, 'seed': m['seed'], 'ticks': len(commands),
                        'missing_expected': [s['input_id'] for s in primary if s['both_latency_s'] is None]})
    replay_hashes = {}
    for filename in ('input_trace.csv', 'command_trace.csv', 'events.csv'):
        original, replay = RUN / 'C1_r02' / filename, REPLAY / 'C1_r01' / filename
        assert original.read_bytes() == replay.read_bytes(), f'Replay differs: {filename}'
        replay_hashes[filename] = sha(original)
    checks.update({'status': 'PASS', 'trials': details, 'replay_seed': 42,
                   'byte_identical_replay_sha256': replay_hashes,
                   'policy_sha256': sha(ROOT / 'completed_policy.py'),
                   'scope': 'Evidence integrity/model bounds/derived CSV only. ROS and hardware untested.'})
    (ROOT / 'verification.json').write_text(json.dumps(checks, indent=2), encoding='utf-8')
    print(json.dumps(checks, indent=2))


if __name__ == '__main__':
    main()
