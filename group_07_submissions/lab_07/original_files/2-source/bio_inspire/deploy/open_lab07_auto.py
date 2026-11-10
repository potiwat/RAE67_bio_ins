"""Open one opt-in experiment viewer. User Start and five releases are required."""
import argparse
import os
import sys
from pathlib import Path

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--condition',choices=('C0','C1'),required=True)
    parser.add_argument('--pair',choices=('P1','P2','P3'),required=True)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[2]
    profile=root/f'bio_inspire/hardware/lab07_automatic_{args.pair}_{args.condition}.json'
    if not profile.is_file():raise FileNotFoundError(profile)
    os.chdir(root)
    os.execv(sys.executable,[sys.executable,'-B',str(root/'shared/runtime/camera_preview.py'),
        '--live','--simple-ui','--max-age-s','.5','--fps','30','--roll-compensation',
        '--normal-profile',str(profile),'--diagnostic-snapshot'])

if __name__=='__main__':main()
