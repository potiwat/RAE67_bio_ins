"""Read-only checks and summary of ROS traces; never infer physical latency."""
import csv
from collections import Counter
import hashlib
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TOPICS = ['/lamp/input/button', '/lamp/input/touch', '/lamp/input/distance',
          '/lamp/interaction', '/lamp/emotion', '/lamp/servo_command', '/lamp/rgb_command']


def read_rows(path):
    with path.open(newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def main():
    source = ROOT / 'src/lamp_week07/lamp_week07/ros_nodes.py'
    original = ROOT.parent / 'lamp_week07/ros_nodes.py'
    expected = original.read_text().replace("('servo_command',servo,servo.data)",
                                            "('servo_command',servo,list(servo.data))")
    assert source.read_text() == expected, 'Unexpected source changes'
    assert (ROOT/'completed_policy.py').read_bytes() == (ROOT.parent/'completed_policy.py').read_bytes()
    results = []
    for repeat, seed in enumerate((41, 42, 43), 1):
        folder = ROOT/'logs'/f'course_ros_20261027_loggingfix_attempt2_r{repeat:02}'
        meta = json.loads((folder/'run_metadata.json').read_text())
        assert meta['status'] == 'completed' and meta['seed'] == seed
        assert not any(p['forced'] for p in meta['shutdowns'].values())
        inputs = read_rows(folder/'inputs.csv')
        interaction = read_rows(folder/'interaction.csv')
        collector = read_rows(folder/'collector.csv')
        assert len(inputs) == 3303
        assert all(row['source_latency_s'] == '' for row in inputs + interaction + collector)
        assert {r['topic'] for r in inputs + collector} == set(TOPICS)
        received = Counter(r['topic'] for r in interaction if r['phase'] == 'receive')
        published = Counter(r['topic'] for r in interaction if r['phase'] == 'publish')
        collected = Counter(r['topic'] for r in collector)
        states = {json.loads(r['payload'])['data'] for r in collector if r['topic'] == '/lamp/emotion'}
        for row in collector:
            value = json.loads(row['payload'])['data']
            if row['topic'] == '/lamp/servo_command':
                assert len(value) == 3 and all(math.isfinite(v) and abs(v) <= b+1e-6 for v,b in zip(value,(.35,.25,.30)))
            if row['topic'] == '/lamp/rgb_command':
                assert len(value) == 4 and all(0 <= v <= 1 for v in value) and value[3] == 1
        graph = json.loads((folder/'graph_seven_topics.json').read_text())
        assert set(graph) == set(TOPICS)
        for topic in TOPICS:
            publishers = [e for e in graph[topic]['publishers'] if e['node'] in ('week07_inputs','week07_interaction')]
            assert len(publishers) == 1
            assert (publishers[0]['reliability'],publishers[0]['durability']) == ('RELIABLE','VOLATILE')
        assert meta['course_declared_qos'] == {'reliability':'RELIABLE','history':'KEEP_LAST','depth':10,'durability':'VOLATILE'}
        stale = json.loads((folder/'receipt_stale_observation.json').read_text())
        assert json.loads(stale['collector_row']['payload'])['data'] == 'normal'
        baginfo = (folder/'bag_info.txt').read_text()
        assert all(topic in baginfo for topic in TOPICS)
        bag_counts = {name:int(count) for name,count in re.findall(r'Topic: (/lamp/\S+) \| Type: \S+ \| Count: (\d+)',baginfo)}
        results.append({'repeat':repeat,'seed':seed,'input_publish_counts':dict(Counter(r['topic'] for r in inputs)),
                        'interaction_input_receipts':dict(received),'interaction_output_publications':dict(published),
                        'collector_output_receipts':dict(collected),'observed_emotions':sorted(states),
                        'bag_topic_counts':bag_counts,
                        'bag_input_count_difference_from_source_log':{t:1101-bag_counts[t] for t in TOPICS[:3]},
                        'count_difference_scope':'Count difference only; not proof of network drop or identity-matched source latency.',
                        'all_five_emotions_observed':states == {'normal','interested','happy','afraid','sleepy'},
                        'seven_topics_and_declared_course_QoS_verified':True,
                        'graph_history_depth':'unavailable when UNKNOWN/0; preserved raw, not inferred',
                        'receipt_stale_normal_observed':True,
                        'source_latency_s':None,'physical_latency_s':None,
                        'log_directory':folder.relative_to(ROOT).as_posix()})
    files = [p for repeat in range(1,4) for p in (ROOT/'logs'/f'course_ros_20261027_loggingfix_attempt2_r{repeat:02}').rglob('*') if p.is_file()]
    files += [p for repeat in range(1,4) for p in (ROOT/'bags'/f'course_ros_20261027_loggingfix_attempt2_r{repeat:02}').rglob('*') if p.is_file()]
    report = {'status':'PASS','scope':'ROS2 middleware with lecturer synthetic inputs; no C1 network injection or hardware test',
              'authorized_fix':'Only convert servo.data to list in logging payload',
              'runs':results,'sha256':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
    (ROOT/'ROS_VERIFICATION.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='sha256'},indent=2))


if __name__ == '__main__':
    main()
