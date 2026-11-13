"""Bounded recorded-input C0/C1 pilot in Normal, under the existing UART owner.

Reference AHM is fixed-grid Lab05 Euler. Physical CPG is the separately
approved .10..13 / time_scale .5 adaptation, not the research .20..40 run.
No devices, threads, ROS publishers or low-level actuator writes here.
"""
import hashlib
import json
import math
from pathlib import Path


def motion_experiment(config):
    flag=config.get('normal_motion_experiment')
    if flag is None:return False
    if (flag is not True or config.get('lab07_recording_seconds')!=180
            or config.get('lab07_start_button_presses')!=5
            or not isinstance(config.get('normal_measurement_source'),str)
            or config.get('cpg_normal_amplitude_deg')!=2.
            or config.get('cpg_time_scale')!=.5):
        raise ValueError('Normal motion requires explicit180s/five buttons/current2deg and .5 time scale')
    return True


class ScheduledAHM:
    def __init__(self,fixture,condition):
        rows=fixture.get('samples')
        if (condition not in ('C0','C1') or fixture.get('dt_s')!=.05
                or fixture.get('stimulus_policy')!='near_only_v2'
                or not isinstance(rows,list) or not (len(rows)==1000 or len(rows)==3600 and fixture.get('schema')=='normal_motion_recorded_input_v1' and fixture.get('duration_s')==180)):
            raise ValueError('Expected paired1000-sample50s recorded-input reference')
        self.duration_s=len(rows)*.05
        previous=-math.inf
        for row in rows:
            value=row.get('stimulus');stamp=row.get('source_s');sid=row.get('source_id')
            if (type(value) not in (int,float) or value not in (0.,1.)
                    or type(stamp) not in (int,float) or not math.isfinite(stamp) or stamp<=previous
                    or not isinstance(sid,str) or not 1<=len(sid)<=120):
                raise ValueError('Invalid recorded-input reference')
            previous=stamp
        self.fixture=fixture;self.values=[r['stimulus'] for r in rows]
        self.condition=condition;self.started=None;self.last_time=None;self.last_index=None;self.skipped=0
        self.h_values=[];h=0.
        for s in self.values:
            self.h_values.append(h)
            h=max(0.,min(1.,h+.05*(.8*s-.6*h-.2*h)))

    def start(self,now):
        if self.started is not None or type(now) not in (int,float) or not math.isfinite(now):
            raise ValueError('Measurement can start once at a finite clock')
        self.started=now

    def step(self,now,stimulus=None,enabled=True):
        if (type(now) not in (int,float) or not math.isfinite(now)
                or self.last_time is not None and now<self.last_time):raise ValueError('Invalid replay clock')
        self.last_time=now
        elapsed=0. if self.started is None else max(0.,now-self.started)
        index=min(len(self.values)-1,int((elapsed+1e-9)/.05))
        active=enabled and self.started is not None and elapsed<self.duration_s
        if active and self.last_index is not None:self.skipped+=max(0,index-self.last_index-1)
        if active:self.last_index=index
        s=self.values[index] if active else 0.;h=self.h_values[index] if active else 0.
        r=h if self.condition=='C1' else s
        reason='disabled' if not enabled else 'waiting' if self.started is None else 'complete' if elapsed>=self.duration_s else 'tracking'
        return dict(condition=self.condition,stimulus=s,h=h,r_used=r,phi=.1+.03*r,reason=reason,
            schedule_index=index if active else None,skipped_schedule_updates=self.skipped,
            reference_source_id=self.fixture['samples'][index]['source_id'] if active else None,
            elapsed_s=elapsed,duration_s=self.duration_s,hormone_dt_s=.05,
            mapping='hardware_normal_phi_010_013',stimulus_policy='near_only_v2',
            clock='recorded_reference_50ms_selected_by_elapsed_owner_time')


