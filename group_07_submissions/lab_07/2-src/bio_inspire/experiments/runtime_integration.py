"""Execute CameraMotor itself with virtual I/O; no live constructor fallback.

One-tick ideal goal-following memory feedback is NOT STS3215 dynamics or
kinematic/vision validation. All output files belong to the supplied run dir.
"""
import contextlib
import io
import gzip
import hashlib
from dataclasses import asdict
import json
import math
from pathlib import Path
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'shared/runtime'))
from physical_button import BufferedInput
from physical_distance import distance_input_kind
from bio_inspire.runtime.camera_motor import CameraMotor
from bio_inspire.runtime.offline_motion_replay import ReplayBus
from .ahm_input_bridge import scenario


class MemoryBus(ReplayBus):
    def __init__(self,profile,clock):
        super().__init__({int(k):v for k,v in profile['origin_raw'].items()})
        self.clock=clock;self.closed=False;self.all_writes=[];self.forbidden=[];self.bounds_violations=0
        self.injected=False;self.in_shutdown=False
        for sid in self.reg:
            p=profile['startup_pid_by_id'][str(sid)]
            self.reg[sid].update({8:1,21:int.from_bytes(bytes((p['p'],p['d'],p['i'])),'little'),55:1})
    def snapshot(self):
        if self.clock.bus_fault_s is not None and self.clock.t>=self.clock.bus_fault_s and not self.injected:
            self.injected=True;raise RuntimeError('Injected memory-bus read failure')
        return [dict(id=i,position_raw=self.pos[i],torque_raw=self.reg[i][40],status_raw=self.reg[i][65],
                     mode=0,speed_raw=0,moving_raw=0,goal_raw=self.reg[i][42],target_speed_raw=self.reg[i][46],
                     acceleration_raw=self.reg[i][41],sampled_monotonic_s=self.clock.t,
                     load_raw=0,current_raw=0,internal_target_raw=self.reg[i][42],voltage_V=7.2,temperature_C=30.)
                for i in range(1,6)]
    def write(self,sid,address,data):
        value=int.from_bytes(data,'little')
        if address not in (40,41,42,46) or address==40 and value!=1:
            self.forbidden.append((sid,address,value));raise RuntimeError('Forbidden memory PID/EEPROM/release')
        if address==42 and not self.windows[sid][0]<=value<=self.windows[sid][1]:self.bounds_violations+=1
        super().write(sid,address,data)
        self.all_writes.append(dict(time_s=self.clock.t,id=sid,address=address,value=value,
                                   phase='cleanup_hold' if self.in_shutdown else 'runtime'))
    def sync_positions(self,goals,cancelled):
        for sid,value in goals.items():
            if cancelled():return dict(status='cancelled')
            self.write(sid,42,int(value).to_bytes(2,'little'))
        return dict(status='synthetic_memory_readback',goals=dict(goals))
    def close(self):self.closed=True


class DigitalPort(BufferedInput):
    def __init__(self,debounce):super().__init__(debounce);self.closed=False
    def close(self):self.closed=True;self.discard_pending()


class DistancePort:
    def __init__(self,clock):self.clock=clock;self.closed=False;self.sample=None;self.update()
    def update(self):
        if self.closed or self.clock.inside(self.clock.tof_stall):return
        frame=self.clock.frame();kind=frame.distance_kind
        raw_status={'range':9,'no_target':4,'unreliable':5,'error':0}
        if kind not in raw_status:raise ValueError('Unsupported virtual distance quality')
        self.sample=dict(distance_cm=None if frame.distance_m is None else frame.distance_m*100.,
                         received_s=self.clock.t,error='synthetic_read_error' if kind=='error' else None,sequence=self.clock.index(),
                         measurement_state=kind,range_status_raw=raw_status[kind])
    def latest(self):return dict(self.sample)
    def wait_first_sample(self):self.require_fresh()
    def require_fresh(self):
        if distance_input_kind(self.sample,self.clock.t)=='fault':raise RuntimeError('Synthetic ToF stale')
    def close(self):self.closed=True


class LedPort:
    state=None
    def normal(self):self.state='normal'
    def interested(self):self.state='interested'
    def happy(self):self.state='happy'
    def sleepy(self):self.state='sleepy'
    def afraid(self):self.state='afraid'
    def angry(self):self.state='angry'
    def close(self):self.state=None


class DeferredWorker:
    def __init__(self,*args,**kw):pass
    def start(self):pass
    def is_alive(self):return False
    def join(self,*args,**kw):pass


class VirtualStop:
    def __init__(self,clock):self.clock=clock;self.flag=False
    def is_set(self):return self.flag
    def set(self):self.flag=True
    def wait(self,timeout=None):self.clock.advance();return self.flag


