"""Opt-in experimental ID1/2/4 bounded release; never whole-path clearance.

One UART owner. Failed attempts stay at reduced cap and return to the same
pinned source goal; retry never expands the envelope or increases the cap.
"""
import time
from normal_gaze_motor import decode_state
from .release_io import ReleaseIO
from .release_plan import ReleasePlan
from .native_stop import GroupStop

def calibrated_id2_context(a,sid):
 """Use only the measured Normal-posture slice, never an emotion label."""
 if sid!=2:return None
 c=a.m.controller;normal={2:2837,3:2746,4:1997,5:2696}
 if any(c.normal[i]!=q for i,q in normal.items()):return None
 lo,hi=c.feedback_window(2)
 if lo>2815 or hi<2861:return None
 rows={r['id']:r for r in c.last_rows}
 if set(rows)!=set(range(1,6)):return None
 for i in(3,4,5):
  r=rows[i];t=c.normal_tolerances[i]
  if (r['mode']or r['torque_raw']!=1 or r['status_raw']or r['speed_raw']or r['moving_raw']or
      abs(r['goal_raw']-normal[i])>t or abs(r['position_raw']-normal[i])>t or r['internal_target_raw']!=r['goal_raw']):return None
 r=rows[2]
 return (2819,2851)if 2819<=r['goal_raw']<=2851 and 2815<=r['position_raw']<=2861 else None

