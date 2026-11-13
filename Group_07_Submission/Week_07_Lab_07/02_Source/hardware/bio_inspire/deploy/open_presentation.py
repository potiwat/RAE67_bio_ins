"""Open the accepted presentation viewer; motors wait for operator Start."""
import os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def main():
    os.chdir(ROOT)
    sys.path[:0]=[str(ROOT),str(ROOT/'bio_inspire/runtime'),str(ROOT/'shared/runtime')]
    from bio_inspire.runtime.presentation_accepted_20261110 import install
    install()
    profile=ROOT/'bio_inspire/hardware/presentation_20261107/play_C1_angry_body25_trial.json'
    preview=ROOT/'shared/runtime/camera_preview.py'
    sys.argv=[str(preview),
        '--live','--simple-ui','--max-age-s','.5','--fps','30','--roll-compensation',
        '--normal-profile',str(profile),'--diagnostic-snapshot']
    print('PRESENTATION_ACCEPTED: Happy H reference2.8to2.5 / LED active CPG / motor profile unchanged',flush=True)
    exec(compile(preview.read_text(encoding='utf-8-sig'),str(preview),'exec'),dict(__name__='__main__',__file__=str(preview)))

if __name__=='__main__':main()