class VirtualClock:
    def __init__(self,duration,frames,stop_s,camera_stall,tof_stall,bus_fault_s,face_lost):
        self.t=0.;self.duration=duration;self.frames=frames;self.motor=None;self.trace=[]
        self.stop_s=stop_s;self.camera_stall=camera_stall;self.tof_stall=tof_stall
        self.bus_fault_s=bus_fault_s;self.face_lost=face_lost;self.stop_sent=False;self.next_sample=0.
    def index(self):return min(len(self.frames)-1,int((self.t+1e-9)/.05))
    def frame(self):return self.frames[self.index()]
    def inside(self,interval):return interval is not None and interval[0]<=self.t<interval[1]
    def publish(self):
        m=self.motor
        if m is None:return
        m.bus.advance(self.t)
        while self.next_sample<=self.t+1e-9:
            source=self.frames[min(len(self.frames)-1,int((self.next_sample+1e-9)/.05))]
            for name in ('button','touch'):
                port=getattr(m,'physical_'+name,None)
                if port is not None and not port.closed:port.sample(getattr(source,name),self.next_sample)
            self.next_sample+=.02
        if m.physical_distance is not None:m.physical_distance.update()
        if not self.inside(self.camera_stall):
            lost=self.inside(self.face_lost);xy=(.08*math.sin(self.t*.3),.08*math.sin(self.t*.2))
            obs=dict(box=None if lost else (.3,.2,.3,.5),status='LOST' if lost else 'TRACKING',captured_s=self.t,source_id='virtual_face_'+str(self.index()),error_xy=xy)
            m.latest_result=dict(state=m.behavior_trial if m.behavior_trial in ('normal','interested','happy','afraid','sleepy','angry') else 'normal',
                observation=obs,intent=dict(mode='SEARCH' if lost else 'FOLLOW',error_xy=xy))
            m.last_frame=self.t
        if self.stop_s is not None and self.t>=self.stop_s and not self.stop_sent:
            m.keys.append(ord('h'));self.stop_sent=True
    def advance(self):
        m=self.motor;c=m.controller
        fsm=m.automatic_fsm.snapshot()
        fsm={k:fsm.get(k) for k in ('state','entry_s','timer_ready','last_dispatch','angry_near_deferred','source_fault')}
        rhythm=getattr(m,'rhythm_view_cache',{})
        rhythm={k:rhythm.get(k) for k in ('o1','o2','phi','dt_s','time_scale','updates','envelope','state_ahm','normal_ahm','small_happy','active','command_offsets_deg')}
        self.trace.append(dict(time_s=self.t,state=c.state,behavior=m.behavior_trial,operator_stopped=m.operator_stopped,
            face_status=(m.latest_result or {}).get('observation',{}).get('status'),
            pitch_search_status=getattr(m,'pitch_search_status',None),follow_enabled=m.follow_enabled,
            happy_head_wake_goal=getattr(m,'happy_head_wake_goal',None),
            fsm_active_since_s=getattr(getattr(m.automatic_fsm,'fsm',None),'active_since',None),
            error=c.last_error,route_phase=getattr(getattr(c,'pose_route',None),'phase',None),
            fsm=fsm,rhythm=rhythm,
            rows=[dict(r) for r in c.last_rows],writes=[dict(w) for w in m.bus.writes]))
        self.t=round(self.t+.05,10)
        if self.t>=self.duration:m.bus.in_shutdown=True;m.stopping.set();return
        self.publish()