class NormalMeasurement:
    def __init__(self,fixture,condition,path):
        self.replay=ScheduledAHM(fixture,condition);self.path=path
        self.state='waiting';self.reason=None;self.trace=[];self.saved=False;self.last_callback=None
        self.streamed=self.replay.duration_s==180.
        self.fixture_sha256=None

    @classmethod
    def from_profile(cls,config,profile):
        extended=motion_experiment(config)
        source=config.get('normal_measurement_source')
        if source is None:return None
        root=Path(__file__).resolve().parents[2]
        if not isinstance(source,str):raise ValueError('Measurement source must be in project')
        path=(root/source).resolve()
        if not path.is_relative_to(root) or not path.is_file() or path.stat().st_size>(2000000 if extended else 512000):
            raise ValueError('Invalid bounded measurement source')
        data=path.read_bytes()
        if hashlib.sha256(data).hexdigest()!=config.get('normal_measurement_source_sha256'):
            raise ValueError('Measurement source hash differs')
        fixture=json.loads(data)
        if (len(fixture.get('samples',[]))==3600)!=extended:raise ValueError('180s fixture must use explicit motion profile')
        if extended:
            import datetime,uuid
            out=root/'bio_inspire/results/normal_motion_measurements'/(datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8])
            output=out/'measurement.json'
        else:output=Path(profile).with_name('last_normal_measurement_'+config['normal_ahm_condition']+'.json')
        result=cls(fixture,config.get('normal_ahm_condition'),output);result.fixture_sha256=hashlib.sha256(data).hexdigest()
        return result

    def begin(self,m,now):
        if self.state!='waiting' or self.replay.started is not None:raise RuntimeError('Normal measurement starts once')
        from bio_inspire.runtime.body_rhythm import BodyRhythm
        driver=m.rhythm_driver.breathing
        driver.rhythm=BodyRhythm(amplitude_deg=2.,phi=.1,time_scale=.5)
        driver.rhythm.active_joint_ids=(2,3)
        driver.mode=None;driver.last_sent={}
        m.rhythm_driver.normal_ahm=self.replay
        self.replay.start(now);self.state='running'
        print('NORMAL_MEASUREMENT_START',self.replay.condition,self.replay.duration_s,flush=True)

    def abort(self,m,reason):
        if self.state=='aborted':return
        self.state='aborted';self.reason=reason
        m._key(ord('h'))  # Existing operator hold; no torque release/re-arm.
        self.close(reason)

    def service(self,m,now):
        from bio_inspire.runtime.distance_behavior import poll_distance
        if self.state=='aborted':return
        if (getattr(m,'operator_stopped',False) or m.stopping.is_set() or m.urgent_stop.is_set()
                or m.controller.state in ('FAULT','STOPPED','WAIT_TOF')):
            self.abort(m,'operator_or_controller_hold');return
        poll_distance(m,now,dispatch=False)
        now=max(now,m.now())
        if m.controller.state in ('FAULT','STOPPED','WAIT_TOF') or m.distance_gate.near:
            self.abort(m,'live_near_or_distance_fault');return
        # Consume/discard original sampler queues without dispatching emotions.
        # Sampler failures still propagate to the existing fault handler.
        for name in ('physical_button','physical_touch'):
            source=getattr(m,name,None)
            if source is not None:source.drain_events(now)
        if self.state=='complete':return
        if self.state=='waiting':
            if m.controller.state not in ('READY','FOLLOWING') or m.behavior_trial!='normal':return
            if self.streamed:raise RuntimeError('180s measurement requires five-button boundary')
            self.begin(m,now)
        if self.last_callback is not None and now-self.last_callback>1.:
            self.abort(m,'owner_gap_over_1s');return
        self.last_callback=now
        if not self.streamed and now-self.replay.started>=self.replay.duration_s:
            self.state='complete';self.reason='completed_50s'
            print('NORMAL_MEASUREMENT_COMPLETE',self.replay.condition,'Q to close',flush=True)

    def record(self,m,now):
        if self.saved or self.state not in ('running','complete'):return
        if (m.controller.state not in ('READY','FOLLOWING') or getattr(m,'behavior_trial',None)!='normal'
                or getattr(m,'operator_stopped',False)
                or any(e is not None and e.is_set() for e in
                       (getattr(m,'stopping',None),getattr(m,'urgent_stop',None)))):
            self.abort(m,'output_cycle_not_healthy');return
        if self.streamed:
            recorder=getattr(m,'lab07_recorder',None)
            if recorder is None:raise RuntimeError('180s measurement requires disk recorder')
            if recorder.error or recorder.dropped or getattr(recorder,'invalid',False):
                self.abort(m,'disk_recording_failure');return
            if recorder.end_seen:
                self.state='complete';self.reason='completed_180s'
                self.close(self.reason)
            return
        if len(self.trace)>=1600:
            self.abort(m,'bounded_trace_capacity');return
        rhythm=getattr(m,'rhythm_view_cache',{})
        driver=getattr(getattr(m,'rhythm_driver',None),'breathing',None)
        self.trace.append(dict(time_s=now,elapsed_s=now-self.replay.started,
            controller_state=m.controller.state,behavior=getattr(m,'behavior_trial',None),
            live_near=bool(getattr(getattr(m,'distance_gate',None),'near',False)),
            rhythm=dict(rhythm),command_goals=dict(getattr(driver,'last_sent',{})),
            rows=[dict(r) for r in m.controller.last_rows]))
        if self.state=='complete':self.close('completed_50s')

    def close(self,reason):
        if self.saved:return
        self.reason=self.reason or reason
        data=dict(condition=self.replay.condition,state=self.state,reason=self.reason,
                  completed=self.state=='complete',started_s=self.replay.started,
                  nominal_duration_s=self.replay.duration_s,
                  nominal_input=(dict(source_sha256=self.fixture_sha256,
                      schema=self.replay.fixture.get('schema'),
                      raw_source=self.replay.fixture.get('raw_source'),
                      raw_sha256=self.replay.fixture.get('raw_sha256'))
                      if self.streamed else self.replay.fixture),
                  trace_storage='disk trace.jsonl' if self.streamed else 'embedded trace',
                  common_initial_o1=-.026965330782974153,common_initial_o2=-.5608626776309884,
                  cpg_dt_s=.05,cpg_time_scale=.5,amplitude_deg_limit=2.,
                  skipped_schedule_updates=self.replay.skipped,trace=self.trace,
                  timing_limit='same nominal reference; actual owner times/skipped indices logged, not every50ms output guaranteed')
        if self.path is not None:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            temporary=self.path.with_suffix('.tmp')
            temporary.write_text(json.dumps(data,allow_nan=False)+'\n',encoding='utf-8');temporary.replace(self.path)
        self.saved=True

    def worker_failed(self):
        if not self.saved:
            self.state='aborted';self.reason='worker_exception'
