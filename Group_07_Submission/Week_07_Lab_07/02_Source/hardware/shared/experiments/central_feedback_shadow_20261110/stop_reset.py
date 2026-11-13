"""Isolated open-path V test: one frozen stop frame, fresh models, Normal park.

Not an enabled contact detector or clearance sensor. No PID/mode/torque writes.
"""
import copy,json,time
from .brake_capture import Capture

def queue_stop_test(m,q):
 """Laboratory V request is handled at a UART-owner packet boundary.

 H/Space keep their original urgent semantics; V must not cancel the PLAY
 packet whose readback is still being verified on the other thread.
 """
 with m.lock:
  if m.stopping.is_set() or m.urgent_stop.is_set() or any(k in (ord('h'),32)for k in m.keys):return False
  if not q.request():return False
  if m.stopping.is_set() or m.urgent_stop.is_set():q.operator_abort=True;return False
  m.keys=[ord('v')]
  return True

def stop_goals(rows,limits,tolerances):
 if [r['id'] for r in rows]!=list(range(1,6)):raise RuntimeError('Five fresh joint samples required')
 goals={}
 for r in rows:
  i=r['id'];q=r['position_raw'];lo,hi=limits[i]
  if r['mode'] or r['torque_raw']!=1 or r['status_raw'] or not lo<=q<=hi:raise RuntimeError('Unhealthy or out-of-bounds stop sample')
  stationary=(r['speed_raw']==0 and r['moving_raw']==0 and r['goal_raw']==r['internal_target_raw']
              and abs(r['goal_raw']-q)<=tolerances[i] and lo<=r['goal_raw']<=hi)
  # Preserve the equilibrium command of a resting loaded joint: do not ratchet
  # its target to the sagged encoder position. Active trajectories are cancelled.
  goals[i]=r['goal_raw'] if stationary else q
 return goals

class StopOnce:
 def __init__(self):self.attempted=False;self.goals=None;self.report=None
 def commit(self,bus,goals,cancelled,writer=None):
  if self.attempted:return self.report
  self.attempted=True;self.goals=dict(goals);prior=dict(bus.windows)
  had_group_flag=hasattr(bus,'sync_all_state_position_trial');prior_group_flag=getattr(bus,'sync_all_state_position_trial',False)
  try:
   # Same exception used by the existing hold_actual: permit only the verified
   # frozen hold values, then restore the prior command windows immediately.
   bus.windows.update({i:(q,q) for i,q in goals.items()})
   if getattr(bus,'presentation_all_state_sync_positions',False) is True:bus.sync_all_state_position_trial=True
   self.report=(bus.sync_positions(self.goals,cancelled) if writer is None else writer.commit(bus,self.goals,cancelled))
   return self.report
  finally:
   bus.windows.clear();bus.windows.update(prior)
   if had_group_flag:bus.sync_all_state_position_trial=prior_group_flag
   elif hasattr(bus,'sync_all_state_position_trial'):delattr(bus,'sync_all_state_position_trial')

def restore_initial_models(m,rhythm,fsm):
 m.rhythm_driver=copy.deepcopy(rhythm);m.automatic_fsm=copy.deepcopy(fsm)
 m.pending_behavior=None;m.pending_happy_from_touch=False
 m.rhythm_pending=None;m.interested_roll_due=None;m.rhythm_normal_gaze_started=False
 if hasattr(m.rhythm_driver,'rhythm'):m.rhythm_view_cache=m.rhythm_driver.rhythm.status()

def return_allowed(stopped,clear,operator_stop):return stopped is True and clear is True and operator_stop is False

def clearance(m):
 from physical_distance import distance_input_kind
 source=getattr(m,'physical_distance',None)
 if source is None:return False
 sample=source.latest();kind=distance_input_kind(sample,m.now())
 # This is an OPEN-PATH experiment only. ToF is not proof of side/base clearance.
 return kind in ('range','no_target') and (kind=='no_target' or sample['distance_cm']>=28.)

