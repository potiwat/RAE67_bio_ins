"""Bounded disk recorder. Writer thread owns files only, never hardware."""
import hashlib,json,math,queue,threading
from pathlib import Path

class SessionRecorder:
    def __init__(self,directory,condition,duration_s,metadata=None):
        if condition not in ('C0','C1') or type(duration_s) not in (int,float) or not math.isfinite(duration_s) or not 1<=duration_s<=600:
            raise ValueError('Expected C0/C1, duration1..600s')
        self.path=Path(directory);self.path.mkdir(parents=True,exist_ok=True)
        self.stream=(self.path/'trace.jsonl').open('x',encoding='utf8',newline='\n')
        self.condition=condition;self.duration=duration_s;self.metadata=metadata or {}
        (self.path/'metadata.json').write_text(json.dumps(self.metadata,allow_nan=False,indent=2)+'\n',encoding='utf8')
        self.queue=queue.Queue(maxsize=256);self.done=threading.Event()
        self.first=None;self.last=None;self.end_seen=False;self.accepted=0;self.written=0;self.dropped=0;self.error=None;self.bytes=0;self.invalid=False
        from bio_inspire.experiments.ros13 import DigitalContinuity
        self.digital_audit=DigitalContinuity();self.input_health_error=None
        self.thread=threading.Thread(target=self._write,name='lab07-disk-writer',daemon=True);self.thread.start()
    def record(self,row):
        if self.done.is_set() or self.end_seen or self.error:return
        if row.get('state') in ('FAULT','STOPPED','WAIT_TOF'):self.invalid=True
        if (row.get('experimental_inputs') or {}).get('state')=='aborted':self.invalid=True
        if 'digital_inputs' in row:
            try:self.digital_audit.check(row['digital_inputs'])
            except ValueError as error:self.invalid=True;self.input_health_error=str(error)
        t=row.get('time_s')
        if type(t) not in (int,float) or not math.isfinite(t) or self.last is not None and t<self.last:
            self.error='invalid_or_regressing_clock';return
        if self.first is None:self.first=t
        self.last=t
        if self.accepted>=20000:self.error='row_limit';return
        try:
            data=json.dumps(row,allow_nan=False,separators=(',',':'))+'\n'
            if len(data.encode('utf8'))>65536:raise ValueError('oversized_row')
            self.queue.put_nowait(data);self.accepted+=1
        except queue.Full:self.dropped+=1
        except (ValueError,TypeError) as e:self.error=str(e)
        if t-self.first>=self.duration:self.end_seen=True;self.done.set()
    def _write(self):
        try:
            while not self.done.is_set() or not self.queue.empty():
                try:data=self.queue.get(timeout=.05)
                except queue.Empty:continue
                size=len(data.encode('utf8'))
                if self.bytes+size>128*1024*1024:raise ValueError('file_limit')
                self.stream.write(data);self.stream.flush();self.bytes+=size;self.written+=1
            self.stream.flush()
        except Exception as e:self.error=str(e)
        finally:
            self.stream.close()
            summary=dict(condition=self.condition,duration_s=self.duration,first_s=self.first,last_s=self.last,
                complete=self.end_seen and not self.invalid and not self.error and not self.dropped and self.written==self.accepted,
                capture_complete=self.end_seen and not self.error and not self.dropped and self.written==self.accepted,
                quality_hold_or_invalid_seen=self.invalid,
                accepted=self.accepted,written=self.written,dropped=self.dropped,error=self.error,
                input_health_error=self.input_health_error,metadata=self.metadata)
            summary['trace_sha256']=hashlib.sha256((self.path/'trace.jsonl').read_bytes()).hexdigest()
            (self.path/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n',encoding='utf8')
    def close(self):
        self.done.set();self.thread.join(timeout=3.)
        if self.thread.is_alive():self.error='writer_close_timeout'


def validate_recording(config):
    duration=config.get('lab07_recording_seconds')
    if duration is None:return None
    from bio_inspire.runtime.normal_measurement import motion_experiment
    motion=motion_experiment(config)
    if type(duration) not in (int,float) or duration not in (30,60,180,600) or config.get('normal_ahm_condition') not in ('C0','C1') or config.get('ahm_scope')!='all_states' or config.get('normal_measurement_source') is not None and not motion:
        raise ValueError('Lab07 recording requires live all-state C0/C1,30,60,180 or600 seconds')
    return duration


def prepare_recorder(m):
    duration=getattr(m,'lab07_recording_seconds',None)
    if duration is None:return None
    import datetime,uuid
    root=Path(__file__).resolve().parents[2];profile=Path(m.lab07_profile_path)
    run=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8]
    metadata={**m.lab07_metadata,'run_id':run,'pair_id':getattr(m,'lab07_pair_id','unassigned'),
              'condition':m.lab07_condition,'clock':'Pi CLOCK_BOOTTIME seconds',
              'semantic_mapping':dict(tilt=4,extend=2,nod=5,unit='rad relative Normal; telemetry only')}
    trial=getattr(m,'automatic_trial',None)
    if trial is not None:
        from bio_inspire.runtime.automatic_trial import schedule,schedule_sha256
        metadata.update(input_origin='scripted_experimental_inputs',experimental_schedule=schedule(),
                        schedule_sha256=schedule_sha256(),physical_inputs_recorded_separately=True)
    measurement=getattr(m,'normal_measurement',None)
    if measurement is not None and measurement.streamed:
        metadata.update(input_origin='recorded_stimulus_replay',experiment='normal_motor_motion180',replay_fixture_sha256=measurement.fixture_sha256,replay_source=measurement.replay.fixture.get('reference_source'),replay_source_sha256=measurement.replay.fixture.get('reference_sha256'),measurement_sidecar=str(measurement.path),clock_note='owner BOOTTIME; per-joint feedback MONOTONIC; per-snapshot before/after anchors')
    return SessionRecorder(root/'bio_inspire/results/lab07_sessions'/run,m.lab07_condition,duration,metadata)


