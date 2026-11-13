"""Bounded pre-motion wait for a real fresh ToF frame, not a motor retry."""
from physical_distance import distance_input_kind

class StartupFreshness:
 def __init__(self,source,original_check,wait,cancelled):
  self.source=source;self.original_check=original_check;self.wait=wait;self.cancelled=cancelled
  self.spent_s=0.;self.wait_count=0;self.calls=0
 def check(self):
  self.calls+=1
  if self.calls>1:
   # Later callbacks can occur after a Normal goal has already moved an
   # axis. The worker is not running yet: retain the original immediate
   # abort/hold rather than waiting blindly between moving axes.
   if self.cancelled():raise RuntimeError('Startup ToF check cancelled')
   sample=self.source.latest();error=(sample or{}).get('error')
   if error not in(None,'invalid measurement'):raise RuntimeError('ToF hardware/input error: '+str(error))
   self.original_check()
   if self.cancelled():raise RuntimeError('Startup ToF check cancelled')
   return
  start=self.source.clock();announced=False
  try:
   while True:
    if self.cancelled():raise RuntimeError('Startup ToF check cancelled')
    sample=self.source.latest();now=self.source.clock();kind=distance_input_kind(sample,now)
    error=(sample or{}).get('error')
    if error not in(None,'invalid measurement'):raise RuntimeError('ToF hardware/input error: '+str(error))
    if kind!='fault':
     try:self.original_check()
     except RuntimeError:
      # A producer can update between the two snapshots. Retry only an
      # actually unavailable frame, never an unexplained validator error.
      sample=self.source.latest();now=self.source.clock()
      if distance_input_kind(sample,now)!='fault':raise
      error=(sample or{}).get('error')
      if error not in(None,'invalid measurement'):raise RuntimeError('ToF hardware/input error: '+str(error))
     else:
      if self.cancelled():raise RuntimeError('Startup ToF check cancelled')
      if announced:print('STARTUP_TOF_READY fresh frame verified',flush=True)
      return
    left=.5-self.spent_s-(self.source.clock()-start)
    if left<=1e-9:raise RuntimeError('Start blocked: no fresh ToF frame within startup wait budget; inspect sensor then retry M')
    if not announced:print('STARTUP_TOF_WAIT waiting for a new frame before motion',flush=True);announced=True
    self.wait_count+=1;self.wait(min(.005,left))
  finally:self.spent_s+=max(0.,self.source.clock()-start)

def build_source_factory(factory,simulation=False,external_cancelled=None):
 def create(*args,**kwargs):
  if external_cancelled is not None and external_cancelled():raise RuntimeError('Startup cancelled before ToF creation')
  source=factory(*args,**kwargs)
  if simulation:
   wait=source.clock.advance;stopped=lambda:False
  else:
   wait=source.stop.wait;stopped=source.stop.is_set
  cancelled=lambda:stopped()or external_cancelled is not None and external_cancelled()
  guard=StartupFreshness(source,source.require_fresh,wait,cancelled)
  source.startup_freshness=guard;source.require_fresh=guard.check
  return source
 return create

def build_recovery_poll(original):
 """Re-enter the existing FSM after a real READY recovery, never clear faults."""
 from .range_conditioning import behavior_frame
 def poll(m,now,dispatch=True):
  result=original(m,now,dispatch=dispatch)
  if getattr(m,'distance_view',None) is not None:
   m.distance_view=behavior_frame(m.distance_view)
  if dispatch:return result
  a=m.bus.central_feedback.brake_capture
  fsm=getattr(m,'automatic_fsm',None)
  if (a.core.phase=='PLAY'and m.controller.state in('READY','FOLLOWING')and
      getattr(m,'behavior_trial',None)=='distance_wait'and fsm is not None and
      not m.operator_stopped and not m.stopping.is_set()and not m.urgent_stop.is_set()):
   source=m.physical_distance;sample=source.latest()
   if distance_input_kind(sample,m.now())!='fault':
    # poll_distance(dispatch=False) recovered native READY, but deliberately
    # left behavior distance_wait. Let the same FSM tick re-dispatch its
    # actual state (including Near/Afraid), rather than wait for a button.
    fsm.applied=None;a.core.record('DISTANCE_READY_REDISPATCH',target=None if fsm.fsm is None else fsm.fsm.state)
  return result
 return poll


def prepare_cold_pid_restore(bus,profile):
 """Restore approved volatile gains before recorder guard, only with all torque OFF.

 The original operator preflight validates values, stationary feedback and lock1.
 It writes only differing PID bytes here; it does not enable torque or move goals.
 """
 from startup_preflight import prepare_operator_start
 pids=profile.get('startup_pid_by_id')
 if not isinstance(pids,dict)or set(pids)!=set(map(str,range(1,6))):raise ValueError('Approved startup PID missing')
 from manual_tuning import validate_values
 desired={}
 for key,p in pids.items():
  if not isinstance(p,dict)or set(p)!={'p','i','d'}:raise ValueError('Approved P/I/D required')
  v=validate_values(dict(p,speed=1),int(key));desired[int(key)]=bytes((v['p'],v['d'],v['i']))
 before={i:bus.read(i,21,3)for i in range(1,6)}
 report=dict(restored=False,pid_before={str(i):list(v)for i,v in before.items()},pid_after={str(i):list(v)for i,v in before.items()})
 if before==desired:return report
 rows=bus.snapshot()
 if len(rows)!=5 or any(r['torque_raw']!=0 for r in rows):raise RuntimeError('Startup PID mismatch while torque active; inspect instead of rewriting')
 prepare_operator_start(bus,pids)
 after={i:bus.read(i,21,3)for i in range(1,6)}
 if after!=desired:raise RuntimeError('Approved cold-start PID restore unconfirmed')
 report.update(restored=True,pid_after={str(i):list(v)for i,v in after.items()},scope='approved volatile startup restore only; no torque/goal writes')
 return report
