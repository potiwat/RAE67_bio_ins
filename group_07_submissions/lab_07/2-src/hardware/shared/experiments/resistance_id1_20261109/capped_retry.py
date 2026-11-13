"""R5 isolated capped retry. Encoder progress is a probe result, not clearance proof."""
import math
from .capped_trial import CapSession,EarlyGuard,AUDITS
from .native_retry import NativeRetry
from .pilot import blocked

class CappedRetry(NativeRetry):
 cap_limit=160
 automatic_retry=True
 def __init__(self):
  super().__init__();self.guard=EarlyGuard();self.probe_qualified=False
  self.stable_since=None;self.stable_stamp=None;self.stable_q=None
 def reset_stable(self):self.stable_since=None;self.stable_stamp=None;self.stable_q=None
 def stable(self,r,after):
  t=r['sampled_monotonic_s'];q=r['position_raw']
  good=(t>after and not r['moving_raw'] and not r['speed_raw']
        and r['goal_raw']==r['internal_target_raw'] and abs(q-r['goal_raw'])<12
        and (r['load_raw']&1023)<32 and r['current_raw']<3)
  if not good:self.reset_stable();return False
  if t==self.stable_stamp:return False
  self.stable_stamp=t
  if self.stable_q is None or abs(q-self.stable_q)>2:self.stable_since=t;self.stable_q=q
  return t-self.stable_since>=.3-1e-9
 def waiting(self,m,now,reason):
  self.hold(m,now,reason);self.paused=True;self.phase='STOP_CONFIRM';self.phase_s=now
  self.reset_stable();self.endpoint_count=0;self.endpoint_since=None
 def latch(self,m,now,reason):
  self.hold(m,now,reason);self.phase='LATCHED';self.paused=True
  self.events.append(dict(event='retry_latched',time_s=now,reason=reason))
 def speed(self,m,value):
  m.controller.bus.id1_probe_speed(value)
  self.events.append(dict(event='id1_speed',value=value))
 def step(self,d,m,now):
  if blocked(m):return
  if self.started is None:
   super().step(d,m,now)
   if self.started is not None:
    self.waiting(m,now,'free_probe_qualification');self.events.append(dict(event='free_probe_required',time_s=now))
   return
  if self.phase=='RUN':
   super().step(d,m,now)
   if self.samples:self.samples[-1]['cap_audit']=dict(getattr(m.controller.bus,'cap_audit',{}))
   return
  if not isinstance(now,(int,float)) or not math.isfinite(now) or not 0<=now-self.previous<=.2:
   raise ValueError('R5 control clock gap/regression')
  self.previous=now;r=next(r for r in m.controller.last_rows if r['id']==1)
  result=self.guard.update(r,now)
  if result['state']=='FAULT_HOLD':raise RuntimeError('R5 feedback fault: '+str(result['reason']))
  if r['acceleration_raw']!=3 or r['target_speed_raw'] not in (17,600):raise ValueError('R5 parameter drift')
  if not self.limits.low-13<=r['position_raw']<=self.limits.high+13:raise ValueError('R5 encoder outside window')
  if self.phase=='STOP_CONFIRM':
   if self.stable(r,self.phase_s):
    self.phase='WAIT';self.phase_s=now;self.events.append(dict(event='stop_confirmed',time_s=now,actual=r['position_raw']))
   elif now-self.phase_s>=4.:self.latch(m,now,'physical stop unconfirmed')
  elif self.phase=='WAIT' and now-self.phase_s>=2.:
   if not self.stable(r,self.phase_s):
    if now-self.phase_s>=4.:self.latch(m,now,'hold stability lost')
   elif self.attempts>=3:self.latch(m,now,'three probe attempts used')
   else:
    self.probe_start=r['position_raw'];sign=1 if self.target>self.probe_start else -1
    self.probe_target=self.probe_start+sign*16
    if not self.limits.low<=self.probe_target<=self.limits.high:self.latch(m,now,'insufficient bounded probe space')
    else:
     if self.probe_qualified:self.attempts+=1
     self.speed(m,17);self.send(m,self.probe_target);self.guard=EarlyGuard()
     self.phase='PROBE';self.phase_s=now;self.reset_stable()
     self.events.append(dict(event='probe_begin',time_s=now,attempt=self.attempts,start=self.probe_start,target=self.probe_target,qualification=not self.probe_qualified))
  elif self.phase=='PROBE':
   sign=1 if self.probe_target>self.probe_start else -1;progress=sign*(r['position_raw']-self.probe_start)
   if progress < -3 or progress>20:self.latch(m,now,'probe encoder excursion')
   elif result['trip']:
    if not self.probe_qualified:self.latch(m,now,'free probe effort failed')
    else:self.waiting(m,now,'probe resistance')
   elif 10<=progress<=20 and self.stable(r,self.phase_s):
    self.hold(m,now,'probe_pass_hold');self.phase='SETTLE';self.phase_s=now;self.reset_stable()
    self.events.append(dict(event='probe_pass',time_s=now,progress_ticks=progress))
   elif now-self.phase_s>=3.:
    if not self.probe_qualified:self.latch(m,now,'free probe motion unconfirmed')
    else:self.waiting(m,now,'probe timeout')
  elif self.phase=='SETTLE':
   if self.stable(r,self.phase_s):
    was_qualified=self.probe_qualified;self.probe_qualified=True;self.speed(m,600)
    self.phase='RESTORE';self.phase_s=now
    self.events.append(dict(event='resume_pending_readback' if was_qualified else 'free_probe_pass',time_s=now))
   elif now-self.phase_s>=4.:self.latch(m,now,'probe stop unconfirmed')
  elif self.phase=='RESTORE':
   if r['sampled_monotonic_s']>self.phase_s and r['target_speed_raw']==600:
    self.guard=EarlyGuard();self.phase='RUN';self.paused=False
    self.events.append(dict(event='auto_resume',time_s=now,attempt=self.attempts,clearance_claim=False))
   elif now-self.phase_s>=1.:self.latch(m,now,'speed restore unconfirmed')
  if len(self.samples)>=4000:raise ValueError('R5 sample ceiling')
  self.samples.append(dict(time_s=now,elapsed_s=self.active_s,wall_elapsed_s=now-self.started,phase=self.phase,attempts=self.attempts,guard_state=self.guard.state,complete=self.complete,goal_ticks=self.last_goal,target_ticks=self.target,probe_qualified=self.probe_qualified,rows=[dict(x) for x in m.controller.last_rows],cap_audit=dict(getattr(m.controller.bus,'cap_audit',{}))))

