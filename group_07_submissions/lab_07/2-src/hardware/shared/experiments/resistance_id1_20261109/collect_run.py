"""Collect all new attempts without replacing raw bytes or selecting the best run."""
from pathlib import Path
import argparse,json,subprocess,hashlib
root=Path(__file__).resolve().parents[3]
parser=argparse.ArgumentParser();parser.add_argument('trial',choices=('R1','R2'));args=parser.parse_args()
trial=args.trial;out=root/'shared/hardware/resistance_id1_20261109'/f'{trial}_CAPTURE'
ssh=['wsl','-d','Ubuntu-24.04','--','ssh','-S','/tmp/lelamp-codex-20261106.sock','-o','BatchMode=yes','-o','ConnectTimeout=7','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=/mnt/c/Users/USER/.ssh/known_hosts','menulis@172.20.10.2']
remote=r'''
from pathlib import Path
import json,hashlib,subprocess
trial=TRIAL;root=Path('/home/menulis/projects/lelamp/camera_tracking');data=root/'shared/hardware/resistance_id1_20261109'
pattern='[c]amera_preview.py|[o]pen_play.py|[o]pen_presentation.py|[r]esistance_id1_20261109/(observer|pilot).py'
assert not subprocess.getoutput('pgrep -af "'+pattern+'"').strip(),'Viewer still open: user Q closes and saves'
ready=json.loads((data/(trial+'_READY.json')).read_text())
pair={'R1':'resistance_id1_R1_baseline','R2':'resistance_id1_R2_pilot'}[trial]
paths={};runs=[]
for p in sorted((root/'bio_inspire/results/lab07_sessions').glob('*/metadata.json')):
 if p.parent.name in ready['previous_runs']:continue
 m=json.loads(p.read_text())
 if m.get('pair_id')!=pair:continue
 run=p.parent.name;runs.append(run)
 for n in ('trace.jsonl','metadata.json','summary.json'):paths[run+'/'+n]=p.parent/n
 if m.get('measurement_sidecar'):paths[run+'/measurement.json']=Path(m['measurement_sidecar'])
assert runs,'No new experiment run; preserve the viewer log and inspect startup'
for name in (trial+'_EVENTS.json',trial+'_SAMPLES.jsonl',trial+'_VIEWER.log',trial+'_READY.json'):
 paths[name]=data/name
if ready.get('variant') in ('capped_early_pause_no_retry','capped_qualified_retry_R5'):
 audit=data/'R4_CAP_AUDIT.json';assert audit.exists(),'Missing cap restoration audit';paths['R4_CAP_AUDIT.json']=audit
stop=root/'bio_inspire/hardware/resistance_id1_20261109/last_gaze_stop.json'
if stop.exists():paths['last_gaze_stop.json']=stop
print(json.dumps(dict(trial=trial,pair_id=pair,ready_pid=ready['pid'],runs=runs,files=[dict(name=n,path=str(p),size=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for n,p in paths.items()])))
'''.replace('TRIAL',repr(trial))
p=subprocess.run(ssh+['/home/menulis/lamp-test-venv/bin/python','-B','-'],input=remote,text=True,capture_output=True,timeout=25)
if p.returncode:raise RuntimeError(p.stderr)
manifest=json.loads(p.stdout);out=out.with_name(out.name+'_'+str(manifest['ready_pid']));out.mkdir(parents=True,exist_ok=True)
for item in manifest['files']:
 p=subprocess.run(ssh+['cat',item['path']],capture_output=True,timeout=60)
 assert p.returncode==0,p.stderr
 b=p.stdout;assert len(b)==item['size'] and hashlib.sha256(b).hexdigest()==item['sha256']
 target=out/item['name'];target.parent.mkdir(parents=True,exist_ok=True)
 if target.exists():assert target.read_bytes()==b,'Existing raw differs; create a separate capture revision'
 else:target.write_bytes(b)
(out/'RETRIEVAL.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
audits=[]
for run in manifest['runs']:
 folder=out/run;s=json.loads((folder/'summary.json').read_text());b=(folder/'trace.jsonl').read_bytes();lines=b.splitlines()
 assert hashlib.sha256(b).hexdigest()==s['trace_sha256'] and len(lines)==s['written']
 audits.append(dict(run_id=run,written=s['written'],accepted=s['accepted'],dropped=s['dropped'],writer_error=s['error'],source_sha256=s['trace_sha256']))
attempts=json.loads((out/(trial+'_EVENTS.json')).read_text())['attempts']
report=dict(trial=trial,raw_runs=audits,observer_or_pilot_attempts=attempts,
    needs_attempt_alignment=len(attempts)!=len(audits),all_attempts_preserved=True,hardware_force_validated=False)
(out/'CAPTURE_AUDIT.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(dict(trial=trial,runs=len(audits),files=len(manifest['files']),output=str(out),all_hashes_verified=True),indent=2))
