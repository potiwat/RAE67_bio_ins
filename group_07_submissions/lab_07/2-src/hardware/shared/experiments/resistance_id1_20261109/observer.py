"""R1 unobstructed yaw calibration. Observer only; no obstruction protection yet."""
import math

PAIR='resistance_id1_R1_baseline'

def blocked(m):
    return (m.operator_stopped or m.stopping.is_set() or m.urgent_stop.is_set() or m.distance_gate.near
        or m.controller.state not in ('READY','FOLLOWING')
        or m.normal_measurement.state not in ('running','complete')
        or getattr(getattr(m.controller,'pose_route',None),'safety_hold',False))

class Observer:
    def __init__(self):
        self.started=None;self.previous=None;self.last_feedback=None;self.complete=False
        self.samples=[];self.events=[]
    def observe(self,m,now):
        if m.lab07_pair_id!=PAIR or m.behavior_trial!='normal':raise ValueError('R1 observer scope violation')
        if (type(now) not in (int,float) or not math.isfinite(now)
            or self.previous is not None and (now<self.previous or now-self.previous>1.)):
            raise ValueError('R1 owner clock gap/regression')
        self.previous=now
        if blocked(m):return
        rows=m.controller.last_rows
        if [r['id'] for r in rows]!=list(range(1,6)):raise ValueError('R1 requires five-joint native feedback')
        r=rows[0];stamp=r.get('sampled_monotonic_s')
        if (type(stamp) not in (int,float) or not math.isfinite(stamp) or not 0<=now-stamp<=.2
            or self.last_feedback is not None and stamp<self.last_feedback):
            raise ValueError('R1 stale/regressing native feedback')
        for key in ('position_raw','goal_raw','internal_target_raw','current_raw','load_raw'):
            maximum=4095 if key in ('position_raw','goal_raw','internal_target_raw') else 65535
            if type(r.get(key)) is not int or not 0<=r[key]<=maximum:raise ValueError('R1 invalid '+key)
        if r.get('mode')!=0 or r.get('torque_raw')!=1 or r.get('status_raw')!=0:
            raise ValueError('R1 unsafe native ID1 status')
        if r.get('target_speed_raw')!=600 or r.get('acceleration_raw')!=3:raise ValueError('R1 ID1 native motion parameters differ')
        if stamp==self.last_feedback or self.complete:return
        self.last_feedback=stamp
        if self.started is None:
            self.started=now;self.events.append(dict(event='baseline_begin',time_s=now,feedback_time_s=stamp,observer_only=True))
        elapsed=now-self.started
        if len(self.samples)>=2000:raise ValueError('R1 observer sample capacity reached')
        self.samples.append(dict(time_s=now,elapsed_s=elapsed,id1_feedback_time_s=stamp,
            id1_goal_error_ticks=r['goal_raw']-r['position_raw'],id1_internal_error_ticks=r['internal_target_raw']-r['position_raw'],
            actual_feedback_interval_s=None if len(self.samples)==0 else stamp-self.samples[-1]['id1_feedback_time_s'],
            observer_only=True,rows=[dict(x) for x in rows]))
        if elapsed+1e-8>=30.:
            self.complete=True;self.events.append(dict(event='baseline_complete',time_s=now,elapsed_s=elapsed,samples=len(self.samples)))
            print('R1_BASELINE_COMPLETE OBSERVER ONLY Q to save',flush=True)

class Sessions:
    def __init__(self):self.attempts=[]
    def get(self,m):
        if self.attempts:
            old,p=self.attempts[-1]
            if old is m:return p
            if not old.finished.is_set():raise RuntimeError('Previous R1 UART owner still closing')
        p=Observer();self.attempts.append((m,p));return p

def scoped_step(original,sessions,driver,m,now):
    if getattr(m,'lab07_pair_id',None)!=PAIR:return original(driver,m,now)
    # Existing yaw/head visual following is retained; no new position commands.
    driver.rhythm.advance(now,False,exclusive=True);driver.mode='normal'
    driver.centers={2:m.controller.normal[2],3:m.controller.normal[3]}
    m.posture_body_plan=dict(mode='normal',time_s=now,goals=dict(driver.centers))
    sessions.get(m).observe(m,now)

def label(original,sessions,m):
    if getattr(m,'lab07_pair_id',None)!=PAIR:return original(m)
    if blocked(m):return original(m)
    p=next((p for owner,p in sessions.attempts if owner is m),None)
    if p is None or not p.samples:return 'R1 BASELINE OBSERVER ONLY | '+original(m)
    elapsed=min(30.,p.samples[-1]['elapsed_s']);status='COMPLETE Q:save' if p.complete else 'collecting'
    return f'R1 ID1 BASELINE {status} {elapsed:.0f}/30s | OBSERVER ONLY | H:stop Q:save'

def main():
    import sys,json,runpy,atexit
    from pathlib import Path
    root=Path(__file__).resolve().parents[3]
    sys.path[:0]=[str(root),str(root/'bio_inspire/runtime'),str(root/'shared/runtime')]
    profile=root/'bio_inspire/hardware/resistance_id1_20261109/R1_BASELINE.json'
    base=json.loads((root/'bio_inspire/hardware/normal_motion_20261106/P1_C0.json').read_text())
    assert json.loads(profile.read_text())=={**base,'lab07_pair_id':PAIR,'id1_resistance_baseline_observer':True}
    from bio_inspire.runtime.body_rhythm import BodyRhythmDriver
    from bio_inspire.runtime.camera_motor import CameraMotor
    from bio_inspire.experiments.encoder_quality_20261107.single_id2 import polled_button_class
    import physical_button
    physical_button.PhysicalButton=polled_button_class()
    original=BodyRhythmDriver.step;original_label=CameraMotor.label;sessions=Sessions()
    BodyRhythmDriver.step=lambda driver,m,now:scoped_step(original,sessions,driver,m,now)
    CameraMotor.label=lambda m:label(original_label,sessions,m)
    def save():
        out=root/'shared/hardware/resistance_id1_20261109';out.mkdir(parents=True,exist_ok=True)
        attempts=[dict(attempt=i,events=p.events,samples=len(p.samples),complete=p.complete) for i,(m,p) in enumerate(sessions.attempts)]
        (out/'R1_EVENTS.json').write_text(json.dumps(dict(purpose='unobstructed_baseline_only_not_collision_test',attempts=attempts),indent=2))
        (out/'R1_SAMPLES.jsonl').write_text(''.join(json.dumps({**s,'attempt':i})+'\n' for i,(m,p) in enumerate(sessions.attempts) for s in p.samples))
    atexit.register(save)
    sys.argv=[str(root/'shared/runtime/camera_preview.py'),'--live','--simple-ui','--max-age-s','.5','--fps','30',
        '--roll-compensation','--normal-profile',str(profile),'--diagnostic-snapshot']
    runpy.run_path(sys.argv[0],run_name='__main__')

if __name__=='__main__':main()