class ResetCapture(Capture):
 def __init__(self,*a,**kw):
  super().__init__(*a,**kw);self.stop=StopOnce();self.phase='WAIT_V';self.operator_abort=False;self.events=[]
  self.method='ONE_FROZEN_SYNC_POSITION_HOLD_NO_DAMPING'
  self.initial_rhythm=None;self.initial_fsm=None
  self.error=None
 def event(self,name,**kw):self.events.append(dict(event=name,time_s=self.clock(),**kw))
 def bind(self,m):
  self.initial_rhythm=copy.deepcopy(m.rhythm_driver);self.initial_fsm=copy.deepcopy(m.automatic_fsm)
 def begin(self,m):
  if self.stop.attempted:return
  c=m.controller;self.hold_started=self.clock();self.context=m.bus.central_feedback.recorder.context();self.phase='BRAKING'
  m.operator_stopped=True;m.follow_enabled=False;m.held=True
  m.pending_behavior=None;m.pending_happy_from_touch=False;m.interested_roll_due=None
  m.visual.position=None;m._reset_pitch();c.behavior_sweep=None
  if getattr(c,'pose_route',None) is not None:c.pose_route.cancel()
  with m.lock:m.keys=[];m.latest_result=None
  # All subsequent motion services are bypassed by the worker hook until Q.
  # This runs only after the prior play transaction has completed. Manual
  # H/Space and Q can still cancel the new stop transaction.
  from normal_gaze_motor import decode_state
  rows=[decode_state(i,m.bus.read(i,33,38)) for i in range(1,6)]
  goals=stop_goals(rows,{i:c.feedback_window(i) for i in range(1,6)},c.normal_tolerances)
  from sync_position_writer import PositionSyncWriter
  # A cancelled play frame may have latched its writer blocked. Safety uses an
  # independent one-shot transaction object on the SAME bus/worker, not a new
  # transport/thread, so a play-writer latch cannot suppress the stop frame.
  report=self.stop.commit(m.bus,goals,lambda:m.stopping.is_set() or m.urgent_stop.is_set(),writer=PositionSyncWriter())
  if not report or report.get('status')!='goal_readback_verified':raise RuntimeError('Frozen stop frame not verified')
  self.hold_done=self.clock();self.event('ONE_STOP_FRAME',goals=goals,report=report)
 def settled(self):
  now=self.clock()
  for i in range(1,6):
   rows=[r for r in self.history[i] if now-r['time_s']<=.35]
   if len(rows)<3 or now-rows[-1]['time_s']>.2:return False
   # A continuous stationary tail, not one zero-velocity sample.
   tail=[]
   for r in reversed(rows):
    if r['speed_raw'] or r['moving_raw'] or r['mode'] or r['torque_raw']!=1 or r['status_raw']:break
    tail.append(r)
   if len(tail)<3 or tail[0]['time_s']-tail[-1]['time_s']<.15:return False
   if max(r['position_raw'] for r in tail)-min(r['position_raw'] for r in tail)>2:return False
  return True
 def service(self,m):
  c=m.controller
  if m.stopping.is_set():return
  if self.operator_abort or c.state=='FAULT':self.phase='LATCHED'
  if self.phase=='RETURNING' and not clearance(m):
   m._hold('Open-path Normal return lost valid clearance',True);m.operator_stopped=True;self.phase='LATCHED'
   self.event('RETURN_ABORT_CLEARANCE');return
  c.tick(m.now());self.tick()
  if c.state=='FAULT':self.phase='LATCHED';return
  if self.phase=='BRAKING' and self.complete:
   stopped=self.settled();clear=clearance(m)
   if self.clock()-self.requested>8. and not stopped:
    self.phase='LATCHED';self.event('STOP_NOT_CONFIRMED');return
   if return_allowed(stopped,clear,self.operator_abort):
    restore_initial_models(m,self.initial_rhythm,self.initial_fsm)
    from sync_position_writer import PositionSyncWriter
    m.bus.position_sync_writer=PositionSyncWriter()
    self.event('MODELS_RESET',h=m.rhythm_driver.normal_ahm.h,phase_source='fresh startup models')
    # Use the accepted coordinated Normal route with the true startup base yaw,
    # rather than the presentation option that preserves the player's yaw.
    from bio_inspire.runtime.three_state_behavior import handle_state_key
    preserved=m.presentation_normal_preserve_yaw;m.presentation_normal_preserve_yaw=False
    try:handle_state_key(m,ord('n'))
    finally:m.presentation_normal_preserve_yaw=preserved
    self.phase='RETURNING';self.event('NORMAL_RETURN_STARTED',target=dict(c.normal))
  elif self.phase=='RETURNING':
   route=getattr(c,'pose_route',None)
   if route is not None and route.phase=='complete' and self.settled():
    m.behavior_trial='normal';m.operator_stopped=True;m.follow_enabled=False;m.held=True
    self.phase='NORMAL_PARKED';self.event('NORMAL_PARKED',h=m.rhythm_driver.normal_ahm.h)
  self.save_reset()
 def save_reset(self):
  signature=(self.phase,len(self.events),self.operator_abort,self.stop.attempted)
  if signature==getattr(self,'saved_signature',None):return
  (self.out/'STOP_RESET.json').write_text(json.dumps(dict(method='ONE_SYNC_HOLD_FRAME_THEN_INITIAL_NORMAL_PARK',phase=self.phase,
   stop_attempted=self.stop.attempted,frozen_stop_goals=self.stop.goals,stop_report=self.stop.report,events=self.events,
   operator_abort=self.operator_abort,error=self.error,open_path_only=True,contact_detection_enabled=False),indent=2),encoding='utf-8')
  self.saved_signature=signature
 def label(self):
  if self.error:return 'STOP FAILED - support lamp / Q saves diagnostic'
  return {'WAIT_V':'Happy > V once; NO FOAM / stop then initial Normal',
   'BRAKING':'STOP CAPTURE / wait for stationary + clear ToF',
   'RETURNING':'H/CPG reset - returning to initial Normal',
   'NORMAL_PARKED':'NORMAL RESET COMPLETE - parked / support then Q',
   'LATCHED':'STOP LATCHED - support then Q / no auto return'}[self.phase]