class AutoRelease:
 def __init__(self,adapter):
  self.a=adapter;self.active=False;self.io=None;self.plan=None;self.sid=None
  self.phase='IDLE';self.attempts=0;self.epoch_attempts=0;self.failed=False;self.failure_handled=False
  self.deadline=None;self.rest_at=None;self.passed=False;self.last_begin_rejection=None
  self.pin_epoch=None;self.pinned_source=None;self.pin_calibration=None
  self.pin_window=None
  self.post_probe_support=[]
 def event(self,name,**data):self.a.core.record(name,**data)
 def cancelled(self):return self.a.m.stopping.is_set()or self.a.m.urgent_stop.is_set()
 def accepted_windows(self):
  # Controller STOPPED/Normal windows can be narrower than the interrupted
  # Happy/Interested posture. Preserve the verified stop transaction's exact
  # reviewed windows; do not reinterpret a supported old goal as a new fault.
  w=self.a.stop_writer
  if (not isinstance(w,GroupStop)or not w.verified or not w.restored or
      w.bus is not self.a.m.bus or getattr(w.bus,'unsafe_damping_axes',())):
   raise RuntimeError('Verified same-owner stop windows required for release')
  return dict(w.windows)
 def begin(self):
  a=self.a;c=a.core;e=c.event or{};sid=e.get('axis')
  if self.failed or self.active or c.phase!='WAIT_CLEARANCE'or not c.allow_return or not c.reset_done:return
  scheduling_gap=(e.get('kind')=='feedback_gap'and getattr(a,'scheduling_gap_serial',None)==c.serial)
  if (e.get('kind')not in('resistance','test_stop')and not scheduling_gap)or sid not in(1,2,4)or sid not in a.enabled_ids:return
  if c.pending or not a.healthy()or not a.stopped()or a.sensor_state()=='near'or a.clear_token is not None:return
  self.sid=sid
  epoch=(c.serial,c.hold_epoch,sid)
  pin=self.pinned_source if self.pin_epoch==epoch else None
  calibration=self.pin_calibration if self.pin_epoch==epoch else calibrated_id2_context(a,sid)
  if calibration is not None and calibrated_id2_context(a,sid)!=calibration:
   reason='Measured ID2 calibration posture no longer holds'
   if reason!=self.last_begin_rejection:self.last_begin_rejection=reason;self.event('AUTO_RELEASE_WAIT_SUPPORT',id=sid,reason=reason)
   self.phase='WAIT_SUPPORT';return
  window=self.accepted_windows()[sid]
  # The interrupted behavior's read window is not the boundary of the
  # already approved path back to initial Normal. Permit only that endpoint
  # corridor for the selected probe axis; the unchanged pinned excursion
  # still limits actual commands to16/32ticks, not a whole Normal move.
  normal=a.m.controller.normal[sid]
  window=(min(window[0],normal),max(window[1],normal))
  if self.pin_epoch==epoch and self.pin_window is not None:window=self.pin_window
  elif sid==4:
   # Previously authorized +/-32tick ID4 probe may be clipped by Normal's
   # +/-22tick read tolerance. Only at the exact reviewed Normal source,
   # use the existing controller command window (default +/-3degrees), never
   # beyond it. Excursion/cap/ramp/actual-travel checks remain unchanged.
   old=a.stop_writer.expected.get(4);row=next((r for r in a.m.controller.last_rows if r['id']==4),{})
   normal=a.m.controller.normal[4];reviewed=getattr(a.m.controller,'joint_windows',{}).get(4)
   q=row.get('position_raw')
   if (old is not None and type(q)is int and int.from_bytes(old[2:4],'little')==q and
       abs(q-normal)<=12 and reviewed is not None and
       reviewed[0]<=window[0]<=window[1]<=reviewed[1]):
    window=(min(window[0],max(reviewed[0],q-32)),max(window[1],min(reviewed[1],q+32)))
  if calibration is not None:
   if not window[0]<=2815<=2861<=window[1]:raise RuntimeError('Calibration exceeds accepted stop window')
   window=(2815,2861)
  io=ReleaseIO(a.m.bus,sid,window,self.cancelled,a.clock,pinned_source=pin,calibrated_goal_window=calibration,id2_command_span=32 if sid==2 else 16)
  # The feedback callback can run during prepare/readback. Register the new
  # scoped owner before lowering cap, so old hold-profile checks do not race.
  self.io=io;self.active=True;self.phase='CONFIGURING'
  try:a._safety(io.prepare)
  except Exception as error:
   if io.prepared:
    self.io=io;self.active=True;raise
   # Static support is an eligibility check, not evidence of removal.
   self.active=False;self.io=None;self.phase='WAIT_SUPPORT';reason=str(error)
   if reason!=self.last_begin_rejection:
    self.last_begin_rejection=reason;self.event('AUTO_RELEASE_WAIT_SUPPORT',id=sid,reason=reason)
   return
  if c.phase!='WAIT_CLEARANCE'or c.error or c.pending or self.cancelled():raise RuntimeError('Automatic release preparation interrupted')
  if self.pin_epoch!=epoch:self.pin_epoch=epoch;self.pinned_source=(io.anchor_goal,io.anchor_q);self.pin_calibration=calibration;self.pin_window=window;self.epoch_attempts=0
  self.io=io;self.active=True;self.phase='WAIT';self.rest_at=None;self.plan=None
  a.m.bus.acceleration_restore=None
  self.event('AUTO_RELEASE_PREPARED',id=sid,source_goal=io.anchor_goal,source_encoder=io.anchor_q,
             cap=400 if sid==2 else 160,probe_speed_raw=600,probe_acc_raw=8 if sid==2 else 3,excursion_ticks=io.excursion,calibrated_goal_window=calibration,whole_path_clearance=False)
 def observe(self,row):
  if not self.active or row['id']!=self.sid or self.phase in('CONFIGURING','CAPTURING','RESTORING','CLOSING'):return
  lo,hi=self.io.window
  if(row['mode']or row['torque_raw']!=1 or row['status_raw']or
     any(not lo<=row[k]<=hi for k in('position_raw','goal_raw','internal_target_raw'))):
   raise RuntimeError('Automatic release native support/window fault ID'+str(self.sid))
 def start_attempt(self,row):
  direction_goal=self.a.m.controller.normal[self.sid]
  if direction_goal==self.io.anchor_q:
   old=getattr(self.a.stop_writer,'original',{}).get(self.sid)
   if old is not None:
    native=int.from_bytes(old[34:36],'little')
    if native!=self.io.anchor_q:direction_goal=native
  if direction_goal==self.io.anchor_q==self.io.anchor_goal:
   # A contact may stop exactly at Normal. Equality is not proof of release
   # and must not generate an endless zero-distance attempt. Choose a local
   # direction with room INSIDE the same accepted window; ReleasePlan still
   # clips to its unchanged excursion and requires actual encoder progress.
   lo,hi=self.io.window;q=self.io.anchor_q
   direction_goal=hi if hi-q>q-lo or hi-q==q-lo and self.sid!=4 else lo
  self.plan=ReleasePlan(self.sid,self.io.anchor_goal,self.io.anchor_q,direction_goal,self.io.window,self.a.clock(),calibrated_goal_window=self.pin_calibration,id2_command_span=32 if self.sid==2 else 16)
  self.plan.start_at(self.io.goal);self.attempts+=1;self.epoch_attempts+=1;self.phase='PROBING';self.io.still=[]
  self.event('AUTO_RELEASE_PROBE_BEGIN',id=self.sid,attempt=self.attempts,anchor_goal=self.io.anchor_goal,target=self.plan.target)
 def tick(self):
  a=self.a;row,_=self.io.read();now=a.clock();self.observe(row)
  if self.phase=='WAIT':
   if self.io.observe_preprobe_still(row,retry=self.epoch_attempts>0):
    if self.rest_at is None:self.rest_at=now
    if now-self.rest_at>=.25:self.start_attempt(row)
   else:self.rest_at=None
  elif self.phase=='PROBING':
   action=self.plan.step(row,now)
   if action['action']=='command':a._safety(lambda:self.io.command(action['goal']))
   elif action['action']=='fault':raise RuntimeError(action['reason'])
   elif action['action']=='passed':
    if self.sid in(1,4):self.capture()
    self.phase='SETTLE_PASS';self.io.still=[];self.deadline=a.clock()+2.
    self.event('AUTO_RELEASE_LOCAL_PROGRESS',id=self.sid,evidence=action,whole_path_clearance=False)
   elif action['action']=='blocked':
    self.phase='RETURN_PIN';self.io.still=[];self.deadline=now+6.
    self.event('AUTO_RELEASE_BLOCKED_RETRY_SAME_PIN',id=self.sid,evidence=action)
  elif self.phase=='RETURN_PIN':
   if self.io.goal!=self.io.anchor_goal:
    if now>self.deadline:raise RuntimeError('Pinned release retry command deadline')
    goal=self.io.goal+(1 if self.io.anchor_goal>self.io.goal else -1)
    a._safety(lambda:self.io.command(goal))
   elif self.io.observe_preprobe_still(row,retry=True):self.phase='WAIT';self.rest_at=None
  elif self.phase=='SETTLE_PASS':
   if self.io.observe_still(row):
    self.phase='RESTORING';a._safety(self.io.restore);self.phase='VERIFY_RESTORED'
    self.deadline=a.clock()+2.;self.io.still=[]
   elif now>self.deadline:raise RuntimeError('Release motion did not settle before profile restoration')
  elif self.phase=='VERIFY_RESTORED':
   if now>self.deadline:raise RuntimeError('Restored release profile support unconfirmed')
   if self.io.observe_still(row)and self.adopt_hold():
    self.active=False;self.phase='COMPLETE'
    a.clear_token=(a.core.serial,a.core.hold_epoch);a.clearance_source='bounded_ID'+str(self.sid)+'_probe_experimental'
    a._reset_acceleration_helper()
    self.event('AUTO_RELEASE_RETURN_AUTHORIZED',id=self.sid,attempt=self.attempts,profile_restored=True,whole_path_clearance=False)
 def adopt_hold(self):
  a=self.a;windows=self.accepted_windows();windows[self.sid]=self.io.window;w=GroupStop(windows,clock=a.clock)
  w.bus=a.m.bus;w.reset_q={};w.brake_acc={};accepted_rows=[]
  for i in range(1,6):
   raw=w._read(w.bus,i);q=int.from_bytes(raw[23:25],'little');goal=int.from_bytes(raw[9:11],'little')
   if raw[7]!=1:raise RuntimeError('Post-probe active hold missing ID'+str(i))
   if raw[25:27]!=bytes(2)or raw[33]or raw[9:11]!=raw[34:36]or abs(q-goal)>a.m.controller.normal_tolerances[i]:
    self.post_probe_support=[];return False
   w.original[i]=raw;w.expected[i]=raw[7:15];w.reset_q[i]=q
   row=decode_state(i,raw);row.update(time_s=a.clock(),torque_limit_raw=int.from_bytes(raw[15:17],'little'));accepted_rows.append(row)
  # One nonzero speed estimate must not latch a fault before the existing
  # verification deadline. Require unchanged native commands and ALL axes
  # actually stationary for four fresh rounds spanning at least 0.15s.
  now=a.clock();identity=tuple((i,w.expected[i],w.original[i][15:17])for i in range(1,6))
  if self.post_probe_support and(identity!=self.post_probe_support[-1][1]or now<=self.post_probe_support[-1][0]or now-self.post_probe_support[-1][0]>.18):
   self.post_probe_support=[]
  self.post_probe_support.append((now,identity,{r['id']:r['position_raw']for r in accepted_rows}))
  self.post_probe_support=self.post_probe_support[-64:]
  while len(self.post_probe_support)>4 and now-self.post_probe_support[1][0]>=.15-1e-9:
   self.post_probe_support.pop(0)
  proof=self.post_probe_support
  if (len(proof)<4 or proof[-1][0]-proof[0][0]<.15-1e-9
      or any(max(v[2][i]for v in proof)-min(v[2][i]for v in proof)>2 for i in range(1,6))):return False
  w.verified=True;w.restored=True;w.attempted=True
  for row in accepted_rows:w.guard_feedback(row)
  w.audit.update(method='POST_BOUNDED_RELEASE_SUPPORTED_HOLD_NO_REBASE',source_acc_restored=True,probe_id=self.sid,probe_audit=self.io.audit,accepted_windows=dict(w.windows),whole_path_clearance=False)
  a.writers.append(w);a.stop_writer=w;self.post_probe_support=[];return True
 def pause_near(self):
  # Do not generate a new trajectory while positive Near evidence persists.
  # Capture and restore a supported hold before the supervisor can continue.
  self.close();self.phase='NEAR_HOLD'
 def capture(self):
  a=self.a;self.phase='CAPTURING'
  windows=self.accepted_windows();windows[self.sid]=self.io.window
  w=GroupStop(windows,clock=a.clock,contact_axis=self.sid)
  a.writers.append(w);goals={r['id']:r['goal_raw']for r in a.m.controller.last_rows};goals[self.sid]=self.io.goal
  a._safety(lambda:w.commit(a.m.bus,goals,lambda:False))
  a.stop_writer=w;deadline=a.clock()+2.;stable=[]
  while a.clock()<deadline:
   rows=[]
   for i in range(1,6):
    raw=a._safety(lambda i=i:a.m.bus.read(i,33,38));r=decode_state(i,raw)
    r.update(time_s=a.clock(),torque_limit_raw=int.from_bytes(raw[15:17],'little'));w.guard_feedback(r);rows.append(r)
   if all(not r['speed_raw']and not r['moving_raw']and r['internal_target_raw']==r['goal_raw']for r in rows):
    stable.append(rows)
    if len(stable)>=4 and stable[-1][0]['time_s']-stable[0][0]['time_s']>=.15 and all(max(v[i]['position_raw']for v in stable)-min(v[i]['position_raw']for v in stable)<=2 for i in range(5))and w.restore(True):break
   else:stable=[]
   self.wait(.02)
  else:raise RuntimeError('Native release capture support unconfirmed')
  self.io.adopt_stop(w)
 def wait(self,seconds):
  if self.a.simulation:self.a.clock.advance(seconds)
  else:time.sleep(seconds)
 def close(self,recovery_attempt=False):
  if not self.active or self.io is None or not self.io.prepared:return
  self.phase='CLOSING';self.capture();self.phase='CLOSING';deadline=self.a.clock()+2.
  while self.a.clock()<deadline:
   row,_=self.io.read()
   if self.io.observe_still(row):
    self.a._safety(self.io.restore)
    if self.adopt_hold():
     self.active=False;self.phase='CLOSED'
     self.a._reset_acceleration_helper();self.event('AUTO_RELEASE_CLOSE_PROFILE_RESTORED',id=self.sid);return
   self.wait(.02)
  raise RuntimeError('Release close restoration not verified; inspection required')
 def failure(self,reason):
  if self.failure_handled:return
  self.failure_handled=True;self.failed=True
  try:
   self.close(recovery_attempt=True)
   self.event('AUTO_RELEASE_FAILURE_SUPPORTED',id=self.sid,reason=reason)
  except BaseException as error:
   a=self.a;a.probe_cleanup_failed=True;a.m.cleanup_confirmed=False
   a.m.bus.unsafe_damping_axes=set(getattr(a.m.bus,'unsafe_damping_axes',()))|{self.sid}
   self.event('AUTO_RELEASE_FAILURE_UNCONFIRMED',id=self.sid,reason=reason,recovery_error=str(error))
  self.active=False;self.phase='FAILED'
