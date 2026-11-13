"""R2 isolated ID1 pilot; existing yaw startup configuration, no PID changes."""
import math
if __name__=='__main__':
    import sys
    from pathlib import Path
    _root=Path(__file__).resolve().parents[3]
    sys.path[:0]=[str(_root),str(_root/'bio_inspire/runtime'),str(_root/'shared/runtime')]
from shared.experiments.resistance_id1_20261109.pause_guard import ID1PauseGuard
from shared.experiments.resistance_id1_20261109.observer import blocked
from bounded_motion import BoundedMotion,MotionLimits

PAIR='resistance_id1_R2_pilot'

class Pilot:
    duration_s=45.
    def __init__(self):
        self.guard=ID1PauseGuard();self.started=None;self.previous=None;self.motion=None;self.center=None;self.limits=None
        self.target=None;self.last_goal=None;self.complete=False;self.resume_requested=False;self.paused=False
        self.pause_started_s=None;self.paused_total_s=0.
        self.samples=[];self.events=[]
        self.yaw_config_requested_s=None;self.awake_readback_wait_s=None;self.safety_wait=False
    def hold(self,m,now,reason):
        # A single fresh measured hold replaces the motion target; no torque release.
        m.controller.bus.hold_actual(1)
        goal=int.from_bytes(m.controller.bus.read(1,42,2),'little')
        m.controller.last_goal=goal;self.last_goal=goal;self.motion=None
        self.events.append(dict(event='hold_ack',time_s=now,reason=reason,hold_goal_ticks=goal))
    def step(self,driver,m,now):
        if m.lab07_pair_id!=PAIR or m.behavior_trial!='normal':raise ValueError('R2 pilot scope violation')
        if (type(now) not in (int,float) or not math.isfinite(now)
            or self.previous is not None and (now<self.previous or self.started is not None and now-self.previous>.2)):
            raise ValueError('R2 control clock gap/regression')
        self.previous=now
        if blocked(m):return
        c=m.controller;row=next(r for r in c.last_rows if r['id']==1)
        if self.started is None and row['target_speed_raw']==600 and row['acceleration_raw']==1:
            # Normal startup uses ACC1; visual following normally restores ACC3.
            # R2 suppresses visual goals, so request that same configuration once.
            age=now-row['sampled_monotonic_s']
            if (not 0<=age<=.18 or row['mode']!=0 or row['torque_raw']!=1 or row['status_raw']!=0
                or row['speed_raw'] or row['moving_raw']
                or c.tracking_speed!=600 or c.tracking_acceleration!=3):
                raise ValueError('R2 unsafe startup yaw configuration')
            if self.yaw_config_requested_s is None:
                c.configure_tracking(yaw=True,pitch=False);self.yaw_config_requested_s=now
                self.events.append(dict(event='existing_yaw_configuration_requested',time_s=now,speed_raw=600,acceleration_raw=3))
            elif now-self.yaw_config_requested_s>1.:
                raise ValueError('R2 startup yaw configuration readback timeout')
            return
        if row['target_speed_raw']!=600 or row['acceleration_raw']!=3:raise ValueError('R2 ID1 native parameters differ')
        if self.started is None and getattr(m,'fast_awake_trial',False):
            # prepare_awake runs after snapshot and can write IDs2-5 this cycle.
            # Do not arm against that pre-configuration snapshot: its next gap
            # includes setup UART work, not a missed active feedback deadline.
            expected={1:3,2:8,3:8,4:12,5:6}
            rows={r['id']:r for r in c.last_rows}
            if set(rows)!=set(expected):raise ValueError('R2 incomplete awake readback')
            for sid,acc in expected.items():
                r=rows[sid]
                if r['target_speed_raw']!=600 or r['acceleration_raw'] not in (1,acc):
                    raise ValueError('R2 unexpected awake configuration')
            if any(rows[sid]['acceleration_raw']!=acc for sid,acc in expected.items()):
                if self.awake_readback_wait_s is None:
                    self.awake_readback_wait_s=now
                    self.events.append(dict(event='await_fresh_awake_readback',time_s=now))
                elif now-self.awake_readback_wait_s>1.:
                    raise ValueError('R2 awake configuration readback timeout')
                return
        result=self.guard.update(row,now)
        if result['state']=='FAULT_HOLD':raise RuntimeError('R2 guard unavailable: '+str(result['reason']))
        if self.complete:return
        if self.started is None:
            self.center=row['position_raw'];span=getattr(m,'id1_resistance_half_span_ticks',34)
            if type(span) is not int or span not in (34,114):raise ValueError('R2 unapproved trial span')
            low=self.center-span;high=self.center+span
            a,b=c.yaw_window;inset=c.command_margin_ticks
            if not a+inset<=low<high<=b-inset or not c.bus.windows[1][0]<=low<high<=c.bus.windows[1][1]:
                raise ValueError('R2 path outside existing approved yaw window')
            self.limits=MotionLimits(low,high,20.,40.,.2);self.target=high
            self.motion=BoundedMotion(self.center,now,self.limits);self.started=now
            self.events.append(dict(event='begin',time_s=now,center_ticks=self.center,command_bounds_ticks=[low,high],
                host_speed_ticks_s=20,host_acceleration_ticks_s2=40,native_speed_raw=600,native_acceleration_raw=3,
                tof_policy='telemetry_only' if tof_observe_only(m) else 'guarded',warning='Pilot only: no force or collision safety validation'))
        elapsed=now-self.started-self.paused_total_s-(0. if self.pause_started_s is None else now-self.pause_started_s)
        driver.rhythm.advance(now,False,exclusive=True);driver.mode='normal';driver.centers={2:c.normal[2],3:c.normal[3]}
        m.posture_body_plan=dict(mode='normal',time_s=now,goals=dict(driver.centers))
        if result['trip']:
            self.hold(m,now,'resistance_suspected');self.paused=True;self.pause_started_s=now
            self.events.append(dict(event='resistance_pause',time_s=now,elapsed_s=elapsed,row=dict(row)))
        if elapsed+1e-8>=self.duration_s:
            if not self.complete:
                if not self.paused:self.hold(m,now,'pilot_complete')
                self.complete=True;self.resume_requested=False
                self.events.append(dict(event='complete',time_s=now,elapsed_s=elapsed))
        elif self.resume_requested:
            self.resume_requested=False
            if self.guard.state=='RESISTANCE_PAUSE':
                if not self.limits.low<=row['position_raw']<=self.limits.high:
                    raise ValueError('R2 actual pose left pilot bounds; inspect before resume')
                self.guard.resume(clearance_confirmed=True);self.paused=False
                if self.pause_started_s is not None:self.paused_total_s+=now-self.pause_started_s
                self.pause_started_s=None
                self.motion=BoundedMotion(row['position_raw'],now,self.limits)
                self.events.append(dict(event='operator_resume',time_s=now,elapsed_s=elapsed,actual_ticks=row['position_raw']))
        if not self.complete and self.guard.state=='MONITORING':
            if self.motion is None:self.motion=BoundedMotion(row['position_raw'],now,self.limits)
            if abs(self.motion.position-self.target)<=1. and abs(self.motion.velocity)<1.:
                self.target=self.limits.low if self.target==self.limits.high else self.limits.high
            goal=round(self.motion.step(self.target,now))
            # Bound future target lead as well as total path. Never increase force by unbounded catch-up.
            q=row['position_raw'];goal=max(round(self.limits.low),min(round(self.limits.high),max(q-24,min(q+24,goal))))
            if not blocked(m) and goal!=self.last_goal:
                c.bus.write(1,42,goal.to_bytes(2,'little'));c.last_goal=goal;self.last_goal=goal
        if len(self.samples)>=4000:raise ValueError('R2 bounded diagnostic storage full')
        self.samples.append(dict(time_s=now,elapsed_s=elapsed,wall_elapsed_s=now-self.started,paused_total_s=self.paused_total_s,complete=self.complete,guard_state=self.guard.state,
            goal_ticks=self.last_goal,center_ticks=self.center,target_ticks=self.target,rows=[dict(r) for r in c.last_rows]))

