"""Group07 derived CSV export; read recorded results, never change the model.

Inputs are reconstructed ONLY from accepted receipts at or before each tick.
Outputs are applied software commands, never physical measurements.
"""
import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TOPICS = ('/lamp/input/button', '/lamp/input/touch', '/lamp/input/distance',
          '/lamp/interaction', '/lamp/emotion', '/lamp/servo_command', '/lamp/rgb_command')


def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows):
    with path.open('x', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    run, out = (ROOT / args.run).resolve(), (ROOT / args.out).resolve()
    if not run.is_relative_to(ROOT) or not out.is_relative_to(ROOT):
        parser.error('All paths must stay inside Lab07')
    out.mkdir(parents=True, exist_ok=False)
    summary = json.loads((run / 'summary.json').read_text(encoding='utf-8'))
    inputs_used, summary_rows, source_rows = {}, [], []
    for metric in summary:
        name = f"{metric['condition']}_r{metric['repeat']:02}"
        folder = run / name
        for filename in ('input_trace.csv', 'command_trace.csv', 'events.csv', 'metrics.json'):
            inputs_used[f'{name}/{filename}'] = sha(folder / filename)
        deliveries = sorted((row for row in read_csv(folder / 'input_trace.csv')
                             if row['status'] == 'accepted'),
                            key=lambda r: (float(r['receipt_time_s']), int(r['sequence']), r['channel']))
        events = defaultdict(list)
        for event in read_csv(folder / 'events.csv'):
            events[round(float(event['decision_time_s']), 8)].append(event)
        latest = {c: None for c in ('button', 'touch', 'distance')}
        index, rows, previous_state = 0, [], 'normal'
        for command in read_csv(folder / 'command_trace.csv'):
            t = float(command['time_s'])
            while index < len(deliveries) and float(deliveries[index]['receipt_time_s']) <= t + 1e-9:
                received = deliveries[index]
                latest[received['channel']] = received
                index += 1
            row = {'condition': metric['condition'], 'repeat': metric['repeat'], 'seed': metric['seed'],
                   'time_s': t, 'scope': 'simulation_applied_command_not_physical', 'state_before': previous_state}
            for channel in latest:
                received = latest[channel]
                # Blank = no sample received yet; NaN = recorded invalid sample.
                # Neither is silently converted to a false/zero valid sample.
                row['/lamp/input/' + channel] = '' if received is None else received['value']
            row.update({'/lamp/interaction': command['interaction'], '/lamp/emotion': command['emotion'],
                        '/lamp/servo_command': json.dumps([float(command[k]) for k in ('tilt_rad', 'extend_rad', 'nod_rad')]),
                        '/lamp/rgb_command': json.dumps([float(command[k]) for k in ('rgb_r', 'rgb_g', 'rgb_b', 'rgb_a')]),
                        'fault_channels': command['fault_channels'],
                        'decision_events_json': json.dumps(events.get(round(t, 8), []), ensure_ascii=False),
                        'physical_motion_onset_s': '', 'physical_rgb_onset_s': ''})
            for channel, received in latest.items():
                for field in ('sequence', 'sample_time_s', 'source_time_s', 'receipt_time_s', 'input_id'):
                    row[channel + '_' + field] = '' if received is None else received[field]
            rows.append(row)
            previous_state = command['emotion']
        write_csv(out / (name + '_trace_7topics.csv'), rows)
        summary_rows.append({k: v for k, v in metric.items() if k != 'source_outcomes'})
        for source in metric['source_outcomes']:
            source_rows.append({'condition': metric['condition'], 'repeat': metric['repeat'],
                                'seed': metric['seed'], **source})
    write_csv(out / 'metrics_summary.csv', summary_rows)
    write_csv(out / 'source_outcomes_all.csv', source_rows)
    manifest = {'source_run': str(run.relative_to(ROOT)), 'source_sha256': inputs_used,
                'scope': 'Derived views only; originals remain authoritative. No hardware measured.',
                'sha256': {p.name: sha(p) for p in sorted(out.iterdir()) if p.is_file()}}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(f'Exported {len(summary)} seven-topic traces, summary and all source outcomes to {out}')


if __name__ == '__main__':
    main()
