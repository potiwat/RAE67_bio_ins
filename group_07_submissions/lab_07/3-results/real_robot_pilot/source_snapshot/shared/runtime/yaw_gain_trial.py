"""Explicit supervised ID1-only volatile P trial; no goals or torque writes.

LeLamp reference: ee23699075fc3d3154da86a71c38a024545b6785,
lelamp/follower/lelamp_follower.py configure(): P16, I0, D32.
This module does not install or call its configure/calibration routine.
"""
import argparse
import json
from pathlib import Path
import sys
from write_ack import receive_write_ack


def change_yaw_p(bus,target):
    if type(target) is not int or target not in (16,32):raise ValueError('Trial16 or restore32 only')
    before={i:list(bus.read(i,21,3)) for i in range(1,6)}
    if before[1] not in ([32,32,0],[16,32,0]):raise RuntimeError('Unexpected base PID; no write')
    if bus.read(1,55,1)!=b'\1':raise RuntimeError('Lock must stay1; no permanent write allowed')
    rows=bus.snapshot()
    if [r['id'] for r in rows]!=list(range(1,6)):raise RuntimeError('Incomplete feedback')
    torques={r['torque_raw'] for r in rows}
    if torques not in ({0},{1}):raise RuntimeError('Mixed/unknown torque; no gain write')
    for r in rows:
        if r['mode'] or r['status_raw'] or r['speed_raw'] or r['moving_raw']:
            raise RuntimeError('All joints must be healthy and stationary')
    p=rows[0]['position_raw']
    if not 1905<=p<=2133:raise RuntimeError('Base outside reviewed Normal yaw window')
    if torques=={1} and abs(p-int.from_bytes(bus.read(1,42,2),'little'))>2:
        raise RuntimeError('Base not at hold goal')
    if before[1][0]!=target:bus.write_p(target)
    after={i:list(bus.read(i,21,3)) for i in range(1,6)}
    expected=dict(before);expected[1]=[target,32,0]
    if after!=expected or bus.read(1,55,1)!=b'\1':raise RuntimeError('Gain readback mismatch; stop trial')
    return dict(before=before,after=after,lock=1,volatile=True,feedback_before=rows)


def open_trial_bus():
    root=Path(__file__).resolve().parents[2]
    parser=root/'calibration_readonly'
    if not parser.is_dir():parser=root.parent/'calibration_readonly'
    sys.path.insert(0,str(parser))
    from read_only_bus import ReadOnlyBus
    from normal_gaze_motor import decode_state
    class TrialBus(ReadOnlyBus):
        def read(self,sid,address,count):
            if sid not in range(1,6) or (address,count) not in {(8,1),(21,3),(55,1),(33,34),(42,2)}:
                raise ValueError('Trial READ denied')
            body=bytes((sid,4,2,address,count))
            return self._read_response(b'\xff\xff'+body+bytes(((~sum(body))&255,)),sid,count)
        def snapshot(self):return [decode_state(i,self.read(i,33,34)) for i in range(1,6)]
        def write_p(self,target):
            if type(target) is not int or target not in (16,32):raise ValueError('P16/32 only')
            if self.read(1,8,1)!=b'\1' or self.read(1,55,1)!=b'\1':
                raise RuntimeError('Response/lock differs; no write')
            # Fixed unicast ID1 addr21. Never unlock, write goal, or change torque.
            body=bytes((1,4,3,21,target))
            packet=b'\xff\xff'+body+bytes(((~sum(body))&255,))
            self.port.reset_input_buffer()
            if self.port.write(packet)!=len(packet):raise IOError('Partial P WRITE')
            self.port.flush();receive_write_ack(self.port,1,packet)
    return TrialBus()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-p',required=True,type=int,choices=(16,32))
    p.add_argument('--report',required=True,type=Path)
    args=p.parse_args()
    # Prove destination writable and preserve baseline before touching hardware.
    bus=open_trial_bus()
    try:
        baseline={i:list(bus.read(i,21,3)) for i in range(1,6)}
        args.report.write_text(json.dumps(dict(status='pending',baseline=baseline),indent=2),encoding='utf-8')
        report=change_yaw_p(bus,args.base_p)
        args.report.write_text(json.dumps(dict(status='verified',**report),indent=2),encoding='utf-8')
        print(json.dumps(report),flush=True)
    finally:bus.close()


if __name__=='__main__':main()
