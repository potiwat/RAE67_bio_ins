"""Measure the existing operator position-hold stop; never issue servo writes."""
import json, threading, time
from collections import deque

def analyze_axis(before, requested_s, after):
 before=[r for r in before if r['time_s']<=requested_s]
 out=dict(outcome='INSUFFICIENT_DATA',sampled_criteria_met=False)
 if not before or len(after)<4:return out
 pre=before[-1];q=pre['position_raw']
 times=[pre['time_s']]+[r['time_s'] for r in after]
 gaps=[b-a for a,b in zip(times,times[1:])]
 healthy=all(r.get('complete_feedback') is True and r['mode']==0 and r['torque_raw']==1 and r['status_raw']==0 for r in before+after)
 valid=healthy and all(0<g<=.2 for g in gaps) and 0<=requested_s-pre['time_s']<=.2
 recent=[r for r in before if requested_s-r['time_s']<=.2]
 moving=bool(recent) and any((r['speed_raw']&32767)>0 for r in recent) and max(r['position_raw'] for r in recent)-min(r['position_raw'] for r in recent)>=2
 since=None;anchor=None;confirmed=None
 for r in after:
  if r['speed_raw']==0 and r['moving_raw']==0:
   if since is None or abs(r['position_raw']-anchor)>2:since=r['time_s'];anchor=r['position_raw']
   if r['time_s']-since>=.15-1e-9 and confirmed is None:confirmed=r['time_s']
  else:since=None;anchor=None;confirmed=None
 drift=max(abs(r['position_raw']-q) for r in after)*360/4096
 latency=None if confirmed is None else confirmed-requested_s
 out.update(outcome='MEASURED_NOT_GLOBALLY_QUALIFIED' if moving and valid else 'N_A_NO_PRESTOP_MOTION' if valid else 'INVALID_FEEDBACK',
  reference_age_s=requested_s-pre['time_s'],max_feedback_gap_s=max(gaps),max_displacement_deg=drift,
  settle_confirmed_after_request_s=latency,prestop_speed_raw=pre['speed_raw'],
  sampled_criteria_met=bool(valid and moving and drift<=.7 and latency is not None and latency<=.25),
  criteria=dict(displacement_deg=.7,settle_confirmation_s=.25),physical_envelope_qualified=False)
 return out

class Capture:
 def __init__(self,out,clock=time.monotonic):
  self.out=out;self.clock=clock;self.lock=threading.RLock();self.history={i:deque(maxlen=100) for i in range(1,6)}
  self.before={};self.after={i:[] for i in range(1,6)};self.requested=None;self.hold_started=None;self.hold_done=None;self.complete=False;self.context=None
 def request(self):
  with self.lock:
   if self.requested is not None:return False
   self.requested=self.clock();self.before={i:list(rows) for i,rows in self.history.items()};return True
 def sample(self,sid,data,stamp):
  from normal_gaze_motor import decode_state
  r=dict(decode_state(sid,data),time_s=stamp,complete_feedback=True)
  with self.lock:
   self.history[sid].append(r)
   if self.requested is not None and stamp>=self.requested and not self.complete:self.after[sid].append(r)
 def tick(self):
  with self.lock:
   if self.requested is not None and not self.complete and self.clock()-self.requested>=3.:
    self.complete=True;self.save()
 def save(self):
  result=dict(method=getattr(self,'method','EXISTING_OPERATOR_POSITION_HOLD_NO_DAMPING'),complete=self.complete,requested_s=self.requested,
   hold_started_s=self.hold_started,hold_done_s=self.hold_done,context=self.context,
   axes={str(i):analyze_axis(self.before.get(i,[]),self.requested,self.after[i]) for i in range(1,6)} if self.requested is not None else {},
   before=self.before,after=self.after,no_new_motor_profiles=True)
  (self.out/'BRAKE_CAPTURE.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
 def label(self):
  if self.complete:return 'BRAKE CAPTURE COMPLETE - support lamp then Q'
  if self.requested is not None:return 'CAPTURING STOP - hold pose / wait 3 seconds'
  return 'Start/M > Happy > V during motion / NO FOAM'

def install():
 from .live import Session
 from bio_inspire.runtime.camera_motor import CameraMotor
 init,feedback,close=Session.__init__,Session.feedback,Session.close
 def opened(s,*a,**kw):
  init(s,*a,**kw);s.brake_capture=Capture(s.recorder.out)
 def observed(s,sid,data,stamp):
  q=getattr(s,'brake_capture',None)
  if q is not None:q.sample(sid,data,stamp)
  return feedback(s,sid,data,stamp)
 def closed(s):
  try:s.brake_capture.save()
  finally:close(s)
 Session.__init__,Session.feedback,Session.close=opened,observed,closed
 key,worker_key,publish=CameraMotor.key,CameraMotor._key,CameraMotor._publish
 def ui_key(m,k):
  q=m.bus.central_feedback.brake_capture
  if k==ord('v'):
   if m.controller.state not in ('READY','FOLLOWING') or m.operator_stopped:return
   if not q.request():return
   k=ord('h')
  if q.requested is not None and k not in (ord('h'),32):return
  return key(m,k)
 def owned_key(m,k):
  q=m.bus.central_feedback.brake_capture
  if k in (ord('h'),32) and q.requested is not None and q.hold_started is None:
   q.hold_started=q.clock();q.context=m.bus.central_feedback.recorder.context()
   try:return worker_key(m,k)
   finally:q.hold_done=q.clock()
  return worker_key(m,k)
 def published(m,ms):
  q=m.bus.central_feedback.brake_capture;q.tick();publish(m,ms)
  with m.lock:m._view['brake_capture_label']=q.label()
 CameraMotor.key,CameraMotor._key,CameraMotor._publish=ui_key,owned_key,published
 import play_view
 draw=play_view.draw
 def rendered(cv,image,result,motor=None,start_error=''):
  out=draw(cv,image,result,motor,start_error)
  label='BRAKE CHECK - Start/M then Happy, V stops; NO FOAM' if motor is None else motor.snapshot_view().get('brake_capture_label','BRAKE CHECK waiting')
  out=cv.copyMakeBorder(out,0,28,0,0,cv.BORDER_CONSTANT,value=(30,30,60))
  cv.putText(out,label,(6,out.shape[0]-10),cv.FONT_HERSHEY_SIMPLEX,.30,(240,240,240),1)
  return out
 play_view.draw=rendered