class Sessions:
    def __init__(self,factory=Pilot):self.attempts=[];self.factory=factory
    def get(self,m):
        if self.attempts:
            old,p=self.attempts[-1]
            if old is m:return p
            if not old.finished.is_set():raise RuntimeError('Previous R2 UART owner still closing')
        p=self.factory();self.attempts.append((m,p));return p

def enqueue_pilot_key(original,m,key):
    if getattr(m,'lab07_pair_id',None)==PAIR and key in (ord('r'),ord('R')):
        # UI thread only enqueues; UART and clearance checks stay on owner thread.
        with m.lock:
            if m.stopping.is_set() or m.urgent_stop.is_set():return
            if len(m.keys)<8 and not any(k in (ord('r'),ord('R')) for k in m.keys):m.keys.append(key)
        return
    return original(m,key)


def handle_key(original,sessions,m,key):
    if getattr(m,'lab07_pair_id',None)==PAIR and key in (ord('r'),ord('R')):
        p=next((p for owner,p in sessions.attempts if owner is m),None)
        if p is not None:
            accepted=not p.complete and not blocked(m) and p.guard.state=='RESISTANCE_PAUSE'
            p.events.append(dict(event='resume_key_received',time_s=m.now() if hasattr(m,'now') else p.previous,accepted=accepted))
            if accepted:p.resume_requested=True
        return
    return original(m,key)

