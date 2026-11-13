import os,sys,json,hashlib
from pathlib import Path

def main():
 root=Path(__file__).resolve().parents[3];os.chdir(root);here=Path(__file__).parent
 manifest=json.loads((here/'manifest.json').read_text())
 for group in ('protected_sha256','own_code_sha256'):
  for n,h in manifest[group].items():
   if hashlib.sha256((root/n).read_bytes()).hexdigest()!=h:raise RuntimeError('Source changed; inspect baseline build: '+n)
 sys.path[:0]=[str(root),str(root/'shared/runtime'),str(root/'bio_inspire/runtime')]
 from .integration import install
 install(root,root/'shared/hardware/all_joint_baseline_20261110')
 if '--check' in sys.argv:print('BASELINE_CHECK_OK; no UART/camera opened');return
 preview=root/'shared/runtime/camera_preview.py';source=preview.read_text(encoding='utf-8-sig');title="'Lamp Bio - Normal / face centering'"
 if source.count(title)!=1:raise RuntimeError('Viewer title anchor changed')
 source=source.replace(title,"'BASELINE - ID1-5 ALL SIX STATES - RECORD ONLY'")
 sys.argv=[str(preview),'--live','--simple-ui','--max-age-s','.5','--fps','30','--roll-compensation','--normal-profile',str(here/'profile.json'),'--diagnostic-snapshot']
 exec(compile(source,str(preview),'exec'),dict(__name__='__main__',__file__=str(preview)))

if __name__=='__main__':main()
