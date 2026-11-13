"""Experimental ID1-only bounded probe; not a person-contact safety system.

No PID/EEPROM/mode/torque-off writes. During probe only, use the previously
observed cap160/Speed600/ACC3 and <=1tick host steps towards a pinned16tick
target. Native proof must precede original profile restoration and any return.
"""
from collections import deque
from write_ack import receive_write_ack
import time

class ProbeIO:
 def __init__(self,bus,window,cancelled,clock):
  self.bus=bus;self.window=window;self.cancelled=cancelled;self.clock=clock
  self.original=None;self.anchor=None;self.goal=None;self.prepared=False;self.restored=False;self.audit=[];self.uncertain_reference=False
 def read(self):
  from normal_gaze_motor import decode_state
  raw=self.bus.read(1,33,38)
  if len(raw)!=38:raise RuntimeError('Probe native read incomplete')
  r=decode_state(1,raw);r['time_s']=self.clock();r['torque_limit_raw']=int.from_bytes(raw[15:17],'little')
  if r['mode']or r['torque_raw']!=1 or r['status_raw']or not self.window[0]<=r['position_raw']<=self.window[1]:
   self.uncertain_reference=True;raise RuntimeError('Probe native support/window fault')
  if not self.window[0]<=r['internal_target_raw']<=self.window[1]or abs(r['internal_target_raw']-r['goal_raw'])>16:
   self.uncertain_reference=True;raise RuntimeError('Probe native reference unconfirmed')
  return r,raw
 def write(self,address,data,recovery=False):
  if address not in(41,42,46,48):raise ValueError('Only ID1 probe RAM allowed')
  if self.cancelled()and not recovery:raise RuntimeError('Probe cancelled')
  body=bytes((1,len(data)+3,3,address))+data;packet=b'\xff\xff'+body+bytes((~sum(body)&255,));p=self.bus.port;p.reset_input_buffer()
  if p.write(packet)!=len(packet):raise RuntimeError('Partial probe write')
  ack_error=None
  try:receive_write_ack(p,1,packet)
  except Exception as error:ack_error=str(error)
  raw=self.bus.read(1,33,38);offset=address-33
  if raw[offset:offset+len(data)]!=data:raise RuntimeError('Probe command readback differs')
  self.audit.append(dict(time_s=self.clock(),address=address,data_hex=data.hex(),ack_error=ack_error))
 def prepare(self):
  r,raw=self.read()
  if r['speed_raw']or r['moving_raw']or abs(r['internal_target_raw']-r['goal_raw'])>2 or abs(r['position_raw']-r['goal_raw'])>12:raise RuntimeError('Probe preparation requires verified stationary hold')
  if r['torque_limit_raw']!=1000:raise RuntimeError('Probe requires known source cap1000')
  self.original=raw;self.anchor=r['position_raw'];self.goal=self.anchor
  # Lower effort before modifying profile or position. Restore cap last.
  self.prepared=True;self.write(48,(160).to_bytes(2,'little'))
  self.write(46,(600).to_bytes(2,'little'));self.write(41,b'\3');self.write(42,self.anchor.to_bytes(2,'little'))
  return r
 def command(self,goal):
  if not self.prepared or not self.window[0]<=goal<=self.window[1]or abs(goal-self.anchor)>16:raise RuntimeError('Probe target outside pinned bound')
  self.goal=goal;self.write(42,goal.to_bytes(2,'little'))
 def hold(self):
  r,_=self.read();q=r['position_raw']
  if self.anchor is None or abs(q-self.anchor)>20:raise RuntimeError('Probe hold outside pinned bound; inspect externally moved base')
  self.goal=q;self.write(42,q.to_bytes(2,'little'),recovery=True)
 def restore(self):
  if self.restored:return
  r,raw=self.read()
  if self.prepared and raw[8]==self.original[8]and raw[13:17]==self.original[13:17]and not r['speed_raw']and not r['moving_raw']and r['internal_target_raw']==r['goal_raw']and abs(r['position_raw']-r['goal_raw'])<=4:
   self.restored=True;return
  if not self.prepared or r['torque_limit_raw']!=160 or r['speed_raw']or r['moving_raw']or r['internal_target_raw']!=r['goal_raw']or abs(r['position_raw']-r['goal_raw'])>4 or(r['load_raw']&1023)>=32 or r['current_raw']>=3:
   raise RuntimeError('Probe profile restore requires fresh low-effort stationary hold')
  if raw[11:13]!=self.original[11:13]:raise RuntimeError('Probe auxiliary register changed')
  self.write(46,self.original[13:15],recovery=True);self.write(41,self.original[8:9],recovery=True)
  self.write(48,self.original[15:17],recovery=True)
  r,raw=self.read()
  if raw[8]!=self.original[8]or raw[13:17]!=self.original[13:17]or r['speed_raw']or r['moving_raw']or r['internal_target_raw']!=r['goal_raw']:raise RuntimeError('Restored probe profile not stationary')
  self.restored=True

