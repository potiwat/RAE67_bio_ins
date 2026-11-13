"""Experimental single-owner adapter. Live contact IDs default DISABLED.

No deploy/GUI entry point. Tests install these hooks only in an isolated process.
"""
import copy,inspect,textwrap,json,threading
from contextlib import contextmanager,ExitStack
from collections import deque
from unittest.mock import patch
from normal_gaze_motor import decode_state
from sync_position_writer import PositionSyncWriter
from shared.experiments.central_feedback_shadow_20261110.stop_reset import StopOnce,stop_goals,restore_initial_models,queue_stop_test,ResetCapture
from shared.experiments.central_feedback_shadow_20261110.live import Session
from shared.experiments.central_feedback_shadow_20261110.integration import patched_worker
from shared.experiments.central_feedback_shadow_20261110.read_response_port import ReadResponsePort
from .supervisor import Supervisor

class PlayPreempted(BaseException):pass

def damping_dispatch_guard(bus,ids):
 if set(ids)&set(getattr(bus,'unsafe_damping_axes',())):raise RuntimeError('Unconfirmed damping recovery; physical Emergency required; motor writes blocked')

def owner_worker(source):
 source=patched_worker(source);lines=source.splitlines();start=next(i for i,x in enumerate(lines)if x=='        while not self.stopping.is_set():')
 end=next(i for i in range(start+1,len(lines))if lines[i].startswith('    except BaseException'))
 body=lines[start+1:end]
 lines[start+1:end]=['            try:']+['    '+x for x in body]+[
  '            except PlayPreempted:',
  '                deadline=next_control_deadline(deadline,self.now())',
  '                self.stopping.wait(max(0,deadline-self.now()))',
  '                continue']
 return ('\n'.join(lines)+'\n').replace('self.stopping.wait(max(0,deadline-self.now()))','self.bus.central_feedback.brake_capture.wait_owner(self,max(0,deadline-self.now()))')

