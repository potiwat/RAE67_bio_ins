"""User-accepted separate Present Safety launcher."""
import os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
FLAGS=['--experimental-contact','--auto-contact-recovery','--tof-mode2-trial','--isolate-tof','--id1-effort-trial','--id2-contact-recovery','--id2-effort-trial','--id4-effort-trial','--accepted-coordination','--contact-ids','1,2,4']
def existing_owners(proc_root=Path('/proc'),self_pid=None):
 self_pid=os.getpid() if self_pid is None else self_pid
 found=[]
 for p in proc_root.iterdir():
  if not p.name.isdigit()or int(p.name)==self_pid:continue
  try:
   # Desktop terminal/shell ancestors include our filename in their arguments.
   # Only another Python lamp process can own this Python runtime.
   if not (p/'comm').read_text().strip().startswith('python'):continue
   cmd=(p/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace')
  except(OSError,PermissionError):continue
  if any(s in cmd for s in ('camera_preview.py','open_presentation.py','presentation_safety_play_20261110.launch','present_safety_start.py','presentation_safety_play_20261110.free_path_auto','lab07_present_safety_pair1_20261112/instrument.py')):found.append((int(p.name),cmd))
 return found

def main():
 os.chdir(ROOT);sys.path[:0]=[str(ROOT),str(ROOT/'bio_inspire/runtime'),str(ROOT/'shared/runtime')]
 from shared.experiments.presentation_safety_play_20261110.launch import main as run
 check='--check'in sys.argv
 if not check:
  owners=existing_owners()
  if owners:raise RuntimeError('Close the existing lamp window with Q first: '+str(owners))
 sys.argv=[__file__,*FLAGS,*(['--check']if check else[])];run()
if __name__=='__main__':
 from contextlib import redirect_stdout,redirect_stderr
 import traceback,time
 with Path(__file__).with_name('PRESENT_SAFETY_STARTUP.log').open('a',buffering=1)as log:
  with redirect_stdout(log),redirect_stderr(log):
   print('PRESENT_SAFETY_LAUNCH',time.time(),os.getpid(),flush=True)
   try:main()
   except BaseException:
    traceback.print_exc();raise
