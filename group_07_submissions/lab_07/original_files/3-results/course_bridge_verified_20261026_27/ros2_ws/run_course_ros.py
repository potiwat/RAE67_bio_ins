"""Run the lecturer's three unchanged executables and rosbag as separate processes.

This is process orchestration only. No controller, QoS, timing or stimulus
parameters are overridden. All files stay under this ROS workspace.
"""
import csv
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

import rclpy
from lamp_week07.ros_nodes import QOS

ROOT = Path(__file__).resolve().parent
CONTRACT = json.loads((ROOT / 'src/lamp_week07/interface_contract.json').read_text())
TOPICS = [t['name'] for t in CONTRACT['topics']]


def read_rows(path):
    if not path.exists():
        return []
    with path.open(newline='') as f:
        return list(csv.DictReader(f))


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def graph(node):
    result = {}
    for topic in TOPICS:
        result[topic] = {}
        for kind, getter in [('publishers', node.get_publishers_info_by_topic),
                             ('subscriptions', node.get_subscriptions_info_by_topic)]:
            result[topic][kind] = [
                {'node': e.node_name, 'type': e.topic_type,
                 'reliability': e.qos_profile.reliability.name,
                 'history': e.qos_profile.history.name,
                 'depth': e.qos_profile.depth,
                 'durability': e.qos_profile.durability.name}
                for e in getter(topic)]
    return result


