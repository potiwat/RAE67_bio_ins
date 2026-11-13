"""Experimental ID1 resistance owner, serviced on the existing UART worker."""
import json,time,traceback
from pathlib import Path
from normal_gaze_motor import decode_state
from write_ack import receive_write_ack
from shared.experiments.resistance_id1_20261109.capped_trial import EarlyGuard
from shared.experiments.resistance_id1_20261109.foam_recovery import Recovery
from shared.experiments.resistance_id1_20261109.foam_trial import HandoffAssist
from shared.experiments.resistance_id1_20261109.damping_brake import _write,restore_position_hold
from .brake import brake_id1
from .adapter import SafetyInterrupt

class Owner:
 def __init__(self,m,output,clock=time.monotonic):
  self.m=m;self.b=m.bus;self.a=self.b.id1_safety_adapter;self.a.owner=self;self.clock=clock
  self.phase='MONITOR';self.reason='Waiting for Normal setup; safety arms before next cycle';self.guard=EarlyGuard();self.armed=False;self.recovery=None;self.assist=None;self.old_goal=None;self.test=None;self.completed_test=False
  self.out=Path(output)/('run_'+str(time.time_ns()));self.out.mkdir(parents=True)
  self.log=(self.out/'trace.jsonl').open('w');self.events=[];self.closed=False;self.last_rows=[]
  self.pid_before={str(i):list(self.b.read(i,21,3)) for i in range(1,6)}
  self.qualification_verified=False
  marker=Path(__file__).with_name('qualification_verified.json')
  if marker.exists():
   verified=json.loads(marker.read_text());manifest=json.loads(Path(__file__).with_name('manifest.json').read_text())
   self.qualification_verified=verified.get('validated') is True and verified.get('qualification_key')==manifest['qualification_key']
  self.event('READY',profile=m.lab07_profile_path)
 def event(self,name,**values):
  r=dict(event=name,time_s=self.clock(),**values);self.events.append(r);self.log.write(json.dumps(r)+'\n');self.log.flush()
 def row(self):
  b=self.b.read(1,33,38);r=decode_state(1,b);r['cap']=int.from_bytes(b[15:17],'little');return r
 def status(self):return dict(phase=self.phase,reason=self.reason,qualification_complete=self.completed_test or self.qualification_verified,log_directory=str(self.out))
 def damp(self,reason):
  b=self.b.read(1,33,38)
  if b[0]!=0 or b[7] not in (1,2) or b[32]!=0 or int.from_bytes(b[15:17],'little')!=160:raise RuntimeError('Damping health/cap unconfirmed')
  _write(self.b,40,b'\2',receive_write_ack,self.clock)
  if self.b.read(1,33,38)[7]!=2:raise RuntimeError('Damping readback mismatch')
  self.event('DAMPING',reason=reason)
 def brake(self):
  r=self.row();v=r['speed_raw']&32767
  if v>600:
   self.damp('actual speed beyond qualified pulse range');raise RuntimeError('ID1 speed >600raw: stopped; active pulse not qualified')
  report=brake_id1(self.b,pulse=True,run_acc=r['acceleration_raw'],run_speed=r['target_speed_raw'])
  self.event('BRAKE',report=report);return report
 def freeze(self,reason):
  self.a.blocked=True;self.m.follow_enabled=False
  self.m._hold(reason,all_axes=True)
  if self.m.controller.state=='FAULT':raise RuntimeError('Body hold unconfirmed')
  self.m.pending_behavior=None;self.m.pending_happy_from_touch=False;self.m.interested_roll_due=None
  f=getattr(self.m,'automatic_fsm',None)
  if f is not None:f.discard_inputs(self.m,'id1_safety_pause')
 def fail(self,error):
  self.a.blocked=True;self.phase='FAULT';self.reason=str(error)
  self.event('FAULT',error=repr(error),traceback=traceback.format_exc())
  try:self.damp('fault');self.freeze('ID1 safety fault')
  except Exception as e:self.event('FAULT_HOLD_UNCONFIRMED',error=repr(e))
  self.m.controller.state='FAULT';self.m.controller.last_error='ID1 safety: '+str(error)
 def manual_stop(self):
  self.a.blocked=True;self.phase='MANUAL';self.reason='Stopped by operator; Start reconnects';self.recovery=None;self.test=None
  try:self.brake()
  except Exception as e:
   try:self.damp('operator stop')
   except Exception as d:self.fail(d)
  self.event('OPERATOR_STOP')
 def observe(self):
  if self.phase!='MONITOR':return True
  c=self.m.controller
  if c.state=='FAULT':
   self.fail('Runtime fault: '+str(c.last_error));return True
  if c.state=='STOPPED':return False
  if c.state=='NORMAL_STARTUP':return False
  if not self.armed:return False
  try:
   self.poll();return False
  except SafetyInterrupt as signal:self.handle_interrupt(signal);return True
  except Exception as e:self.fail(e);return True
 def poll(self):
  # Cooperative polling on the SAME UART owner, including long state/profile
  # transitions. Never wait for a whole five-joint behavior cycle to finish.
  stopping=getattr(self.m,'stopping',None)
  if stopping is not None and stopping.is_set():self.a.blocked=True;return
  if self.phase!='MONITOR' or not self.armed:return
  now=self.clock();previous=self.guard.last_stamp
  if previous is not None and now-previous<.04:return
  try:
   with self.a.internal():r=self.row()
   now=self.clock();g=self.guard.update(r,now)
   self.log.write(json.dumps(dict(phase=self.phase,behavior=self.m.behavior_trial,row=r,poll_interval_s=None if previous is None else r['sampled_monotonic_s']-previous))+'\n');self.log.flush()
   if g['state']=='FAULT_HOLD':raise SafetyInterrupt('fault',r,g['reason'])
   if g['trip']:raise SafetyInterrupt('resistance',r,g['reason'])
  except SafetyInterrupt:raise
  except Exception as e:raise SafetyInterrupt('fault',reason='ID1 feedback read failed: '+repr(e)) from e
 def handle_interrupt(self,signal):
  if signal.kind!='resistance':self.fail(signal.reason or 'Unknown safety interruption');return
  try:
   r=signal.row;self.old_goal=r['goal_raw'];sign=-1 if r['speed_raw']&32768 else 1
   if not r['speed_raw']:sign=1 if r['goal_raw']>=r['position_raw'] else -1
   self.phase='BRAKING';self.a.blocked=True
   self.event('RESISTANCE',behavior=self.m.behavior_trial,row=r)
   with self.a.internal():self.brake()
   self.freeze('ID1 resistance pause')
   self.recovery=Recovery(2347 if sign>0 else 1691,native_probe=True,rest_s=.5);self.recovery.pause(self.clock(),new_contact=True)
   self.phase='RECOVERY';self.reason='Remove foam; limited gentle probe follows'
  except Exception as e:self.fail(e)
 def arm_if_ready(self):
  # NORMAL_READY is raised inside controller.tick, before the runtime performs
  # its one-time awake/profile setup. Establish the watchdog baseline only
  # after that work, from an actual new UART read, never a retimestamped row.
  if self.phase!='MONITOR' or self.armed:return False
  if self.m.controller.state not in ('READY','FOLLOWING'):return False
  try:
   with self.a.internal():r=self.row()
   now=self.clock();g=self.guard.update(r,now)
   if g['state']=='FAULT_HOLD':raise RuntimeError(g['reason'])
   self.armed=True;self.reason='ID1 monitoring; V = open-path1000/8 test'
   self.event('MONITOR_ARMED',row=r,after_initial_profile_setup=True);return False
  except Exception as e:self.fail(e);return True
 def tof_allows(self):
  from physical_distance import distance_input_kind
  source=getattr(self.m,'physical_distance',None)
  if source is None:return True
  sample=source.latest();now=self.m.now();kind=distance_input_kind(sample,now)
  self.m.distance_gate.step(sample,now);self.m.distance_view=dict(sample or {},near=self.m.distance_gate.near)
  return kind!='fault' and not self.m.distance_gate.near
 def return_normal(self):
  with self.a.internal():
   self.m.controller.last_rows=self.b.snapshot()
  self.a.blocked=False;self.phase='MONITOR';self.guard=EarlyGuard();self.armed=False;self.assist=None;self.recovery=None
  self.m.controller.last_error='';self.m.operator_stopped=False;self.m.held=True
  auto=getattr(self.m,'automatic_fsm',None)
  if auto is not None:auto.discard_inputs(self.m,'id1_safety_clear');auto.fsm=None;auto.applied='normal';auto.faulted=False
  from bio_inspire.runtime.three_state_behavior import handle_state_key
  handle_state_key(self.m,ord('n'));self.reason='ID1 clear: returning Normal';self.event('RESUME_NORMAL')
 def request_test(self):
  self.event('V_REQUEST',phase=self.phase,behavior=self.m.behavior_trial,controller_state=self.m.controller.state)
  if self.phase!='MONITOR' or self.m.controller.state not in ('READY','FOLLOWING') or self.m.behavior_trial!='normal':
   self.reason='V test: first wait for Normal';self.event('V_NOT_STARTED',reason=self.reason);return
  try:
   r=self.row()
   if r['speed_raw'] or r['moving_raw']:
    self.reason='V test: wait until ID1 stops, then press V';self.event('V_NOT_STARTED',reason=self.reason);return
   if not 1900<=r['position_raw']<=2100:
    self.reason='V test: Stop then Start to center base before test';self.event('V_NOT_STARTED',reason=self.reason);return
   self.a.blocked=True;self.freeze('open-path1000/8 test');self.test=dict(case=0,records=[],began=self.clock())
   self.start_test_case()
  except Exception as e:self.fail(e)
 def start_test_case(self):
  with self.a.internal():restore_position_hold(self.b) if self.b.read(1,33,38)[7]==2 else None
  r=self.row();direction=1 if self.test['case']==0 else -1;target=r['position_raw']+direction*170
  lo,hi=self.b.windows[1]
  if not max(1691,lo)<=target<=min(2347,hi):raise RuntimeError('Insufficient open-path test space; no motion')
  data=b'\10'+target.to_bytes(2,'little')+b'\0\0'+(1000).to_bytes(2,'little')
  _write(self.b,41,data,receive_write_ack,self.clock)
  if self.b.read(1,33,38)[8:15]!=data:raise RuntimeError('1000/8 test profile readback mismatch')
  self.test.update(start=r['position_raw'],direction=direction,target=target,case_began=self.clock(),stable_since=None);self.guard=EarlyGuard()
  self.phase='TEST_RUN';self.reason='OPEN PATH ONLY:1000/8 brake test '+str(self.test['case']+1)+'/2';self.event('TEST_RUN',case=self.test['case'],target=target)
 def service(self):
  if self.phase=='MONITOR':return False
  if self.phase in ('FAULT','MANUAL','TEST_DONE'):return True
  try:
   self.m.controller.last_rows=self.b.snapshot();self.last_rows=self.m.controller.last_rows
   for r in self.last_rows:
    if r['mode'] or r['status_raw'] or r['torque_raw'] not in ((1,2) if r['id']==1 else (1,)):raise RuntimeError('Safety pause: motor health fault')
   r=self.row();now=self.clock();self.log.write(json.dumps(dict(phase=self.phase,row=r))+'\n');self.log.flush()
   if not self.tof_allows():
    if self.phase=='RECOVERY':self.recovery.pause(now)
    else:raise RuntimeError('ToF blocks test/resume; no auto restart')
    self.reason='Safety paused: clear ToF / wait fresh distance';return True
   if self.phase=='TEST_RUN':
    g=self.guard.update(r,now)
    if g['state']=='FAULT_HOLD' or g['trip']:self.brake();raise RuntimeError('Open-path test interrupted by feedback/resistance; inspect before restarting')
    if now-self.test['case_began']>3.:raise RuntimeError('1000/8 brake test did not reach test point')
    if abs(r['position_raw']-self.test['start'])>=24 and (r['speed_raw']&32767)>=200:
     report=self.brake();self.test['records'].append(dict(case=self.test['case'],trigger=r,brake=report));self.phase='TEST_SETTLE';self.test['stable_since']=None;self.event('TEST_BRAKE',case=self.test['case'])
   elif self.phase=='TEST_SETTLE':
    if now-self.test['case_began']>10.:raise RuntimeError('Brake settling not confirmed')
    if not r['speed_raw'] and not r['moving_raw']:
     if self.test['stable_since'] is None:self.test['stable_since']=now
     if now-self.test['stable_since']>=.3:
      if self.test['case']==0:self.test['case']=1;self.start_test_case()
      else:
       with self.a.internal():restore_position_hold(self.b)
       self.completed_test=True;self.phase='TEST_DONE';self.m.operator_stopped=True;self.reason='1000/8 open-path sequence complete. Q saves; inspect log before foam.';self.event('HIGH_PROFILE_TEST_COMPLETE',records=self.test['records'])
    else:self.test['stable_since']=None
   elif self.phase=='RECOVERY':
    action=self.recovery.update(r,now)
    if action=='PROBE':
     with self.a.internal():restore_position_hold(self.b)
     self.recovery.issued(self.clock(),self.row()['position_raw']);self.reason='Limited gentle ID1 probe';self.event('PROBE',target=self.recovery.probe_target)
    elif action=='PAUSE':self.damp('probe resistance');self.event('PROBE_FAILED',reason=self.recovery.pause_reason);self.recovery.pause(self.clock());self.reason='Still resisted: paused before retry'
    elif action=='LATCH':raise RuntimeError('No bounded probe space; operator inspection required')
    elif action=='RESUME':
     # Resume only the pre-contact goal when it remains ahead; never replay a new far sweep.
     goal=self.old_goal;direction=self.recovery.sign;distance=direction*((goal if goal is not None else r['position_raw'])-r['position_raw'])
     if distance<16:self.return_normal();return True
     lo,hi=self.b.windows[1]
     if not max(lo,1691)<=goal<=min(hi,2347):raise RuntimeError('Old ID1 goal outside current bounds')
     acc=4 if distance>=96 else 3;data=bytes((acc,))+goal.to_bytes(2,'little')+b'\0\0'+(600).to_bytes(2,'little')
     _write(self.b,41,data,receive_write_ack,self.clock)
     if self.b.read(1,33,38)[8:15]!=data:raise RuntimeError('Safety handoff readback mismatch')
     self.assist=HandoffAssist(goal,self.clock()) if acc==4 else None;self.resume_started=self.clock();self.phase='HANDOFF';self.guard=EarlyGuard();self.reason='ID1 clear: handoff';self.event('HANDOFF',goal=goal,acc=acc)
    if self.phase=='RECOVERY' and self.recovery.phase=='PROBING':
     goal=self.recovery.command_goal(self.clock())
     if goal!=r['goal_raw']:
      with self.a.internal():self.b.write(1,42,goal.to_bytes(2,'little'))
   elif self.phase=='HANDOFF':
    if r['target_speed_raw']!=600 or r['acceleration_raw']!=(4 if self.assist else 3):raise RuntimeError('Safety handoff profile drift')
    g=self.guard.update(r,now)
    if g['state']=='FAULT_HOLD':raise RuntimeError(g['reason'])
    if g['trip']:
     self.brake();self.recovery.pause(self.clock(),new_contact=True);self.phase='RECOVERY';self.assist=None
    elif self.assist is None and now-self.resume_started>=.15 or self.assist is not None and self.assist.restore_ready(r,now):
     _write(self.b,41,b'\3',receive_write_ack,self.clock);self.return_normal()
   return True
  except Exception as e:self.fail(e);return True
 def cleanup(self):
  self.a.blocked=True;self.phase='CLOSING'
  self.damp('Q/owner cleanup');deadline=self.clock()+4.;since=None
  while self.clock()<deadline:
   r=self.row()
   if not r['speed_raw'] and not r['moving_raw']:
    if since is None:since=self.clock()
    if self.clock()-since>=.3:break
   else:since=None
   time.sleep(.02)
  else:raise RuntimeError('ID1 cleanup did not settle; cap retained')
  with self.a.internal():restore_position_hold(self.b)
  self.pid_after={str(i):list(self.b.read(i,21,3)) for i in range(1,6)}
  if self.pid_after!=self.pid_before:raise RuntimeError('PID changed externally; no automatic correction')
 def finish(self,error):
  if self.closed:return
  self.closed=True;self.log.flush();self.log.close()
  (self.out/'summary.json').write_text(json.dumps(dict(experimental=True,phase=self.phase,reason=self.reason,events=self.events,test_complete=self.completed_test,cleanup_error=None if error is None else repr(error),cap_audit=getattr(self.b,'cap_audit',{}),pid_before=self.pid_before,pid_after=getattr(self,'pid_after',None)),indent=2))
