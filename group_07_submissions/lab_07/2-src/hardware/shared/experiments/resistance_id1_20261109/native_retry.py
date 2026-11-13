"""Isolated ID1 native sweep plus bounded probes; not contact safety certification."""
import math
from .pilot import Pilot,blocked
from .pause_guard import ID1PauseGuard
from bounded_motion import BoundedMotion,MotionLimits

class NativeRetry(Pilot):
 def __init__(self):
  super().__init__();self.phase='INIT';self.attempts=0;self.active_s=0.;self.phase_s=None;self.probe_start=None;self.probe_motion=None;self.good=0;self.probe_stamp=None;self.endpoint_stamp=None;self.endpoint_since=None;self.endpoint_count=0
 def send(self,m,q):
  if not self.limits.low<=q<=self.limits.high:raise ValueError('Native trial goal outside approved yaw path')
  if not blocked(m) and q!=self.last_goal:
   m.controller.bus.write(1,42,int(q).to_bytes(2,'little'));m.controller.last_goal=q;self.last_goal=q
 def waiting(self,m,now,reason):
  self.hold(m,now,reason);self.paused=True;self.endpoint_count=0;self.endpoint_since=None
  self.phase='LATCHED' if self.attempts>=3 else 'WAIT';self.phase_s=now
 def step(self,d,m,now):
  if blocked(m):return
  if self.started is None:
   super().step(d,m,now)
   if self.started is not None:
    c=m.controller;lo,hi=c.yaw_window;lo+=c.command_margin_ticks;hi-=c.command_margin_ticks
    self.limits=MotionLimits(lo,hi,20.,40.,.2);self.target=hi;self.phase='RUN';self.phase_s=now
    self.events.append(dict(event='native_mode',time_s=now,bounds=[lo,hi],max_probe_attempts=3,probe_ticks=8,native_speed_raw=600,native_acceleration_raw=3))
   return
  if type(now) not in (float,int) or not math.isfinite(now) or now<self.previous or now-self.previous>.2:raise ValueError('Native control clock gap/regression')
  dt=now-self.previous;self.previous=now;c=m.controller;r=next(r for r in c.last_rows if r['id']==1)
  if r['target_speed_raw']!=600 or r['acceleration_raw']!=3:raise ValueError('Native parameter drift')
  if not c.yaw_window[0]<=r['position_raw']<=c.yaw_window[1]:raise ValueError('Native encoder outside approved yaw window')
  result=self.guard.update(r,now)
  if result['state']=='FAULT_HOLD':raise RuntimeError('Native feedback fault: '+str(result['reason']))
  if self.complete:return
  if self.phase=='RUN':
   self.active_s+=dt
   if result['trip']:
    self.events.append(dict(event='resistance_pause',time_s=now,elapsed_s=self.active_s,row=dict(r)))
    self.waiting(m,now,'resistance_suspected')
   elif self.active_s>=45.:
    self.hold(m,now,'pilot_complete');self.complete=True;self.phase='COMPLETE'
    self.events.append(dict(event='complete',time_s=now,elapsed_s=self.active_s))
   else:
    # A stationary servo can retain small error with the accepted P/I settings.
    # Confirm native target receipt, low effort and fresh settled samples; never
    # call high-effort contact an endpoint, nor change PID/offset to force arrival.
    error=abs(r['position_raw']-self.target)
    arrived=(error<self.guard.internal_error_ticks and r['goal_raw']==self.target
             and r['internal_target_raw']==self.target and not r['speed_raw'] and not r['moving_raw']
             and (r['load_raw']&1023)<self.guard.effort_duty_raw and r['current_raw']<self.guard.effort_current_raw)
    if r['sampled_monotonic_s']!=self.endpoint_stamp:
     self.endpoint_stamp=r['sampled_monotonic_s']
     if arrived:
      if self.endpoint_since is None:self.endpoint_since=self.endpoint_stamp
      self.endpoint_count+=1
     else:self.endpoint_count=0;self.endpoint_since=None
    if self.endpoint_count>=3 and self.endpoint_stamp-self.endpoint_since>=.1-1e-9:
     self.events.append(dict(event='settled_endpoint',time_s=now,target_ticks=self.target,actual_ticks=r['position_raw'],residual_ticks=error))
     self.target=self.limits.low if self.target==self.limits.high else self.limits.high
     self.endpoint_count=0;self.endpoint_since=None
    self.send(m,int(self.target))
  elif self.phase=='WAIT' and now-self.phase_s>=2.:
   if self.attempts>=3:self.phase='LATCHED'
   elif not r['speed_raw'] and not r['moving_raw']:
    self.attempts+=1;self.probe_start=r['position_raw'];sign=1 if self.target>self.probe_start else -1
    self.probe_target=max(self.limits.low,min(self.limits.high,self.probe_start+sign*8))
    self.probe_motion=BoundedMotion(self.probe_start,now,MotionLimits(min(self.probe_start,self.probe_target)-1,max(self.probe_start,self.probe_target)+1,20.,40.,.2))
    self.phase='PROBE';self.phase_s=now;self.good=0;self.probe_stamp=None
    self.events.append(dict(event='probe_begin',time_s=now,attempt=self.attempts,start=self.probe_start,target=self.probe_target))
  elif self.phase=='PROBE':
   sign=1 if self.probe_target>self.probe_start else -1;progress=sign*(r['position_raw']-self.probe_start)
   if r['sampled_monotonic_s']!=self.probe_stamp:
    self.probe_stamp=r['sampled_monotonic_s']
    good=(6<=progress<=10 and abs(r['internal_target_raw']-r['position_raw'])<=4 and (r['load_raw']&1023)<32 and r['current_raw']<3)
    self.good=self.good+1 if good else 0
   if self.good>=2:
    self.hold(m,now,'probe_pass_hold');self.phase='SETTLE';self.phase_s=now
    self.events.append(dict(event='probe_pass',time_s=now,attempt=self.attempts,progress_ticks=progress))
   elif now-self.phase_s>=1.5:
    self.events.append(dict(event='probe_fail',time_s=now,attempt=self.attempts))
    self.waiting(m,now,'probe_failed')
   else:
    q=round(self.probe_motion.step(self.probe_target,now));q=max(min(self.probe_start,self.probe_target),min(max(self.probe_start,self.probe_target),q))
    self.send(m,q)
  elif self.phase=='SETTLE':
   if r['sampled_monotonic_s']>self.phase_s and not r['speed_raw'] and not r['moving_raw'] and abs(r['internal_target_raw']-r['position_raw'])<=4:
    self.guard=ID1PauseGuard();self.phase='RUN';self.paused=False;self.resume_requested=False
    self.events.append(dict(event='auto_resume',time_s=now,attempt=self.attempts,actual_ticks=r['position_raw']))
   elif now-self.phase_s>2.:raise RuntimeError('Probe settling timeout')
  if len(self.samples)>=4000:raise ValueError('Native diagnostic sample limit')
  self.samples.append(dict(time_s=now,elapsed_s=self.active_s,wall_elapsed_s=now-self.started,phase=self.phase,attempts=self.attempts,guard_state=self.guard.state,complete=self.complete,goal_ticks=self.last_goal,center_ticks=self.center,target_ticks=self.target,rows=[dict(x) for x in c.last_rows]))