def recording_metadata(profile_bytes):
    root=Path(__file__).resolve().parents[2]
    sources={str(p.relative_to(root)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()
        for base in ('bio_inspire/runtime','shared/runtime') for p in (root/base).glob('*.py') if not p.name.startswith('test_')}
    return dict(origin='live_robot',profile_sha256=hashlib.sha256(profile_bytes).hexdigest(),
        profile=json.loads(profile_bytes.decode('utf-8-sig')),source_hashes=sources)



def record_owner(m,row):
    gate=getattr(m,'lab07_start_gate',None)
    if gate is not None and not gate.started:return
    recorder=getattr(m,'lab07_recorder',None)
    if recorder is None:return
    if recorder.first is None and (row.get('state') not in ('READY','FOLLOWING') or row.get('behavior')!='normal' or getattr(m,'operator_stopped',False)):return
    driver=getattr(m,'rhythm_driver',None);rhythm=getattr(driver,'rhythm',None)
    fsm=getattr(m,'automatic_fsm',None);route=getattr(m.controller,'pose_route',None)
    digital={}
    cursors=getattr(m,'lab07_digital_cursors',{})
    for channel in ('button','touch'):
        source=getattr(m,'physical_'+channel,None)
        if source is None:continue
        view=source.diagnostics();old=cursors.get(channel,(-math.inf,0))
        raw=view.get('raw_edges',[]);stable=view.get('stable_edges',[])
        view['raw_edges']=[e for e in raw if e['time_s']>old[0]]
        view['stable_edges']=[e for e in stable if e['sequence']>old[1]]
        view.pop('accepted_source_times',None)
        view['raw_history_may_be_truncated']=len(raw)==24 and raw[0]['time_s']>old[0] and old[0]!=-math.inf
        cursors[channel]=(raw[-1]['time_s'] if raw else old[0],view.get('stable_sequence',old[1]))
        digital[channel]=view
    m.lab07_digital_cursors=cursors
    # Snapshot only: no ROS, file/network I/O or additional hardware access here.
    from bio_inspire.experiments.ros13 import COLORS
    model=getattr(fsm,'fsm',None);events=list(getattr(model,'events',()))
    serial=getattr(m,'lab07_fsm_serial',0)
    fresh=[dict(e) for e in events if int(e['event_id'].rsplit('_',1)[1])>serial]
    lost=bool(fresh and int(fresh[0]['event_id'].rsplit('_',1)[1])>serial+1)
    if fresh:m.lab07_fsm_serial=int(fresh[-1]['event_id'].rsplit('_',1)[1])
    led=getattr(m,'last_led_behavior',None)
    extra=dict(digital_inputs=digital,oscillator=None if rhythm is None else rhythm.status(),fsm=None if fsm is None else fsm.snapshot(),
        touch_event=getattr(m,'last_touch_event',None),pose_phase=getattr(route,'phase',None),
        error=getattr(m.controller,'last_error',None),
        ros=dict(schema_version=1,events=fresh,event_history_lost=lost,led_behavior=led,
                 led_rgb_255=COLORS.get(led,[0,0,0]) if getattr(m,'led_ring',None) is not None else [0,0,0],
                 brightness=.03))
    measurement=getattr(m,'normal_measurement',None)
    if measurement is not None and measurement.streamed:
        import time
        b1=time.clock_gettime(time.CLOCK_BOOTTIME);mono=time.monotonic();b2=time.clock_gettime(time.CLOCK_BOOTTIME)
        extra['normal_motion']=dict(state=measurement.state,replay_elapsed_s=row['time_s']-measurement.replay.started,fixture_sha256=measurement.fixture_sha256)
        extra['clock_anchor']=dict(boottime_before_s=b1,monotonic_s=mono,boottime_after_s=b2,feedback_timestamp_meaning='host read receipt, not sensor acquisition onset')
    if gate is not None and recorder.first is None:extra['measurement_start']=dict(m.lab07_start_marker)
    trial=getattr(m,'automatic_trial',None)
    if trial is not None:extra['experimental_inputs']=trial.status(row['time_s'])
    recorder.record({**row,**extra})