class Adapter:
 def __init__(self,session,clock,enabled_ids=(),simulation=False,clearance_proof=None):
  if enabled_ids and not simulation:raise ValueError('New contact axes require physical qualification; offline tests only')
  self.session=session;self.clock=clock;self.enabled_ids=set(enabled_ids);self.clearance_proof=clearance_proof or (lambda event:False)
  self.m=None;self.requested=None;self.next_event=None;self.operator_abort=False
  self.core=Supervisor(self);self.history={i:deque(maxlen=100)for i in range(1,6)};self.safety_depth=0;self.transaction_depth=0
  self.transactions={};self.packet_events=[];self.snapshots=[];self.last_saved=None
  self.wake=threading.Event()
 @property
 def phase(self):return 'WAIT_V'if self.core.phase=='PLAY'else self.core.phase
 def bind(self,m):
  self.m=m;self.initial_rhythm=copy.deepcopy(m.rhythm_driver);self.initial_fsm=copy.deepcopy(m.automatic_fsm)
 def request(self):
  event=self.next_event or dict(kind='test_stop',axis=None);self.next_event=None
  if event['kind']=='test_stop' and self.core.phase!='PLAY':return False
  if not self.core.request(**event):return False
  self.requested=self.clock();self.wake.set();return True
 def wait_owner(self,m,timeout):
  if not isinstance(m.stopping,threading.Event):return m.stopping.wait(timeout) # virtual plant pump
  if self.wake.is_set():self.wake.clear();return
  self.wake.wait(timeout);self.wake.clear()
 def observe(self,row,decision):
  sid=row['id'];self.history[sid].append(dict(row,time_s=row['time_s']))
  if self.m is None or self.core.phase not in ('PLAY','RETURNING'):return
  if decision['decision']=='WOULD_STOP_RESISTANCE' and sid in self.enabled_ids:
   self.next_event=dict(kind='resistance',axis=sid);queue_stop_test(self.m,self)
  elif self.core.phase=='PLAY' and decision['decision']=='WOULD_HOLD_DATA' and decision['reason']!='controller not ready or operator stop':
   self.next_event=dict(kind='feedback_gap',axis=sid);queue_stop_test(self.m,self)
 def packet_boundary(self):
  if self.m is None or self.safety_depth or self.transaction_depth:return
  if self.core.pending and self.core.pending['kind']in ('resistance','test_stop','feedback_gap'):
   self.begin();raise PlayPreempted()
 def begin(self):self.core.step()
 def service(self,m):
  if m.stopping.is_set():self.core.request('close')
  if self.core.phase!='PLAY':
   for name in ('physical_button','physical_touch'):
    source=getattr(m,name,None)
    if source is not None:source.discard_pending()
  self.core.step();self.save()
 def _safety(self,fn):
  self.safety_depth+=1
  try:return fn()
  finally:self.safety_depth-=1
 def hold(self,epoch):
  m=self.m;c=m.controller;m.operator_stopped=True;m.follow_enabled=False;m.held=True
  m.pending_behavior=None;m.pending_happy_from_touch=False;m.interested_roll_due=None;c.behavior_sweep=None
  if getattr(c,'pose_route',None)is not None:c.pose_route.cancel()
  with m.lock:m.keys=[];m.latest_result=None
  m.visual.position=None;m._reset_pitch()
  def send():
   rows=[decode_state(i,m.bus.read(i,33,38))for i in range(1,6)]
   goals=stop_goals(rows,{i:c.feedback_window(i)for i in range(1,6)},c.normal_tolerances)
   txn=self.transactions.setdefault(epoch,StopOnce())
   report=txn.commit(m.bus,goals,lambda:m.stopping.is_set() or m.urgent_stop.is_set(),writer=getattr(self,'stop_writer',None) or PositionSyncWriter())
   if not report or report['status']!='goal_readback_verified':raise RuntimeError('Stop frame unverified')
   self.packet_events.append(dict(epoch=epoch,time_s=self.clock(),goals=report.get('effective_goals',goals),verified_ids=report['verified_ids'],method=report.get('method','position_hold')))
  self._safety(send)
 def tick_feedback(self):self._safety(lambda:self.m.controller.tick(self.m.now()))
 def failure_hold(self,reason):
  # A failure before the frozen group is verified must not leave the prior
  # dance goal running until Q. Use the original per-axis best-effort hold.
  # It retains independent read/ACK checks and attempts all enabled axes.
  if hasattr(self,'fallback_report'):return
  self.fallback_report=dict(attempted=True,confirmed=False,reason=reason,time_s=self.clock())
  m=self.m;m.operator_stopped=True;m.follow_enabled=False;m.held=True
  try:self.fallback_report['confirmed']=bool(self._safety(lambda:m.controller.hold(reason,all_axes=True)))
  except Exception as error:self.fallback_report['error']=str(error)
  finally:m.controller.state='FAULT';self.core.record('NATIVE_FALLBACK_HOLD',fallback=dict(self.fallback_report))
 def healthy(self):
  rows=self.m.controller.last_rows
  return self.m.controller.state!='FAULT' and len(rows)==5 and all(r['mode']==0 and r['torque_raw']==1 and r['status_raw']==0 for r in rows)
 def stopped(self):return ResetCapture.settled(self)
 def sensor_state(self):
  from physical_distance import distance_input_kind
  source=getattr(self.m,'physical_distance',None);sample=None if source is None else source.latest()
  kind=distance_input_kind(sample,self.m.now())
  self.sensor_snapshot=dict(kind=kind,sample=sample,observed_s=self.m.now())
  if (sample or{}).get('error')not in(None,'invalid measurement'):return 'hardware_fault'
  if kind=='range':return 'clear'if sample['distance_cm']>=28. else 'near'
  return 'clear'if kind=='no_target'else'unknown'
 def clearance_verified(self,event):
  # External evidence is REQUIRED. A low current or head ToF alone cannot
  # certify that side/base contact has been removed.
  return bool(self.clearance_proof(event))
 def reset(self):
  restore_initial_models(self.m,self.initial_rhythm,self.initial_fsm)
  for name in ('physical_button','physical_touch'):
   source=getattr(self.m,name,None)
   if source is not None:source.discard_pending()
  with self.m.lock:self.m.keys=[];self.m.latest_result=None
  self.reset_snapshot=dict(h=self.m.rhythm_driver.normal_ahm.h,bank={k:r.status()for k,r in self.m.rhythm_driver.bank.items()})
 def return_normal(self):
  m=self.m
  def begin():
   from bio_inspire.runtime.three_state_behavior import handle_state_key
   m.bus.position_sync_writer=PositionSyncWriter();flag=m.presentation_normal_preserve_yaw;m.presentation_normal_preserve_yaw=False
   try:handle_state_key(m,ord('n'))
   finally:m.presentation_normal_preserve_yaw=flag
  self._safety(begin)
 def normal_complete(self):
  c=self.m.controller;route=getattr(c,'pose_route',None)
  return getattr(route,'phase',None)=='complete' and all(abs(r['position_raw']-c.normal[r['id']])<=c.normal_tolerances[r['id']] for r in c.last_rows)
 def park(self):
  self.m.operator_stopped=True;self.m.follow_enabled=False;self.m.held=True;self.m.behavior_trial='normal'
  from bio_inspire.runtime.presentation_led import service_breathing
  service_breathing(self.m,'normal',force=True)
 def save(self):
  signature=(self.core.phase,len(self.core.events),len(self.packet_events))
  if signature==self.last_saved:return
  value=dict(evidence='OFFLINE_ADAPTER_NOT_PHYSICAL_QUALIFICATION',phase=self.core.phase,error=self.core.error,events=self.core.events,
   stops=self.packet_events,reset=getattr(self,'reset_snapshot',None),sensor=getattr(self,'sensor_snapshot',None),fallback=getattr(self,'fallback_report',None),enabled_ids=sorted(self.enabled_ids))
  (self.session.recorder.out/'CENTRAL_SAFETY.json').write_text(json.dumps(value,indent=2))
  self.last_saved=signature

