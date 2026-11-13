"""Repeated bounded probes; no ratcheting and no claim of whole-path clearance."""
from .foam_trial import checked_row
from .capped_trial import EarlyGuard

class Recovery:
 def __init__(self,target,native_probe=False,rest_s=2.):
  if type(rest_s) not in (int,float) or rest_s not in (.5,2.):raise ValueError('Unreviewed probe rest interval')
  self.rest_s=rest_s
  self.probe_speed,self.probe_acc=(600,3) if native_probe else (17,1)
  self.target=target;self.attempts=0;self.phase='IDLE';self.since=None;self.q=None;self.stamp=None;self.last_now=None;self.guard=EarlyGuard();self.anchor=None
 def pause(self,now,new_contact=False):
  self.phase='SETTLE';self.start=now;self.since=None;self.q=None;self.stamp=None;self.last_now=now
  if new_contact:self.anchor=None
 def stable(self,r,now):
  if r['sampled_monotonic_s']==self.stamp:return False
  self.stamp=r['sampled_monotonic_s'];q=r['position_raw']
  if r['speed_raw'] or r['moving_raw']:self.since=None;self.q=None;return False
  if self.q is None or abs(q-self.q)>2:self.q=q;self.since=now
  return now-self.since>=.3-1e-9
 def issued(self,now,actual=None):
  self.motion_start=self.issue_position if actual is None else actual
  if abs(self.motion_start-self.anchor)>20:raise RuntimeError('Probe start outside pinned movement bound')
  self.issue_position=self.motion_start;self.duration=max(.8,abs(self.probe_target-self.motion_start)/8.)
  self.last_goal=self.motion_start;self.flow=[];self.resume_kind=None
  self.phase='PROBING';self.start=now;self.since=None;self.q=None;self.stamp=None;self.guard=EarlyGuard();self.last_now=now
 def command_goal(self,now):
  if self.phase!='PROBING' or now<self.start:raise RuntimeError('Probe command outside active ramp')
  u=min(1.,(now-self.start)/self.duration);blend=u*u*(3.-2.*u)
  desired=round(self.motion_start+(self.probe_target-self.motion_start)*blend)
  # A delayed host iteration must not turn the ramp into a large goal step.
  self.last_goal+=max(-1,min(1,desired-self.last_goal))
  return self.last_goal
 def update(self,r,now):
  checked_row(r,now,True)
  if self.last_now is not None and now<self.last_now:raise RuntimeError('Recovery clock regression')
  self.last_now=now
  if self.phase=='LATCHED':return None
  if self.phase in ('SETTLE','WAIT'):
   if r['torque_raw']!=2:raise RuntimeError('Recovery wait requires damping')
   if self.phase=='SETTLE':
    if self.stable(r,now):self.phase='WAIT';self.start=now
   else:
    stable=self.stable(r,now)
    if now-self.start<self.rest_s-1e-9:return None
    if not stable:
     if now-self.start>4.:self.phase='SETTLE';self.start=now
     return None
    if self.anchor is None:self.anchor=r['position_raw']
    self.probe_start=self.anchor;self.issue_position=r['position_raw'];self.sign=1 if self.target>self.anchor else -1;self.probe_target=self.anchor+self.sign*16
    if not 1691<=self.probe_target<=2347:self.phase='LATCHED';return 'LATCH'
    self.attempts+=1;self.phase='PREPARING';return 'PROBE'
  elif self.phase=='PROBING':
   if r['torque_raw']!=1 or r['target_speed_raw']!=self.probe_speed or r['acceleration_raw']!=self.probe_acc:raise RuntimeError('Probe configuration drift')
   progress=self.sign*(r['position_raw']-self.probe_start);g=self.guard.update(r,now)
   if g['state']=='FAULT_HOLD':raise RuntimeError(g['reason'])
   if progress < -3 or progress>20:raise RuntimeError('Probe exceeded movement bound')
   if g['trip'] or now-self.start>=6.:
    self.pause_reason=g['reason'] if g['trip'] else 'bounded probe timeout';return 'PAUSE'
   velocity=(r['speed_raw']&32767)*(-1 if r['speed_raw']&32768 else 1)
   moving=(2<=progress<=20 and self.sign*(r['position_raw']-self.issue_position)>=2
           and 0<=self.sign*velocity<=100 and self.sign*(r['goal_raw']-self.motion_start)>=0
           and min(self.motion_start,self.probe_target)<=r['goal_raw']<=max(self.motion_start,self.probe_target)
           and abs(r['internal_target_raw']-r['goal_raw'])<=1 and abs(r['internal_target_raw']-r['position_raw'])<=8
           and (r['load_raw']&1023)<32 and r['current_raw']<3)
   if moving:
    stamp=r['sampled_monotonic_s'];q=r['position_raw']
    if not self.flow or stamp!=self.flow[-1][0]:
     if self.flow and self.sign*(q-self.flow[-1][1])<0:self.flow=[]
     self.flow.append((stamp,q))
     while len(self.flow)>1 and stamp-self.flow[1][0]>=.1:self.flow.pop(0)
    if self.sign*velocity>0 and progress>=10 and len(self.flow)>=4 and stamp-self.flow[0][0]>=.1-1e-9 and self.sign*(q-self.flow[0][1])>=2:
     self.resume_kind='moving';self.phase='RESUMED';return 'RESUME'
   else:self.flow=[]
   good=(now-self.start>=self.duration and 10<=progress<=20 and self.sign*(r['position_raw']-self.issue_position)>=2 and r['goal_raw']==r['internal_target_raw']==self.probe_target and abs(r['position_raw']-self.probe_target)<12 and (r['load_raw']&1023)<32 and r['current_raw']<3)
   if good and self.stable(r,now):self.resume_kind='settled_fallback';self.phase='RESUMED';return 'RESUME'
   if not good:self.since=None;self.q=None
  return None