def run_runtime(out,condition='C1',duration_s=600.,seed=41,stop_s=None,camera_stall=None,tof_stall=None,bus_fault_s=None,face_lost=None,frames_override=None,initial_pose=None,initial_torque=0,profile_path=None,park_only=False):
    if condition not in ('C0','C1') or type(duration_s) not in (int,float) or not 0<duration_s<=630:
        raise ValueError('Bounded C0/C1 virtual runtime required')
    out=Path(out).resolve()
    if not out.is_relative_to(ROOT/'bio_inspire/results'):raise ValueError('Virtual evidence must stay in project results')
    out.mkdir(parents=True,exist_ok=True)
    if any(out.iterdir()):raise FileExistsError('Refuse to overwrite virtual runtime evidence')
    source_profile=(ROOT/'bio_inspire/hardware/afraid_pose_trial.json') if profile_path is None else Path(profile_path).resolve()
    if not source_profile.is_relative_to(ROOT):raise ValueError('Virtual source profile must stay in project')
    profile=json.loads(source_profile.read_text(encoding='utf-8'))
    profile.update(normal_ahm_condition=condition,ahm_scope='all_states',
                   status='PC_virtual_IO_only_not_an_approved_hardware_profile')
    path=out/'virtual_profile.json';path.write_text(json.dumps(profile),encoding='utf-8')
    frames=scenario(seed) if frames_override is None else frames_override
    if not math.ceil(duration_s/.05)<=len(frames)<=12600:raise ValueError('Input frames must cover the bounded virtual run')
    recorded_frames=[asdict(f) for f in frames[:math.ceil(duration_s/.05)]]
    input_bytes=json.dumps(recorded_frames,sort_keys=True,allow_nan=False).encode('utf-8')
    with gzip.open(out/'input_frames.json.gz','wb') as stream:stream.write(input_bytes)
    input_hash=hashlib.sha256(input_bytes).hexdigest()
    run_config=dict(condition=condition,duration_s=duration_s,seed=seed,stop_s=stop_s,
        camera_stall=camera_stall,tof_stall=tof_stall,bus_fault_s=bus_fault_s,face_lost=face_lost,
        initial_pose=initial_pose,initial_torque=initial_torque,input_sha256=input_hash,
        input_kind='synthetic source frames; held between20Hz frames for50Hz GPIO sampling',
        baseline_profile_sha256=hashlib.sha256((ROOT/'bio_inspire/hardware/afraid_pose_trial.json').read_bytes()).hexdigest(),
        source_profile=str(source_profile.relative_to(ROOT)),source_profile_sha256=hashlib.sha256(source_profile.read_bytes()).hexdigest())
    (out/'run_config.json').write_text(json.dumps(run_config,indent=2)+'\n',encoding='utf-8')
    clock=VirtualClock(duration_s,frames,stop_s,camera_stall,tof_stall,bus_fault_s,face_lost)
    bus=MemoryBus(profile,clock)
    if initial_torque not in (0,1):raise ValueError('Expected virtual torque0/1')
    if initial_pose is not None:
        if set(initial_pose)!=set(range(1,6)) or any(type(v)is not int or not 0<=v<=4095 for v in initial_pose.values()):
            raise ValueError('Expected five virtual encoder positions')
        bus.pos=dict(initial_pose)
        for sid,v in initial_pose.items():bus.reg[sid][42]=v
    for sid in bus.reg:bus.reg[sid][40]=initial_torque
    with contextlib.ExitStack() as stack, contextlib.redirect_stdout(io.StringIO()) as stdout:
        stack.enter_context(patch('bio_inspire.runtime.camera_motor.open_bus',return_value=bus))
        stack.enter_context(patch('bio_inspire.runtime.camera_motor.CameraMotor.now',staticmethod(lambda:clock.t)))
        thread_probe=stack.enter_context(patch('threading.Thread.start',side_effect=AssertionError('Real thread start forbidden in virtual replay')))
        stack.enter_context(patch('threading.Thread',DeferredWorker))
        stack.enter_context(patch('physical_button.PhysicalButton',DigitalPort))
        stack.enter_context(patch('physical_touch.PhysicalTouch',DigitalPort))
        stack.enter_context(patch('physical_distance.PhysicalDistance',lambda:DistancePort(clock)))
        stack.enter_context(patch('led_ring.LedRing',LedPort))
        motor=CameraMotor(path,operator_start=True,**({'park_only':True} if park_only else {}));clock.motor=motor;motor.stopping=VirtualStop(clock)
        clock.publish();motor._run()
    (out/'runtime.log').write_text(stdout.getvalue(),encoding='utf-8')
    result=dict(scope='Actual CameraMotor loop with virtual I/O and ideal one-tick memory feedback; not hardware/vision/dynamics proof',
        condition=condition,duration_s=duration_s,trace=clock.trace,
        input_sha256=input_hash,
        behaviors=sorted({r['behavior'] for r in clock.trace}),controller_states=sorted({r['state'] for r in clock.trace}),
        cleanup_confirmed=motor.cleanup_confirmed,bus_closed=bus.closed,real_threads_started=thread_probe.call_count,
        worker_execution='deferred worker invoked synchronously; real Thread.start trapped',
        operator_start_preflight=True,
        forbidden_writes=bus.forbidden,bounds_violations=bus.bounds_violations,
        cleanup_hold_writes=[w for w in bus.all_writes if w['phase']=='cleanup_hold'],
        position_writes_after_stop=[w for w in bus.all_writes if stop_s is not None and w['time_s']>stop_s+.05+1e-9 and w['address']==42 and w['phase']=='runtime'])
    with gzip.open(out/'result.json.gz','wt',encoding='utf-8') as stream:json.dump(result,stream,allow_nan=False)
    return result


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--condition',choices=('C0','C1'),default='C1')
    parser.add_argument('--duration',type=float)
    parser.add_argument('--case',choices=('normal','stop','camera_stall','tof_stale','bus_fault','face_lost'),default='normal')
    args=parser.parse_args()
    cases=dict(normal={},stop=dict(stop_s=3.),camera_stall=dict(camera_stall=(3.,4.)),
               tof_stale=dict(tof_stall=(3.,3.5)),bus_fault=dict(bus_fault_s=3.),face_lost=dict(face_lost=(3.,4.2)))
    duration=args.duration if args.duration is not None else (600. if args.case=='normal' else 8.)
    result=run_runtime(args.out,condition=args.condition,duration_s=duration,**cases[args.case])
    print(json.dumps({k:v for k,v in result.items() if k not in ('trace','cleanup_hold_writes','position_writes_after_stop')},ensure_ascii=False))
