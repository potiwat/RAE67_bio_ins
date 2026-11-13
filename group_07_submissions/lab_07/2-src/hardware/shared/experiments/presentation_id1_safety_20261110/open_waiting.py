"""Read-only preflight then show isolated GUI waiting for operator Start."""
import json,subprocess,sys
from pathlib import Path
from deploy import SSH,ROOT,REL
REMOTE=r'''
from pathlib import Path
import os,sys,json,subprocess,time,hashlib
root=Path('/home/menulis/projects/lelamp/camera_tracking');os.chdir(root)
dest=root/'shared/experiments/presentation_id1_safety_20261110'
assert not subprocess.run(['pgrep','-af','[c]amera_preview.py|[o]pen_presentation.py|[f]oam_trial|[p]resentation_id1_safety_20261110.launch'],capture_output=True,text=True).stdout.strip(),'Another motor owner/viewer is running'
sys.path[:0]=[str(root),str(root/'bio_inspire/runtime'),str(root/'shared/runtime')]
from normal_gaze_motor import open_bus,decode_state
b=open_bus()
try:
 rows=[decode_state(i,b.read(i,33,38)) for i in range(1,6)]
 pids={str(i):list(b.read(i,21,3)) for i in range(1,6)}
 expected={'1':[8,16,0],'2':[32,20,0],'3':[24,26,0],'4':[5,0,0],'5':[7,3,0]}
 assert pids==expected,'PID mismatch; no automatic correction: '+repr(pids)
 assert all(r['mode']==0 and r['torque_raw']==1 and not r['status_raw'] and not r['speed_raw'] and not r['moving_raw'] for r in rows),'Inspect stationary healthy hold: '+repr(rows)
 block=b.read(1,33,38)
 assert int.from_bytes(block[15:17],'little')==1000,'Original cap1000 not restored'
 assert block[8]==3 and int.from_bytes(block[13:15],'little')==600,'Original600/3 not restored'
 assert b.read(1,18,1)==b'\x0c' and b.read(1,55,1)==b'\x01','Unexpected phase/lock'
finally:b.close()
env={**os.environ,'PYTHONPATH':str(root)+':'+str(root/'bio_inspire/runtime')+':'+str(root/'shared/runtime'),'PYTHONDONTWRITEBYTECODE':'1','DISPLAY':':0','XDG_RUNTIME_DIR':'/run/user/'+str(os.getuid()),'DBUS_SESSION_BUS_ADDRESS':'unix:path=/run/user/'+str(os.getuid())+'/bus'}
log=dest/'viewer_latest.log'
with log.open('a') as f:p=subprocess.Popen([sys.executable,'-B','-m','shared.experiments.presentation_id1_safety_20261110.launch'],cwd=root,env=env,stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
time.sleep(4)
assert p.poll() is None,log.read_text()[-4000:]
manifest=json.loads((dest/'manifest.json').read_text())
assert all(hashlib.sha256((root/n).read_bytes()).hexdigest()==h for n,h in manifest['protected_sha256'].items())
report=dict(status='GUI_WAITING_START_NO_MOTION_SENT',pid=p.pid,preflight=rows,pid_before=pids,viewer_log=str(log),protected_files_unchanged=len(manifest['protected_sha256']))
(dest/'OPENED.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
'''
if __name__=='__main__':
 r=subprocess.run(SSH,input=REMOTE,text=True,capture_output=True,timeout=35)
 if r.returncode:print(r.stdout);print(r.stderr);raise SystemExit(r.returncode)
 report=json.loads(r.stdout);(ROOT/REL/'OPENED_PI.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