def tof_observe_only(m):
    return getattr(m,'lab07_pair_id',None)==PAIR and getattr(m,'id1_tof_observe_only',False) is True

def observe_distance(m,now):
    from physical_distance import distance_input_kind
    source=getattr(m,'physical_distance',None);sample=None if source is None else source.latest()
    now=max(now,m.now());kind=distance_input_kind(sample,now)
    m.distance_view=dict(sample or {},near=False,event=None,input_kind=kind,
        observed_near=kind=='range' and sample['distance_cm']<=20.,policy='telemetry_only_id1_trial')
    return False

def telemetry_distance_class(base):
    # Instantiated only by this isolated entry point. Retain the existing input
    # worker and its error reporting, with no freshness gate on trial motion.
    class TelemetryDistance(base):
        def wait_first_sample(self,timeout_s=5.):return
        def require_fresh(self):return
    return TelemetryDistance


def poll_startup_distance(original,m,now,dispatch=True):
    if tof_observe_only(m):return observe_distance(m,now)
    # Reuse the existing startup WAIT_TOF path only before the R2 start boundary.
    qualified=(getattr(m,'lab07_pair_id',None)==PAIR and m.controller.state=='NORMAL_STARTUP'
        and getattr(getattr(m,'normal_measurement',None),'state',None)=='waiting'
        and not getattr(getattr(m,'lab07_start_gate',None),'started',True))
    if not qualified:return original(m,now,dispatch=dispatch)
    old=getattr(m,'presentation_startup_tof_recovery',False)
    m.presentation_startup_tof_recovery=True
    try:return original(m,now,dispatch=dispatch)
    finally:m.presentation_startup_tof_recovery=old

