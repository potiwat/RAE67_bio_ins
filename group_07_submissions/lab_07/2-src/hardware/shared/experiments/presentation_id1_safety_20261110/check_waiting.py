"""Read GUI process/log and capture desktop; never UART or motor writes."""
import base64,json,subprocess
from deploy import SSH,ROOT,REL
r=subprocess.run(SSH,input=r'''
from pathlib import Path
import subprocess,os,json,base64
d=Path('/home/menulis/projects/lelamp/camera_tracking/shared/experiments/presentation_id1_safety_20261110')
p=d/'waiting_desktop.png'
r=subprocess.run(['scrot','-o',str(p)],env={**os.environ,'DISPLAY':':0'},capture_output=True,text=True)
print(json.dumps(dict(log=(d/'viewer_latest.log').read_text()[-2500:],process=subprocess.run(['pgrep','-af','[p]resentation_id1_safety_20261110.launch'],capture_output=True,text=True).stdout,screenshot=None if r.returncode else base64.b64encode(p.read_bytes()).decode(),screenshot_error=r.stderr)))
''',text=True,capture_output=True,timeout=15)
if r.returncode:raise RuntimeError(r.stderr)
v=json.loads(r.stdout);s=v.pop('screenshot')
if s:(ROOT/REL/'waiting_desktop.png').write_bytes(base64.b64decode(s))
print(json.dumps(v,indent=2))