def main():
    os.chdir(ROOT)
    declared_qos = {'reliability': QOS.reliability.name, 'history': QOS.history.name,
                    'depth': QOS.depth, 'durability': QOS.durability.name}
    if tuple(declared_qos.values()) != ('RELIABLE', 'KEEP_LAST', 10, 'VOLATILE'):
        raise RuntimeError('Course declared QoS differs from contract')
    rclpy.init()
    observer = rclpy.create_node('lamp_lab07_run_observer')
    if any(t.startswith('/lamp/') for t, _ in observer.get_topic_names_and_types()):
        raise RuntimeError('Existing /lamp topics detected; do not mix runs')
    try:
        for repeat, seed in enumerate((41, 42, 43), 1):
            folder = ROOT / 'logs' / f'course_ros_20261027_loggingfix_attempt2_r{repeat:02}'
            folder.mkdir(parents=True, exist_ok=False)
            bag = ROOT / 'bags' / folder.name
            if bag.exists():
                raise FileExistsError(bag)
            bag.parent.mkdir(exist_ok=True)
            origin = time.perf_counter_ns()
            children, handles, starts, shutdowns = {}, {}, {}, {}
            status = 'failed'

            def launch(name, args):
                handle = (folder / (name + '.stdout.log')).open('x')
                handles[name] = handle
                children[name] = subprocess.Popen(args, cwd=ROOT, stdout=handle,
                                                   stderr=subprocess.STDOUT,
                                                   start_new_session=True)
                starts[name] = {'pid': children[name].pid, 'argv': args,
                                'launch_request_offset_s': (time.perf_counter_ns() - origin) / 1e9}

            def step():
                rclpy.spin_once(observer, timeout_sec=.02)
                for name, child in children.items():
                    if child.poll() is not None and name not in shutdowns:
                        raise RuntimeError(f'{name} exited unexpectedly: {child.returncode}')

            def stop(name):
                child = children[name]
                shutdowns[name] = {'signal': 'SIGINT', 'forced': False}
                if child.poll() is None:
                    os.killpg(child.pid, signal.SIGINT)
                    try:
                        child.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        shutdowns[name]['forced'] = True
                        os.killpg(child.pid, signal.SIGTERM)
                        child.wait(timeout=10)
                shutdowns[name]['returncode'] = child.returncode

            try:
                launch('recorder', ['ros2', 'bag', 'record', '-o', str(bag), *TOPICS])
                launch('collector', ['ros2', 'run', 'lamp_week07', 'output_collector',
                                     '--ros-args', '-p', f'trace_file:={folder / "collector.csv"}'])
                launch('interaction', ['ros2', 'run', 'lamp_week07', 'interaction', '--ros-args',
                                       '-p', f'policy_file:={ROOT / "completed_policy.py"}',
                                       '-p', f'trace_file:={folder / "interaction.csv"}'])
                # Administrative startup timeout, not a model/experiment value.
                deadline = time.monotonic() + 30
                while True:
                    step()
                    observed = graph(observer)
                    outputs = TOPICS[3:]
                    ready = all(any(e['node'] == 'week07_interaction' for e in observed[t]['publishers'])
                                and any(e['node'] == 'week07_output_collector' for e in observed[t]['subscriptions'])
                                and any('recorder' in e['node'] for e in observed[t]['subscriptions']) for t in outputs)
                    if ready:
                        break
                    if time.monotonic() > deadline:
                        raise RuntimeError('Collector/interaction/recorder graph not ready within administrative timeout')
                dump(folder / 'graph_before_inputs.json', observed)
                launch('inputs', ['ros2', 'run', 'lamp_week07', 'synthetic_inputs', '--ros-args',
                                  '-p', f'seed:={seed}', '-p', f'trace_file:={folder / "inputs.csv"}'])
                deadline = time.monotonic() + 120
                while True:
                    step()
                    log = (folder / 'inputs.stdout.log').read_text(errors='replace')
                    if '22s source protocol complete' in log:
                        break
                    if time.monotonic() > deadline:
                        raise RuntimeError('Official source protocol did not complete within administrative timeout')
                observed = graph(observer)
                dump(folder / 'graph_seven_topics.json', observed)
                for topic in CONTRACT['topics']:
                    matching = [e for e in observed[topic['name']]['publishers'] if e['node'] in ('week07_inputs', 'week07_interaction')]
                    if len(matching) != 1 or matching[0]['type'] != topic['type']:
                        raise RuntimeError('Missing/incorrect publisher: ' + topic['name'])
                    e = matching[0]
                    if (e['reliability'], e['durability']) != ('RELIABLE', 'VOLATILE'):
                        raise RuntimeError('Unexpected course QoS: ' + topic['name'])
                    if e['history'] not in ('KEEP_LAST', 'UNKNOWN') or e['depth'] not in (10, 0):
                        raise RuntimeError('Unexpected discoverable history/depth: ' + topic['name'])
                # Source timer has finished; stop only the child we opened.
                stop('inputs')
                # Observe the documented receipt-stale fallback, without changing stale_s.
                deadline = time.monotonic() + 30
                while True:
                    step()
                    rows = read_rows(folder / 'interaction.csv')
                    emotion_rows = [r for r in rows if r.get('phase') == 'publish' and r.get('topic') == '/lamp/emotion']
                    if emotion_rows:
                        payload = json.loads(emotion_rows[-1]['payload'])
                        if payload['data'] == 'normal' and set(payload['fault_channels'].split(',')) == {'button', 'touch', 'distance'}:
                            collector = read_rows(folder / 'collector.csv')
                            collected = [r for r in collector if r.get('topic') == '/lamp/emotion']
                            if collected and json.loads(collected[-1]['payload'])['data'] == 'normal':
                                dump(folder / 'receipt_stale_observation.json', {
                                    'interaction_row': emotion_rows[-1], 'collector_row': collected[-1],
                                    'interpretation': 'Receipt-stale fallback observed after official source ended. Not sensor acquisition freshness.'})
                                break
                    if time.monotonic() > deadline:
                        raise RuntimeError('No observed receipt-stale neutral fallback')
                stop('interaction')
                stop('collector')
                stop('recorder')
                info = subprocess.run(['ros2', 'bag', 'info', str(bag)], capture_output=True, text=True)
                (folder / 'bag_info.txt').write_text(info.stdout + info.stderr)
                if info.returncode:
                    raise RuntimeError('rosbag info failed')
                status = 'completed'
            finally:
                for name in reversed(list(children)):
                    if name not in shutdowns:
                        stop(name)
                for handle in handles.values():
                    handle.close()
                dump(folder / 'run_metadata.json', {
                    'status': status, 'seed': seed, 'repeat': repeat, 'source_protocol_s': 22,
                    'policy_sha256': hashlib.sha256((ROOT / 'completed_policy.py').read_bytes()).hexdigest(),
                    'startup_offsets_scope': 'Popen request times only; not node clock origins. Do not infer source latency.',
                    'processes': starts, 'shutdowns': shutdowns,
                    'source_latency_s': None, 'physical_latency_s': None,
                    'ROS_DISTRO': os.environ.get('ROS_DISTRO'), 'ROS_DOMAIN_ID_override': None,
                    'course_declared_qos': declared_qos,
                    'graph_qos_limit': 'UNKNOWN history/depth=0 is unavailable introspection, not a replacement for KEEP_LAST/10. Retain raw graph.',
                    'scope': 'Real ROS2 middleware with synthetic inputs. No physical devices; no artificial C1 transport injection.'})
            print(f'Completed ROS2 trial {repeat}/3, seed={seed}: {folder}', flush=True)
    finally:
        observer.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
