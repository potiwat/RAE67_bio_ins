"""Passive native feedback capture. No resistance decisions or motor writes."""
import csv,json,time
from pathlib import Path
from normal_gaze_motor import decode_state

STATES=('normal','interested','happy','angry','afraid','sleepy')
FIELDS=('time_s','id','behavior','fsm_state','controller_state','route_phase','fold_phase','operator_stopped','goal_raw','internal_target_raw','position_raw','goal_error_ticks','internal_error_ticks','target_speed_raw','acceleration_raw','torque_limit_raw','speed_raw','speed_signed_raw','load_raw','load_signed_raw','current_raw','voltage_V','temperature_C','mode','torque_raw','status_raw','moving_raw','sample_interval_s','complete_feedback','block_hex')

class Recorder:
 def __init__(self,output,clock=time.monotonic):
  self.clock=clock;self.out=Path(output)/('run_'+str(time.time_ns()));self.out.mkdir(parents=True)
  self.motor=None;self.closed=False;self.rows=0;self.last={};self.first=None;self.last_time=None;self.last_flush=clock();self.last_context=None
  self.pid_before={};self.pid_after=None;self.native_before={};self.native_after=None
  self.coverage={state:{i:dict(n=0,seconds=0.,last=None) for i in range(1,6)} for state in STATES}
  self.raw=(self.out/'feedback.jsonl').open('w',encoding='utf-8');self.events=(self.out/'events.jsonl').open('w',encoding='utf-8');self.csvfile=(self.out/'JOINT_FEEDBACK.csv').open('w',newline='',encoding='utf-8-sig');self.csv=csv.DictWriter(self.csvfile,fieldnames=FIELDS);self.csv.writeheader()
 def event(self,name,**values):
  self.events.write(json.dumps(dict(event=name,time_s=self.clock(),**values),ensure_ascii=False)+'\n');self.events.flush()
 def context(self):
  m=self.motor;c=None if m is None else m.controller;auto=None if m is None else getattr(m,'automatic_fsm',None);fsm=None if auto is None else getattr(auto,'fsm',None)
  return dict(behavior='startup' if m is None else m.behavior_trial,fsm_state=None if fsm is None else fsm.state,controller_state='INIT' if c is None else c.state,route_phase=getattr(getattr(c,'pose_route',None),'phase',None),fold_phase=(getattr(c,'sleepy_native_fold',None) or {}).get('phase'),operator_stopped=False if m is None else getattr(m,'operator_stopped',False))
 def sample(self,sid,address,count,data,stamp=None):
  if self.closed or address!=33 or count not in (34,38):return
  r=decode_state(sid,data);t=r['sampled_monotonic_s'] if stamp is None else stamp;r['sampled_monotonic_s']=t
  ctx=self.context();previous=self.last.get(sid);dt=None if previous is None else t-previous;self.last[sid]=t
  v=r['speed_raw'];load=r['load_raw'];internal=r.get('internal_target_raw')
  values=dict(time_s=t,id=sid,**ctx,**{k:r.get(k) for k in ('goal_raw','internal_target_raw','position_raw','target_speed_raw','acceleration_raw','speed_raw','load_raw','current_raw','voltage_V','temperature_C','mode','torque_raw','status_raw','moving_raw')},torque_limit_raw=int.from_bytes(data[15:17],'little'),goal_error_ticks=r['goal_raw']-r['position_raw'],internal_error_ticks=None if internal is None else internal-r['position_raw'],speed_signed_raw=-(v&32767) if v&32768 else v,load_signed_raw=-(load&1023) if load&1024 else load&1023,sample_interval_s=dt,complete_feedback=count==38,block_hex=data.hex())
  self.raw.write(json.dumps(values,ensure_ascii=False)+'\n');self.csv.writerow(values);self.rows+=1;self.first=t if self.first is None else self.first;self.last_time=t
  identity=tuple(ctx.items())
  if identity!=self.last_context:self.event('CONTEXT',**ctx);self.last_context=identity
  state=ctx['behavior'];valid=(count==38 and state in STATES and ctx['controller_state'] in ('READY','FOLLOWING') and not ctx['operator_stopped'] and r['mode']==0 and r['torque_raw']==1 and r['status_raw']==0 and (state!='sleepy' or ctx['fold_phase']=='breathing'))
  if valid:
   for other,bins in self.coverage.items():
    if other!=state:bins[sid]['last']=None
   q=self.coverage[state][sid];old=q['last'];q['n']+=1
   if old is not None and 0<t-old<=.25:q['seconds']+=t-old
   q['last']=t
  # Coverage never fills time through faults, transitions or missing feedback.
  else:
   for bins in self.coverage.values():bins[sid]['last']=None
  now=self.clock()
  if now-self.last_flush>=1.:self.raw.flush();self.csvfile.flush();self.last_flush=now
 def status(self):
  done={state:all(q['n']>=30 and q['seconds']>=3. for q in bins.values()) for state,bins in self.coverage.items()}
  ready=sum(done.values());need=next((s for s in STATES if not done[s]),None);ctx=self.context()
  return dict(complete=ready==6,states_done=done,ready_states=ready,next_state=need,rows=self.rows,fold_phase=ctx['fold_phase'],output=str(self.out))
 def close(self,error=None):
  if self.closed:return
  status=self.status();self.closed=True
  for f in (self.raw,self.csvfile,self.events):f.flush();f.close()
  (self.out/'summary.json').write_text(json.dumps(dict(**status,duration_s=None if self.first is None else self.last_time-self.first,coverage=self.coverage,pid_before=self.pid_before,pid_after=self.pid_after,pid_unchanged=None if self.pid_after is None else self.pid_before==self.pid_after,native_before=self.native_before,native_after=self.native_after,error=error,observer_only=True,resistance_protection_enabled=False,units=dict(position='ticks',current='native register raw; not contact force',load='signed PWM raw; not calibrated torque',speed='native register raw; phase-dependent')),indent=2),encoding='utf-8')

def attach_bus(bus,output,pid_before=None):
 recorder=Recorder(output);read=bus.read;write=bus.write;close=bus.close
 recorder.original_read=read
 try:
  recorder.pid_before=pid_before if pid_before is not None else {str(i):list(read(i,21,3)) for i in range(1,6)}
  if pid_before is None:recorder.native_before={str(i):read(i,33,38).hex() for i in range(1,6)}
 except BaseException as error:recorder.close(repr(error));raise
 def observed_read(sid,address,count):
  data=read(sid,address,count);recorder.sample(sid,address,count,data);return data
 def guarded_write(sid,address,data):
  if address not in (40,41,42,46):raise ValueError('Baseline forbids PID/EEPROM/cap and unreviewed writes')
  result=write(sid,address,data);recorder.event('WRITE',id=sid,address=address,data_hex=data.hex(),behavior=recorder.context()['behavior']);return result
 def observed_close():
  error=None
  try:
   recorder.pid_after={str(i):list(read(i,21,3)) for i in range(1,6)}
   recorder.native_after={str(i):read(i,33,38).hex() for i in range(1,6)}
   if recorder.pid_after!=recorder.pid_before:raise RuntimeError('PID differs; no automatic correction')
  except Exception as e:error=repr(e)
  finally:
   try:recorder.close(error)
   finally:close()
  if error:raise RuntimeError(error)
 bus.read=observed_read;bus.write=guarded_write;bus.close=observed_close;bus.all_joint_baseline=recorder
 return recorder
