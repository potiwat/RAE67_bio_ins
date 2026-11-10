"""Read-only SHA256 and evidence-contract checks; never touches hardware."""
from pathlib import Path
import hashlib,json,sys
root=Path(__file__).resolve().parent
manifest=json.loads((root/'manifest_sha256.json').read_text(encoding='utf8'));errors=[]
for name,expected in manifest.items():
    p=root/name
    if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=expected:errors.append('hash: '+name)
contract=json.loads((root/'2-src/ros2_package/config/topic_contract_13.json').read_text(encoding='utf8'))
if len(contract['topics'])!=13:errors.append('topic contract !=13')
raw=root/'3-results/real_robot_pilot'
for condition,suffix in [('C0','db0023c1'),('C1','86706a5d')]:
    verification=json.loads((raw/f'{condition}_bag_{suffix}/verification.json').read_text(encoding='utf-8'))
    if not verification['all_13_observed'] or verification['missing_topics']:errors.append(condition+' ROS13 missing')
    matches=list((raw/(condition+'_raw')).glob('*/summary.json'))
    if len(matches)!=1:errors.append(condition+' ambiguous raw session');continue
    summary=json.loads(matches[0].read_text(encoding='utf-8'))
    if hashlib.sha256(matches[0].with_name('trace.jsonl').read_bytes()).hexdigest()!=summary['trace_sha256']:errors.append(condition+' raw trace hash')
    if summary['complete'] or verification['status']!='INCOMPLETE':errors.append(condition+' partial pilot mislabeled')
source_hashes=json.loads((raw/'source_snapshot_hashes.json').read_text(encoding='utf-8'))
for name,expected in source_hashes.items():
    if hashlib.sha256((raw/'source_snapshot'/name).read_bytes()).hexdigest()!=expected:errors.append('pilot source mismatch '+name)
print(json.dumps(dict(package_integrity='PASS' if not errors else 'FAIL',files_checked=len(manifest),pilot_source_files_checked=len(source_hashes),
                     final_research_complete=False,errors=errors),indent=2))
raise SystemExit(bool(errors))