class RetryCapSession(CapSession):
 def write_speed(self,value):
  if value not in (17,600):raise ValueError('R5 speed denied')
  b=self.read(1,33,38)
  if b[0]!=0 or b[7]!=1 or b[32]!=0 or int.from_bytes(b[15:17],'little')!=160:
   raise RuntimeError('R5 speed requires healthy capped ID1')
  body=bytes((1,5,3,46))+value.to_bytes(2,'little');packet=b'\xff\xff'+body+bytes((~sum(body)&255,))
  p=self.bus.port;p.reset_input_buffer()
  if p.write(packet)!=len(packet):raise IOError('Partial R5 speed write')
  p.flush();self.ack(p,1,packet)
  if int.from_bytes(self.read(1,33,38)[13:15],'little')!=value:raise RuntimeError('R5 speed readback mismatch')
  self.audit['speed_raw']=value
 def write_cap(self,value):
  if value==self.old and self.audit['applied']:self.write_speed(600)
  super().write_cap(value)
 def install(self):
  b=super().install();b.id1_probe_speed=self.write_speed;return b

def install(module):
 original=module.open_bus
 def open_retry():
  b=original()
  try:
   s=RetryCapSession(b);AUDITS.append(s.audit);return s.install()
  except BaseException:b.close();raise
 module.open_bus=open_retry