class ProbePlan:
 def __init__(self,anchor,normal,now):
  self.anchor=anchor;self.sign=1 if normal>anchor else -1;self.target=anchor+self.sign*16
  self.started=now;self.goal=anchor;self.motion_start=anchor;self.flow=deque();self.still=deque();self.last_stamp=None
 def step(self,r,now):
  t=r['time_s'];progress=self.sign*(r['position_raw']-self.anchor)
  if not 0<=now-t<=.18:return dict(action='pause',reason='stale probe feedback')
  if self.last_stamp is not None and t<=self.last_stamp:return dict(action='wait')
  if self.last_stamp is not None and t-self.last_stamp>.2:
   self.flow.clear();self.still.clear();self.last_stamp=t;return dict(action='pause',reason='probe feedback gap')
  self.last_stamp=t
  if not -3<=progress<=20:return dict(action='pause',reason='probe progress bound')
  effort=(r['load_raw']&1023)>=32 and r['current_raw']>=3
  if effort or abs(r['internal_target_raw']-r['position_raw'])>=12 or now-self.started>=6.:
   self.flow.clear();self.still.clear();return dict(action='pause',reason='renewed effort/error or bounded probe timeout')
  velocity=(r['speed_raw']&32767)*(-1 if r['speed_raw']&32768 else 1)
  good=(10<=progress<=20 and self.sign*(r['position_raw']-self.motion_start)>=2 and abs(r['internal_target_raw']-r['goal_raw'])<=1 and
        abs(r['internal_target_raw']-r['position_raw'])<=8 and(r['load_raw']&1023)<32 and r['current_raw']<3 and 0<=self.sign*velocity<=100)
  if good:
   if self.flow and self.sign*(r['position_raw']-self.flow[-1][1])<0:self.flow.clear()
   self.flow.append((t,r['position_raw']))
   while len(self.flow)>4 and t-self.flow[1][0]>=.2:self.flow.popleft()
   if len(self.flow)>=4 and t-self.flow[0][0]>=.1-1e-9 and self.sign*(r['position_raw']-self.flow[0][1])>=2:return dict(action='passed',progress_ticks=progress,whole_path_clearance=False)
  else:self.flow.clear();self.still.clear()
  if good and now-self.started>=.8 and r['goal_raw']==self.target and not r['speed_raw']and not r['moving_raw']:
   self.still.append((t,r['position_raw']))
   while len(self.still)>4 and t-self.still[1][0]>=.3:self.still.popleft()
   if len(self.still)>=4 and t-self.still[0][0]>=.3-1e-9 and max(q for _,q in self.still)-min(q for _,q in self.still)<=2:
    return dict(action='passed',progress_ticks=progress,kind='stationary_after_verified_motion',whole_path_clearance=False)
  else:self.still.clear()
  u=min(1.,max(0.,(now-self.started)/.8));desired=round(self.motion_start+(self.target-self.motion_start)*(u*u*(3.-2*u)))
  self.goal+=max(-1,min(1,desired-self.goal))
  return dict(action='command',goal=self.goal)