def service_measurement(original,sessions,measurement,m,now):
    # R2 uses the research fixture only for its five-button boundary/logger.
    # A research trial must abort on interrupted inputs; this separate pause
    # pilot must instead keep polling during the existing safe ToF hold.
    if (getattr(m,'lab07_pair_id',None)!=PAIR or measurement.state not in ('running','complete')
        or getattr(m,'operator_stopped',False) or m.stopping.is_set() or m.urgent_stop.is_set()
        or m.controller.state in ('FAULT','STOPPED')):
        return original(measurement,m,now)
    from bio_inspire.runtime.distance_behavior import poll_distance
    from physical_distance import distance_input_kind
    if tof_observe_only(m):
        observe_distance(m,now)
        for name in ('physical_button','physical_touch'):
            source=getattr(m,name,None)
            if source is not None:source.drain_events(m.now())
        measurement.last_callback=m.now()
        return
    p=sessions.get(m);c=m.controller;source=getattr(m,'physical_distance',None)
    sample=None if source is None else source.latest();now=max(now,m.now())
    kind=distance_input_kind(sample,now)
    near=(kind=='range' and sample['distance_cm']<=20.) or m.distance_gate.near
    if c.state=='WAIT_TOF' or kind=='fault' or near:
        if not p.safety_wait:
            p.safety_wait=True;p.motion=None
            p.events.append(dict(event='tof_safety_wait',time_s=now,input_kind=kind,sample=sample))
    poll_distance(m,now,dispatch=False)
    if m.distance_gate.near and c.state in ('READY','FOLLOWING'):
        m._hold('R2 ToF Near: wait for fresh clear',all_axes=True)
        if c.state!='FAULT':c.state='WAIT_TOF';m.behavior_trial='distance_wait'
    if c.state in ('FAULT','STOPPED') or m.operator_stopped or m.stopping.is_set() or m.urgent_stop.is_set():
        return original(measurement,m,m.now())
    if p.safety_wait:
        # Never use cached distance, low current, or the pre-hold trajectory to restart.
        sample=None if source is None else source.latest();now=m.now();kind=distance_input_kind(sample,now)
        clear=kind=='no_target' or kind=='range' and sample['distance_cm']>=28.
        rows=c.last_rows;row=next((r for r in rows if r['id']==1),None)
        healthy=(len(rows)==5 and all(r.get('mode')==0 and r.get('status_raw')==0 and r.get('torque_raw')==1 for r in rows)
                 and row is not None and not row.get('moving_raw') and not row.get('speed_raw')
                 and 0<=now-row.get('sampled_monotonic_s',-float('inf'))<=.18)
        if c.state not in ('READY','FOLLOWING') or m.distance_gate.near or not clear or not healthy:return
        if p.guard.state=='FAULT_HOLD':raise RuntimeError('R2 motor fault remains latched')
        if p.limits is not None and not p.limits.low<=row['position_raw']<=p.limits.high:
            raise RuntimeError('R2 actual yaw left pilot path during safety wait')
        p.safety_wait=False;p.previous=None;p.motion=None
        p.guard.history.clear();p.guard.last_now=None;p.guard.last_stamp=None
        m.behavior_trial='normal';c.last_error=''
        p.events.append(dict(event='tof_fresh_clear',time_s=now,actual_ticks=row['position_raw'],sample=sample))
    for name in ('physical_button','physical_touch'):
        source=getattr(m,name,None)
        if source is not None:source.drain_events(m.now())
    measurement.last_callback=m.now()

def record_measurement(original,sessions,measurement,m,now):
    if (getattr(m,'lab07_pair_id',None)==PAIR and measurement.state in ('running','complete')
        and not m.operator_stopped and not m.stopping.is_set() and not m.urgent_stop.is_set()
        and m.controller.state in ('READY','FOLLOWING','WAIT_TOF')):
        recorder=getattr(m,'lab07_recorder',None)
        if recorder is None:
            if getattr(m,'lab07_recording_seconds',None) is not None:
                raise RuntimeError('R2 raw session recorder missing')
        else:
            # invalid is a research-quality flag (WAIT_TOF sets it), not an
            # I/O failure. Preserve it in the raw summary; never clear it.
            error=recorder.error or getattr(recorder,'input_health_error',None) or getattr(m,'lab07_recording_error',None)
            if error or recorder.dropped:
                raise RuntimeError(f'R2 recording failure: {error or "dropped rows"}')
            if recorder.end_seen and not sessions.get(m).complete:
                raise RuntimeError('R2 raw capture ceiling reached before pilot completion')
        # _publish already streams all rows, including waits and recovery.
        # Do not call NormalMeasurement.record: its C0/C1 quality policy also
        # aborts after returning from WAIT, even when file I/O is healthy.
        return
    return original(measurement,m,now)


