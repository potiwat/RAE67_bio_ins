"""Separate camera launcher. No automatic motor start and no production writes."""
import sys,os,json,hashlib
from pathlib import Path

def main():
 root=Path(__file__).resolve().parents[3];os.chdir(root)
 manifest=json.loads(Path(__file__).with_name('manifest.json').read_text())
 for n,h in manifest['protected_sha256'].items():
  if hashlib.sha256((root/n).read_bytes()).hexdigest()!=h:raise RuntimeError('Accepted source changed; rebuild isolated safety version: '+n)
 for n,h in manifest['own_code_sha256'].items():
  if hashlib.sha256((root/n).read_bytes()).hexdigest()!=h:raise RuntimeError('Experimental file changed; rebuild and recheck: '+n)
 sys.path[:0]=[str(root),str(root/'shared/runtime'),str(root/'bio_inspire/runtime')]
 from .integration import install
 install(root,root/'shared/hardware/presentation_id1_safety_20261110')
 if '--check' in sys.argv:
  print('SAFETY_WRAPPER_CHECK_OK; no camera/UART opened');return
 preview=root/'shared/runtime/camera_preview.py';source=preview.read_text(encoding='utf-8-sig')
 needle="'Lamp Bio - Normal / face centering'"
 if source.count(needle)!=1:raise RuntimeError('Camera title anchor changed')
 source=source.replace(needle,"'EXPERIMENT - Presentation + ID1 SAFETY'")
 sys.argv=[str(preview),'--live','--simple-ui','--max-age-s','.5','--fps','30','--roll-compensation','--normal-profile',str(Path(__file__).with_name('profile.json')),'--diagnostic-snapshot']
 # __file__ remains the accepted source inode, preserving its exclusive viewer lock.
 exec(compile(source,str(preview),'exec'),dict(__name__='__main__',__file__=str(preview)))

if __name__=='__main__':main()