@contextmanager
def hooks(root,output,config,clock,enabled_ids=(),simulation=False,clearance_proof=None):
 from bio_inspire.runtime import camera_motor as mod
 original_open=mod.open_bus;original_key=mod.CameraMotor.key;original_owned_key=mod.CameraMotor._key;original_publish=mod.CameraMotor._publish
 source=owner_worker(inspect.getsource(mod.CameraMotor._run));scope=dict(mod.__dict__,PlayPreempted=PlayPreempted);exec(compile(source,str(__file__),'exec'),scope)
 created=[]
 def opened():
  b=original_open();b.port=ReadResponsePort(b.port);s=Session(b,output,config);created.append(s)
  s.scheduler.clock=clock;s.recorder.clock=clock
  a=Adapter(s,clock,enabled_ids,simulation,clearance_proof);s.brake_capture=a
  update=s.detector.update
  def observe(row):r=update(row);a.observe(row,r);return r
  s.detector.update=observe;bind=s.bind
  def bound(m):a.bind(m);bind(m)
  s.bind=bound
  # Guard the final dispatch AFTER scheduler.service(), not the caller-facing
  # wrapper: a READ performed by service() can discover a new stop request.
  # Once a Sync frame begins, keep its entire readback atomic before preemption.
  write,sync=s.scheduler.original_write,s.scheduler.original_sync
  def guarded_write(sid,address,data,*args,**kw):
   if address in(40,41,42,46):damping_dispatch_guard(b,(sid,))
   a.packet_boundary();return write(sid,address,data,*args,**kw)
  def guarded_sync(goals,*args,**kw):
   damping_dispatch_guard(b,goals)
   a.packet_boundary();a.transaction_depth+=1
   try:return sync(goals,*args,**kw)
   finally:a.transaction_depth-=1
  s.scheduler.original_write=guarded_write;s.scheduler.original_sync=guarded_sync
  return b
 def key(m,k):
  a=m.bus.central_feedback.brake_capture
  if k==ord('v'):queue_stop_test(m,a);return
  if k in (ord('h'),32) and a.requested is not None:a.core.request('operator_stop')
  if a.requested is not None and k not in(ord('h'),32):return
  original_key(m,k)
 def owned(m,k):
  a=m.bus.central_feedback.brake_capture
  if k==ord('v'):a.begin();return
  original_owned_key(m,k)
 def publish(m,ms):
  original_publish(m,ms);a=m.bus.central_feedback.brake_capture
  if m.controller.state=='FAULT' and a.core.phase not in('LATCHED','CLOSED'):
   a.core.error=m.controller.last_error;a.core.phase='LATCHED';a.core.record('NATIVE_FAULT')
  a.save()
  with m.lock:m._view['central_safety']=dict(phase=a.core.phase,error=a.core.error)
 with ExitStack()as stack:
  from bio_inspire.runtime import presentation_tempo,presentation_led
  from shared.experiments.central_feedback_shadow_20261110.happy_hormone import HormonePresentationRhythms
  from shared.experiments.central_feedback_shadow_20261110.cpg_led import build_service
  stack.enter_context(patch.object(presentation_tempo,'PresentationRhythms',HormonePresentationRhythms))
  stack.enter_context(patch.object(presentation_led,'service_breathing',build_service(presentation_led.service_breathing)))
  for obj,name,value in ((mod,'open_bus',opened),(mod.CameraMotor,'key',key),(mod.CameraMotor,'_key',owned),(mod.CameraMotor,'_publish',publish),(mod.CameraMotor,'_run',scope['_run'])):
   stack.enter_context(patch.object(obj,name,value))
  yield created