def service_rhythm(original,sessions,m):
    if getattr(m,'lab07_pair_id',None)!=PAIR:return original(m)
    p=sessions.get(m)
    if p.safety_wait or blocked(m):return
    p.step(m.rhythm_driver,m,m.now())
    # Avoid the normal gaze-start configuration hook: this pilot owns only ID1.
    with m.lock:m.rhythm_view_cache=m.rhythm_driver.rhythm.status()


def pilot_label(original,sessions,m):
    if getattr(m,'lab07_pair_id',None)!=PAIR:return original(m)
    p=next((p for owner,p in sessions.attempts if owner is m),None)
    if p is not None and p.safety_wait:return 'R2 WAIT ToF | Holding; waiting for fresh clear distance | H:stop Q:save'
    if blocked(m):return original(m)
    if p is None or not p.samples:return 'R2 PILOT | '+original(m)
    if hasattr(p,'phase'):
        return f'R3 NATIVE {p.phase} | attempts {p.attempts}/3 | active {p.active_s:.1f}/45s | H:stop Q:save'
    if p.complete:return 'R2 COMPLETE45/45s | Q:save | NOT SAFETY VALIDATED'
    if p.guard.state=='RESISTANCE_PAUSE':return 'R2 RESISTANCE PAUSE | Clear path, then R:continue | H:stop Q:save'
    return f"R2 ID1 SLOW PILOT {p.samples[-1]['elapsed_s']:.0f}/45s | H:stop Q:save"

