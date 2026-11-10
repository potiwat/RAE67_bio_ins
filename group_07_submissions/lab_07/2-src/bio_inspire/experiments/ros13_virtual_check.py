"""Generate owner telemetry using actual CameraMotor with virtual I/O only."""
import hashlib,json
from pathlib import Path
from unittest.mock import patch
from .runtime_integration import ROOT,run_runtime
from .ahm_input_bridge import InputFrame
from bio_inspire.runtime.camera_motor import CameraMotor
from bio_inspire.runtime.session_recording import record_owner


def generate(out,condition):
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    profile=ROOT/'bio_inspire/hardware/happy_dynamic_c1_trial.json'
    config=json.loads(profile.read_text(encoding='utf8'))
    config['normal_ahm_condition']=condition
    captured=[]
    class Sink:
        first=None
        def record(self,row):
            self.first=row['time_s'];captured.append(json.loads(json.dumps(row)))
    sink=Sink();original=CameraMotor._record_trace
    def capture(m,row):
        original(m,row)
        m.lab07_recorder=sink;record_owner(m,row)
    frames=[]
    for k in range(1800):
        t=k*.05
        button=15<=t<15.3
        touch=30<=t<33 or any(s<=t<s+.15 for s in (49.,49.4,49.8))
        near=65<=t<72
        frames.append(InputFrame(t,t,button,touch,'range',.18 if near else 1.2,'virtual_'+str(k)))
    with patch.object(CameraMotor,'_record_trace',capture):
        result=run_runtime(out/'runtime',condition=condition,duration_s=90.,frames_override=frames,profile_path=profile)
    metadata=dict(run_id='virtual_'+condition,pair_id='virtual_P1',condition=condition,
                  origin='virtual_actual_runtime_ideal_memory_feedback_not_hardware',
                  clock='virtual_seconds',profile=config,source_hashes={
                  str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in [Path(__file__),ROOT/'bio_inspire/runtime/session_recording.py',ROOT/'bio_inspire/experiments/ros13.py']})
    (out/'metadata.json').write_text(json.dumps(metadata,indent=2),encoding='utf8')
    data=''.join(json.dumps(r,allow_nan=False,separators=(',',':'))+'\n' for r in captured)
    (out/'trace.jsonl').write_text(data,encoding='utf8',newline='\n')
    (out/'summary.json').write_text(json.dumps(dict(complete=True,written=len(captured),dropped=0,error=None,
                      trace_sha256=hashlib.sha256(data.encode('utf8')).hexdigest())),encoding='utf8')
    from .ros13 import Encoder,TOPICS
    encoder=Encoder(metadata);counts={t:0 for t in TOPICS}
    for k,row in enumerate(captured):
        for packet in encoder.encode(row,k):counts[packet['topic']]+=1
    report=dict(scope='software only; no real devices',counts=counts,
                states=result['behaviors'],forbidden_writes=result['forbidden_writes'],bounds_violations=result['bounds_violations'])
    (out/'coverage.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report))


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--condition',choices=['C0','C1'],required=True)
    a=p.parse_args();generate(a.out,a.condition)
