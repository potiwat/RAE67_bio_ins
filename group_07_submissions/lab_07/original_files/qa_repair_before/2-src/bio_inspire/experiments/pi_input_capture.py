"""Finite Pi input-only capture. Never imports motor, serial, SPI or LED code."""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import sys
import time


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--seconds',type=float,default=30.)
    parser.add_argument('--stop-file',type=Path,help='stop cleanly when this new in-project marker is created')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[2]
    target=args.out.resolve()
    stop_file=None if args.stop_file is None else args.stop_file.resolve()
    if (not target.is_relative_to(root) or not 1<=args.seconds<=180
            or stop_file is not None and (not stop_file.is_relative_to(root) or stop_file.exists())):
        parser.error('new files inside project; duration1..180seconds')
    if target.exists():raise FileExistsError(target)
    sys.path.insert(0,str(root/'shared/runtime'))
    from physical_distance import PhysicalDistance
    from physical_button import PhysicalButton
    from physical_touch import PhysicalTouch
    clock=lambda:time.clock_gettime(time.CLOCK_BOOTTIME)
    target.parent.mkdir(parents=True,exist_ok=True)
    with ExitStack() as stack:
        button=PhysicalButton(.06);stack.callback(button.close)
        touch=PhysicalTouch(.06);stack.callback(touch.close)
        tof=PhysicalDistance(clock=clock);stack.callback(tof.close)
        # A completed quality-coded frame is sufficient, even if no target.
        tof.ready.wait(5.)
        button.discard_pending();touch.discard_pending()
        start=clock();count=0
        with target.open('x',encoding='utf-8') as stream:
            print('INPUT_CAPTURE_READY',str(target),'duration_s',args.seconds,flush=True)
            while clock()-start<args.seconds and not (stop_file is not None and stop_file.exists()):
                bd=button.diagnostics();bs=clock()
                td=touch.diagnostics();ts=clock()
                b=bd['stable_pressed'] is True;t=td['stable_pressed'] is True
                be=button.drain_events(bs);te=touch.drain_events(ts)
                sample=tof.latest() or {};now=clock()
                kind=sample.get('measurement_state','error')
                if sample.get('error'):kind='error'
                cm=sample.get('distance_cm')
                row=dict(time_s=now,button=b,touch=t,distance_kind=kind,
                         distance_m=None if cm is None else cm/100.,
                         button_sample_s=bs,touch_sample_s=ts,distance_sample_s=sample.get('received_s',now),
                         digital_predebounced=True,button_events=be,touch_events=te,
                         button_raw=bd['raw_pressed'],touch_raw=td['raw_pressed'],
                         source_id=f'pi_input_{int(start*1000)}_{count:05d}',tof_sequence=sample.get('sequence'),
                         tof_range_status=sample.get('range_status_raw'),error=sample.get('error'))
                stream.write(json.dumps(row,allow_nan=False)+'\n');count+=1
                deadline=start+count*.05
                time.sleep(max(0.,deadline-clock()))
        print('INPUT_CAPTURE_DONE',count,'snapshots; no actuator access',flush=True)


if __name__=='__main__':main()