def install():
 from .startup_freshness import install as install_startup_freshness
 install_startup_freshness()
 from .live import Session
 from bio_inspire.runtime.camera_motor import CameraMotor
 init,feedback,close,bind=Session.__init__,Session.feedback,Session.close,Session.bind
 def opened(s,*a,**kw):
  init(s,*a,**kw)
  from .read_response_port import ReadResponsePort
  s.bus.port=ReadResponsePort(s.bus.port)
  s.recorder.event('READ_RESPONSE_DRAIN_POLICY',read_reply_validation_unchanged=True,motor_write_flush_unchanged=True)
  s.brake_capture=ResetCapture(s.recorder.out)
 def bound(s,m):s.brake_capture.bind(m);return bind(s,m)
 def observed(s,sid,data,stamp):
  if hasattr(s,'brake_capture'):s.brake_capture.sample(sid,data,stamp)
  return feedback(s,sid,data,stamp)
 def closed(s):
  try:
   s.brake_capture.save();s.brake_capture.save_reset()
   s.recorder.event('READ_RESPONSE_DRAIN_AUDIT',read_drains_skipped=getattr(s.bus.port,'read_drains_skipped',0),motor_write_flush_unchanged=True)
  finally:close(s)
 Session.__init__,Session.bind,Session.feedback,Session.close=opened,bound,observed,closed
 key,worker_key,publish=CameraMotor.key,CameraMotor._key,CameraMotor._publish
 def ui_key(m,k):
  q=m.bus.central_feedback.brake_capture
  if k==ord('v'):
   if m.controller.state not in ('READY','FOLLOWING') or m.operator_stopped:return
   queue_stop_test(m,q);return
  if q.requested is not None:
   if k not in (ord('h'),32):return
   q.operator_abort=True
  return key(m,k)
 def owned_key(m,k):
  q=m.bus.central_feedback.brake_capture
  if q.requested is not None:
   if k in (ord('h'),32) or k==ord('v') and (q.operator_abort or m.urgent_stop.is_set()):
    q.operator_abort=True
    try:return worker_key(m,ord('h') if k==ord('v') else k)
    finally:q.phase='LATCHED';m.urgent_stop.clear()
   if k==ord('v'):
    try:return q.begin(m)  # One owner-side V dispatch, one frozen stop frame.
    except Exception as error:
     q.error=str(error);q.phase='LATCHED';q.event('STOP_FAILED',error=q.error)
     raise  # Existing worker fault/hold path remains authoritative.
  return worker_key(m,k)
 def published(m,ms):
  publish(m,ms)
  q=m.bus.central_feedback.brake_capture
  if m.controller.state=='FAULT':
   if q.phase!='LATCHED':q.phase='LATCHED';q.error=m.controller.last_error or 'Controller fault'
   q.save_reset()
  with m.lock:m._view['brake_reset_label']=m.bus.central_feedback.brake_capture.label()
 CameraMotor.key,CameraMotor._key,CameraMotor._publish=ui_key,owned_key,published
 import play_view
 draw=play_view.draw
 def rendered(cv,image,result,motor=None,start_error=''):
  out=draw(cv,image,result,motor,start_error)
  label='Start/M > Happy > V stops then resets to Normal / NO FOAM' if motor is None else motor.snapshot_view().get('brake_reset_label','Waiting')
  out=cv.copyMakeBorder(out,0,28,0,0,cv.BORDER_CONSTANT,value=(45,30,30))
  cv.putText(out,label,(6,out.shape[0]-10),cv.FONT_HERSHEY_SIMPLEX,.29,(240,240,240),1)
  return out
 play_view.draw=rendered