def main():
    import sys,json,runpy,atexit
    from pathlib import Path
    root=Path(__file__).resolve().parents[3];sys.path[:0]=[str(root),str(root/'bio_inspire/runtime'),str(root/'shared/runtime')]
    retry_mode='--capped-retry' in sys.argv
    capped_mode='--capped' in sys.argv or retry_mode
    native_mode='--native' in sys.argv or capped_mode
    profile=root/('bio_inspire/hardware/resistance_id1_20261109/R4_CAPPED_FREE.json' if capped_mode else 'bio_inspire/hardware/resistance_id1_20261109/R3_NATIVE_RETRY.json' if native_mode else 'bio_inspire/hardware/resistance_id1_20261109/R2_PILOT.json')
    base=json.loads((root/'bio_inspire/hardware/normal_motion_20261106/P1_C0.json').read_text())
    expected={**base,'lab07_pair_id':PAIR,'id1_resistance_pause_pilot':True,'id1_tof_observe_only':True,'id1_resistance_half_span_deg':10}
    if native_mode:expected['id1_native_resistance_retry_trial']=True
    if capped_mode:expected['id1_capped_safety_trial']=True
    assert json.loads(profile.read_text())==expected
    from bio_inspire.runtime.camera_motor import CameraMotor
    if capped_mode:
        from bio_inspire.runtime import camera_motor as camera_motor_module
        if retry_mode:
            from shared.experiments.resistance_id1_20261109.capped_retry import install as install_cap
        else:
            from shared.experiments.resistance_id1_20261109.capped_trial import install as install_cap
        install_cap(camera_motor_module)
    import physical_distance
    physical_distance.PhysicalDistance=telemetry_distance_class(physical_distance.PhysicalDistance)
    original_public_key=CameraMotor.key
    CameraMotor.key=lambda m,key:enqueue_pilot_key(original_public_key,m,key)
    original_init=CameraMotor.__init__
    def init(m,*args,**kwargs):
        m.id1_tof_observe_only=True;m.id1_resistance_half_span_ticks=114
        return original_init(m,*args,**kwargs)
    CameraMotor.__init__=init

    from bio_inspire.runtime.body_rhythm import BodyRhythmDriver
    from bio_inspire.runtime import distance_behavior
    from bio_inspire.experiments.encoder_quality_20261107.single_id2 import polled_button_class
    import physical_button
    physical_button.PhysicalButton=polled_button_class()
    original_step=BodyRhythmDriver.step;original_apply=CameraMotor._apply;original_key=CameraMotor._key;original_label=CameraMotor.label
    if retry_mode:
        from shared.experiments.resistance_id1_20261109.capped_retry import CappedRetry
        sessions=Sessions(CappedRetry)
    elif capped_mode:
        from shared.experiments.resistance_id1_20261109.capped_trial import CappedNative
        sessions=Sessions(CappedNative)
    elif native_mode:
        from shared.experiments.resistance_id1_20261109.native_retry import NativeRetry
        sessions=Sessions(NativeRetry)
    else:sessions=Sessions()
    import play_view
    from shared.experiments.resistance_id1_20261109.trial_view import draw as draw_trial_view
    original_draw=play_view.draw
    play_view.draw=lambda cv,image,result,motor=None,start_error='':draw_trial_view(original_draw,sessions,cv,image,result,motor,start_error)
    from bio_inspire.runtime.normal_measurement import NormalMeasurement
    original_record=NormalMeasurement.record
    NormalMeasurement.record=lambda measurement,m,now:record_measurement(original_record,sessions,measurement,m,now)
    original_measurement=NormalMeasurement.service
    NormalMeasurement.service=lambda measurement,m,now:service_measurement(original_measurement,sessions,measurement,m,now)
    original_rhythm=CameraMotor._service_body_rhythm
    CameraMotor._service_body_rhythm=lambda m:service_rhythm(original_rhythm,sessions,m)

    original_distance=distance_behavior.poll_distance
    distance_behavior.poll_distance=lambda m,now,dispatch=True:poll_startup_distance(original_distance,m,now,dispatch)
    def step(driver,m,now):
        if getattr(m,'lab07_pair_id',None)==PAIR:return sessions.get(m).step(driver,m,now)
        return original_step(driver,m,now)
    BodyRhythmDriver.step=step
    CameraMotor._apply=lambda m,result,now:None if getattr(m,'lab07_pair_id',None)==PAIR else original_apply(m,result,now)
    CameraMotor._key=lambda m,key:handle_key(original_key,sessions,m,key)
    CameraMotor.label=lambda m:pilot_label(original_label,sessions,m)
    def save():
        out=root/'shared/hardware/resistance_id1_20261109';out.mkdir(parents=True,exist_ok=True)
        (out/'R2_EVENTS.json').write_text(json.dumps(dict(purpose='experimental_pause_pilot_not_safety_certified',variant='capped_qualified_retry_R5' if retry_mode else 'capped_early_pause_no_retry' if capped_mode else 'native_auto_probe' if native_mode else 'incremental_manual_resume',attempts=[
            dict(attempt=i,events=p.events,samples=len(p.samples),complete=p.complete) for i,(m,p) in enumerate(sessions.attempts)]),indent=2))
        if capped_mode:
            from shared.experiments.resistance_id1_20261109.capped_trial import AUDITS
            (out/'R4_CAP_AUDIT.json').write_text(json.dumps(AUDITS,indent=2))
        (out/'R2_SAMPLES.jsonl').write_text(''.join(json.dumps({**s,'attempt':i})+'\n' for i,(m,p) in enumerate(sessions.attempts) for s in p.samples))
    atexit.register(save)
    sys.argv=[str(root/'shared/runtime/camera_preview.py'),'--live','--simple-ui','--max-age-s','.5','--fps','30',
        '--roll-compensation','--normal-profile',str(profile),'--diagnostic-snapshot']
    runpy.run_path(sys.argv[0],run_name='__main__')

if __name__=='__main__':main()
