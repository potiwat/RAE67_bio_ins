"""Desktop camera viewer only; boot does not move the lamp; never presses Start Auto."""
import os,sys
from pathlib import Path
root=Path(__file__).resolve().parents[2]
def main():
    os.chdir(root)
    os.execv(sys.executable,[sys.executable,'-B',str(root/'shared/runtime/camera_preview.py'),'--live','--simple-ui','--max-age-s','.5','--fps','30','--roll-compensation','--normal-profile',str(root/'bio_inspire/hardware/boot_ready_c1.json'),'--diagnostic-snapshot'])
if __name__=='__main__':main()