class AutoID1:
 """Owner-thread sub-sequence. Other axes keep verified frozen holds."""
 def __init__(self,adapter):
  self.a=adapter;self.active=False;self.io=None;self.plan=None;self.phase='IDLE';self.stable=[];self.attempts=0;self.rest_at=None;self.passed=False;self.failed=False;self.failure_handled=False;self.manual_epoch=None
 def event(self,name,**data):self.a.core.record(name,**data)
 def begin(self):
  a=self.a;e=a.core.event or{}
  if self.failed or self.active or self.manual_epoch==(a.core.serial,a.core.hold_epoch)or a.core.phase!='WAIT_CLEARANCE'or not a.core.allow_return or not a.core.reset_done or e.get('axis')!=1 or e.get('kind')not in('resistance','test_stop'):return
  if a.core.pending or not a.healthy()or not a.stopped()or a.sensor_state()=='near':return
  if a.clear_token is not None:return
  r=next(r for r in a.m.controller.last_rows if r['id']==1)
  if abs(r['goal_raw']-r['position_raw'])>12:return
  lo,hi=a.m.controller.feedback_window(1);window=(max(1691,lo),min(2347,hi))
  q=r['position_raw'];sign=1 if a.m.controller.normal[1]>q else -1
  if not window[0]<=q+sign*16<=window[1]:
   self.phase='MANUAL_REQUIRED';self.manual_epoch=(a.core.serial,a.core.hold_epoch)
   self.event('AUTO_ID1_MANUAL_REQUIRED',reason='No previously reviewed16tick probe space');return
  self.active=True;self.phase='CONFIGURING';self.io=ProbeIO(a.m.bus,window,lambda:a.m.stopping.is_set()or a.m.urgent_stop.is_set(),a.clock)
  try:a._safety(self.io.prepare)
  except BaseException:
   self.event('AUTO_ID1_SETUP_FAILED',writes=self.io.audit);raise
  self.phase='WAIT';self.stable=[];self.rest_at=None
  self.event('AUTO_ID1_PREPARED',cap=160,speed=600,acc=3,pinned_anchor=self.io.anchor,probe_ticks=16,rest_s=.5)
 def observe(self,row):
  if not self.active or row['id']!=1:return
  if row['mode']or row['torque_raw']!=1 or row['status_raw']or not self.io.window[0]<=row['position_raw']<=self.io.window[1]:raise RuntimeError('Automatic probe native support/window fault')
  if not self.io.window[0]<=row['internal_target_raw']<=self.io.window[1]:
   self.io.uncertain_reference=True;raise RuntimeError('Automatic probe native reference outside window')
  if self.a.m.stopping.is_set()or self.a.m.urgent_stop.is_set():return
  if self.phase not in('CONFIGURING','RESTORING','CLOSING'):
   if ('torque_limit_raw'in row and row['torque_limit_raw']!=160)or row['acceleration_raw']!=3 or row['target_speed_raw']!=600 or row['goal_raw']!=self.io.goal:raise RuntimeError('Automatic probe RAM/goal changed')
   if abs(row['internal_target_raw']-row['goal_raw'])>16:
    self.io.uncertain_reference=True;raise RuntimeError('Automatic probe native reference left bounded trajectory')
 def settled(self,r,now,low_effort=True,tolerance=4):
  if not 0<=now-r['time_s']<=.18 or self.stable and r['time_s']-self.stable[-1][0]>.2:
   self.stable=[];self.rest_at=None;return False
  good=(not r['speed_raw']and not r['moving_raw']and r['internal_target_raw']==r['goal_raw']and
        abs(r['position_raw']-r['goal_raw'])<=tolerance and(not low_effort or(r['load_raw']&1023)<32 and r['current_raw']<3))
  if not good:self.stable=[];return False
  if self.stable and r['time_s']<=self.stable[-1][0]:return False
  self.stable.append((r['time_s'],r['position_raw']))
  while len(self.stable)>3 and now-self.stable[1][0]>=.15:self.stable.pop(0)
  return len(self.stable)>=3 and self.stable[-1][0]-self.stable[0][0]>=.15-1e-9 and max(q for _,q in self.stable)-min(q for _,q in self.stable)<=2
 def tick(self):
  a=self.a;r,_=self.io.read();now=a.clock();self.observe(r)
  if self.phase=='WAIT':
   if self.settled(r,now):
    if self.rest_at is None:self.rest_at=now
    if now-self.rest_at>=.5:
     self.plan=ProbePlan(self.io.anchor,a.m.controller.normal[1],now);self.plan.goal=self.io.goal;self.attempts+=1;self.phase='PROBING';self.stable=[]
     progress=self.plan.sign*(r['position_raw']-self.io.anchor)
     if not -3<=progress<=12:
      self.phase='RESTORING';a._safety(self.io.restore);self.adopt_hold();self.active=False;self.phase='MANUAL_REQUIRED';self.manual_epoch=(a.core.serial,a.core.hold_epoch)
      self.event('AUTO_ID1_MANUAL_REQUIRED',reason='Pinned probe space exhausted or external displacement; no ratcheting');return
     self.plan.motion_start=r['position_raw']
     self.event('AUTO_ID1_PROBE_BEGIN',attempt=self.attempts,anchor=self.io.anchor,target=self.plan.target)
   else:self.rest_at=None
  elif self.phase=='PROBING':
   action=self.plan.step(r,now)
   if action['action']=='command'and action['goal']!=self.io.goal:a._safety(lambda:self.io.command(action['goal']))
   elif action['action']in('pause','passed'):
    a._safety(self.io.hold);self.passed=action['action']=='passed';self.phase='SETTLE';self.stable=[]
    self.event('AUTO_ID1_PROBE_PROGRESS'if self.passed else'AUTO_ID1_PROBE_PAUSED',attempt=self.attempts,evidence=action,whole_path_clearance=False)
  elif self.phase=='SETTLE'and self.settled(r,now,tolerance=4 if self.passed else 11):
   # A cancelled tiny move may coast to a quiet residual (recorded7ticks).
   # Loose11 is only for a FAILED attempt: it never preserves a pass token.
   # Establish low-effort standstill first, then ONE fresh actual-position
   # hold at cap160. Do not raise the cap or infer clearance from residual.
   a._safety(self.io.hold);self.phase='SETTLE_FINAL';self.stable=[]
   self.event('AUTO_ID1_STATIONARY_REHOLD',prior_residual_ticks=r['goal_raw']-r['position_raw'],cap=160)
  elif self.phase=='SETTLE_FINAL'and self.settled(r,now):
   if self.passed:
    self.phase='RESTORING';a._safety(self.io.restore);self.adopt_hold();self.active=False;self.phase='COMPLETE'
    a.clear_token=(a.core.serial,a.core.hold_epoch);a.clearance_source='bounded_ID1_probe_experimental'
    self.event('AUTO_ID1_RETURN_AUTHORIZED',method='bounded encoder/effort probe; experimental not whole-path clearance',attempt=self.attempts,profile_restored=True)
   else:
    self.phase='WAIT';self.stable=[];self.rest_at=None
 def adopt_hold(self):
  from .native_stop import GroupStop
  a=self.a;w=GroupStop({i:a.m.controller.feedback_window(i)for i in range(1,6)},clock=a.clock)
  w.bus=a.m.bus;w.reset_q={};w.brake_acc={};w.allow_id1_contact_deflection=True
  for i in range(1,6):
   raw=w._read(w.bus,i);q=int.from_bytes(raw[23:25],'little');goal=int.from_bytes(raw[9:11],'little')
   if raw[7]!=1 or raw[25:27]!=b'\0\0'or raw[33]or raw[9:11]!=raw[34:36]or abs(q-goal)>a.m.controller.normal_tolerances[i]:raise RuntimeError('Post-probe frozen support unconfirmed ID'+str(i))
   w.original[i]=raw;w.expected[i]=raw[7:15];w.reset_q[i]=q
  w.verified=True;w.restored=True;w.attempted=True;w.audit.update(method='POST_PROBE_NATIVE_SUPPORT_ADOPTED_NO_GOAL_WRITES',source_acc_restored=True,probe_audit=self.io.audit,prior_stop_quality_unchanged=True)
  a.writers.append(w);a.stop_writer=w
 def pause_near(self):
  if self.phase!='NEAR_HOLD':
   self.a._safety(self.io.hold);self.phase='NEAR_HOLD';self.stable=[];self.rest_at=None;self.passed=False;self.event('AUTO_ID1_NEAR_PAUSED')
 def failure(self,reason):
  if self.failure_handled:return
  self.failure_handled=True;self.failed=True
  try:
   if self.io is not None and self.io.uncertain_reference:raise RuntimeError('Unknown native reference; no speculative probe recovery writes')
   self.close(recovery_attempt=True)
   self.event('AUTO_ID1_FAILURE_RECOVERED',reason=reason,profile_restored=self.io is None or self.io.restored)
  except BaseException as error:
   self.a.m.bus.unsafe_damping_axes=set(getattr(self.a.m.bus,'unsafe_damping_axes',()))|{1}
   self.a.probe_cleanup_failed=True;self.a.m.cleanup_confirmed=False
   self.event('AUTO_ID1_FAILURE_UNCONFIRMED',reason=reason,recovery_error=str(error))
  self.active=False;self.phase='FAILED'
 def close(self,recovery_attempt=False):
  if self.failed and not recovery_attempt and self.io is not None and not self.io.restored:raise RuntimeError('Probe recovery remains unconfirmed; low cap/unsafe axis requires inspection')
  if not self.active or self.io is None or not self.io.prepared:return
  self.phase='CLOSING';self.a._safety(self.io.hold);self.stable=[];deadline=self.a.clock()+2.
  while self.a.clock()<deadline:
   r,_=self.io.read()
   if self.settled(r,self.a.clock()):
    self.a._safety(self.io.restore);self.adopt_hold();self.active=False;self.phase='CLOSED';self.event('AUTO_ID1_CLOSE_PROFILE_RESTORED');return
   if self.a.simulation:self.a.clock.advance(.02)
   else:time.sleep(.02)
  raise RuntimeError('Probe close support unconfirmed; low cap retained, do not start presentation')

def supervisor_class(base):
 class AutoSupervisor(base):
  def _step(self):
   p=self.a.auto_id1
   if p.failed or self.phase in('LATCHED','CLOSED'):return super()._step()
   if p.active:
    if self.pending or self.a.m.stopping.is_set()or self.a.m.urgent_stop.is_set():p.close();return super()._step()
    if self.a.sensor_state()=='near':p.pause_near();self.a.tick_feedback();return
    if p.phase=='NEAR_HOLD':p.phase='WAIT';p.stable=[];p.rest_at=None
    self.a.tick_feedback()
    if not self.a.healthy():raise RuntimeError('Native motor fault during ID1 probe')
    p.tick();return
   super()._step()
   if self.phase=='WAIT_CLEARANCE':p.begin()
 return AutoSupervisor
