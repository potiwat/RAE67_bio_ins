"""Explicitly authorized, unqualified manual-R experimental integration only."""
import json,time
from pathlib import Path
from importlib import import_module
from dataclasses import dataclass
from contextlib import contextmanager
from unittest.mock import patch
from shared.experiments.central_safety_controller_20261110 import runtime as base
from shared.experiments.central_safety_controller_20261110.supervisor import Supervisor
from shared.experiments.central_safety_controller_20261110.bench_checks import RestorationGate
from shared.experiments.central_feedback_shadow_20261110.live import Session as BaseSession
from .native_stop import GroupStop
from .led import build_service,build_driver,blackout_output
from .restart import ButtonRestartGate
from .tof import ReturnDistancePolicy
from .startup import build_source_factory,build_recovery_poll

BaseAdapter=base.Adapter

class TrialSupervisor(Supervisor):
 def _step(self):
  super()._step()
  if self.phase!='WAIT_CLEARANCE'or not self.allow_return or not self.reset_done:return
  proof=self.a.static_normal_after_pause()
  if proof is None:return
  self.record('NORMAL_ARRIVAL_VERIFIED_AFTER_SENSOR_PAUSE',proof=proof)
  self.a.park();self.phase='NORMAL_PARKED';self.record('NORMAL_PARKED',completion='verified static arrival; no extra motion')

@dataclass(frozen=True)
class TrialConsent:
 user_authorized:bool
 ids:tuple
 manual_r:bool
 strict_brake_criteria_waived:bool

def contact_ids(values):
 ids=tuple(values)
 if not ids or any(type(i)is not int or i not in range(1,6)for i in ids)or len(set(ids))!=len(ids):raise ValueError('Contact IDs must be unique integers in1..5')
 return tuple(sorted(ids))

def consent(ids=(1,2,3,4,5)):return TrialConsent(True,contact_ids(ids),True,True)

def adapter_class(c,isolate_tof=False,effort_stop=False,auto_id1_return=False,id2_contact_recovery=False,id2_effort_stop=False,resume_after_normal=False,auto_contacts=False,id4_effort_stop=False):
 if id4_effort_stop and 4 not in c.ids:raise ValueError('ID4 effort trial requires selected contact ID4')
 if id2_effort_stop and not id2_contact_recovery:raise ValueError('ID2 effort stop requires the manual recovery trial')
 if id2_contact_recovery and auto_id1_return:raise ValueError('ID2 contact recovery trial requires manual R; ID1 automatic return must be off')
 if auto_id1_return and not(isolate_tof and effort_stop):raise ValueError('Automatic ID1 trial requires isolated ToF and ID1 effort detector')
 if auto_contacts and(auto_id1_return or not isolate_tof):raise ValueError('Central automatic probe requires isolated ToF and no separate ID1 auto owner')
 if auto_contacts and set(c.ids)-{1,2,4}:raise ValueError('Automatic release currently supports only selected ID1/2/4')
 if type(c)is not TrialConsent or not(c.user_authorized and c.manual_r and c.strict_brake_criteria_waived):raise ValueError('Explicit six-state unqualified trial / manual-R consent required')
 contact_ids(c.ids)
 if id2_contact_recovery and 2 not in c.ids:raise ValueError('ID2 recovery requires selected contact ID2')
 if auto_id1_return and 1 not in c.ids:raise ValueError('Automatic ID1 trial requires enabled contact ID1')
 class TrialAdapter(BaseAdapter):
  def __init__(self,session,clock,enabled_ids=(),simulation=False,clearance_proof=None):
   # Preserve the original live guard; this new opt-in adapter has its own
   # separately logged authority, never represents hardware as simulation.
   super().__init__(session,clock,enabled_ids=(),simulation=simulation)
   from .tof_isolation import IsolatedSupervisor,IsolatedDistancePolicy
   self.core=IsolatedSupervisor(self)if isolate_tof else TrialSupervisor(self)
   from .auto_id1 import AutoID1,supervisor_class
   self.auto_id1=AutoID1(self)
   if auto_id1_return:self.core=supervisor_class(IsolatedSupervisor)(self)
   if auto_contacts:
    from .auto_release import AutoRelease
    self.auto_id1=AutoRelease(self);self.core=supervisor_class(IsolatedSupervisor)(self)
   from .recovery_sequence import immediate_reset_supervisor
   self.core=immediate_reset_supervisor(type(self.core))(self)
   self.enabled_ids=set(c.ids);self.simulation=simulation;self.clearance_proof=self.manual_clearance
   if not simulation:
    from .async_log import install
    install(session)
   startup_receipt=getattr(session.bus,'experimental_startup_pid_restore',None)
   if startup_receipt and startup_receipt['restored']:session.recorder.event('APPROVED_COLD_START_PID_RESTORED_BEFORE_RECORDING',**startup_receipt)
   self.clear_token=None;self.pending_r=None;self.in_r_owner=False;self.writers=[];self.stop_writer=None;self.close_prepared=False;self.trial_save_signature=None
   self.clearance_source=None;self.r_wait=None
   self.restart_gate=None;self.restart_request=None;self.restart_claimed=False
   self.retiring_parked_owner=False;self.restart_hold_goals={}
   self.probe_cleanup_failed=False
   self.scheduling_gap_candidate=None;self.scheduling_gap_serial=None
   self.return_distance_policy=IsolatedDistancePolicy()if isolate_tof else ReturnDistancePolicy();self.tof_degraded=False
   self.return_dispatch=False;self.envelope_error=None;self.needs_return_recovery=False;self.normal_arrival_candidate=False
   from .effort_detection import ID1EffortEvidence
   self.effort_monitor=ID1EffortEvidence(session.detector.config)if effort_stop else None
   from .effort_detection import ID2EffortEvidence
   self.id2_effort_monitor=ID2EffortEvidence(session.detector.config)if id2_effort_stop else None
   from .effort_detection import ID4EffortEvidence
   self.id4_effort_monitor=ID4EffortEvidence(session.detector.config)if id4_effort_stop else None
   from .conditioned_effort import ContextEffortEvidence
   self.id2_context_monitor=ContextEffortEvidence.from_path(Path(__file__).with_name('id2_context_reference.json'))if id2_effort_stop else None
   original_close=session.begin_close
   def close():
    try:self.prepare_close()
    except Exception as error:
     if self.auto_id1.io is not None and self.auto_id1.io.prepared:
      self.probe_cleanup_failed=True;self.auto_id1.failure(str(error))
     self.core.error=str(error);self.core.phase='LATCHED'
     if self.m is not None:self.m.controller.state='FAULT';self.m.cleanup_confirmed=False
     self.core.record('CLOSE_PROBE_RESTORE_UNCONFIRMED',error=str(error));self.save()
    finally:
     original_close()
     timing=getattr(self,'pipeline_timing',None)
     if timing is not None:
      try:
       path=self.session.recorder.out/'PIPELINE_TIMING.json';text=json.dumps(timing.snapshot(),indent=2)
       spool=getattr(self.session,'log_spool',None)
       if spool is None:path.write_text(text)
       else:spool.snapshot(path,text)
      except OSError as error:print('PIPELINE_TIMING_SAVE_FAILED',str(error),flush=True)
   session.begin_close=close
  def bind(self,m):
   super().bind(m);original=m.controller.hold
   from .probe_feedback import install as install_probe_feedback
   install_probe_feedback(self)
   spool=getattr(self.session,'log_spool',None)
   if spool is not None and getattr(m,'status_path',None)is not None:
    from .async_log import StatusPath
    m.status_path=StatusPath(m.status_path,spool)
   if not self.simulation:
    from .pipeline_timing import PipelineTiming
    self.pipeline_timing=PipelineTiming(self.clock)
    for obj,name,label in ((self.session.scheduler,'original_read','uart_read'),(self.session.scheduler,'original_write','uart_write'),(self.session.scheduler,'original_sync','uart_sync'),(self.session.scheduler,'on_feedback','feedback_dispatch'),(self.session.recorder,'sample','record_sample'),(self.session.recorder,'event','record_event'),(m.controller,'tick','controller_tick'),(self,'save','safety_save')):
     self.pipeline_timing.wrap(obj,name,label)
    for name in('_apply','_publish','_service_interested_roll','_service_body_rhythm','_service_behavior_request'):
     self.pipeline_timing.wrap(m,name)
    self.pipeline_timing.wrap(getattr(m,'automatic_fsm',None),'service','fsm_service')
   def hold(reason,all_axes=False):
    if reason=='motor worker stopped'and all_axes and self.retiring_parked_owner and not self.probe_cleanup_failed:
     from normal_gaze_motor import decode_state
     from .restart import verify_parked_retirement
     try:
      rows=[decode_state(i,m.bus.read(i,33,38))for i in range(1,6)]
      proof=verify_parked_retirement(self,rows)
     except Exception as error:
      self.core.error=str(error);self.core.record('PARKED_RETIREMENT_FAILED',error=str(error))
      try:self.save()
      except OSError as save_error:print('PARKED_RETIREMENT_AUDIT_FAILED',str(save_error),flush=True)
      return original(reason,all_axes=all_axes)
     self.core.record('PARKED_OWNER_RETIRED_WITHOUT_REBASE',proof=proof);self.save();return True
    result=original(reason,all_axes=all_axes)
    return False if reason=='motor worker stopped'and self.probe_cleanup_failed else result
   m.controller.hold=hold
  def manual_clearance(self,event):
   if self.core.phase=='WAIT_CLEARANCE'and not self.id1_contact_released():self.clear_token=None
   return self.clear_token is not None and self.clear_token==(self.core.serial,self.core.hold_epoch)
  def blackout_detection(self):
   self.m.safety_recovery_led_off=True
   # Detection must not wait for decorative SPI/process cleanup before brake.
   # The existing hold finally performs the physical off after native capture.
   self.m.presentation_led_output=dict(state='contact_detected',requested_brightness=0.,enabled=False,off_command_completed=False,pending_physical_off=True)
  def observe(self,row,decision):
   self.auto_id1.observe(row)
   if (decision.get('reason')=='feedback gap'and self.core.phase=='PLAY'and self.core.pending is None):
    timing=getattr(self,'pipeline_timing',None)
    snapshot=None if timing is None else timing.snapshot()
    self.core.record('FEEDBACK_GAP_DIAGNOSTIC',id=row['id'],gap_s=decision.get('gap_s'),pipeline=snapshot)
    from .scheduling_gap import publish_stall_evidence
    evidence=publish_stall_evidence(snapshot,decision.get('gap_s'),self.clock())
    self.scheduling_gap_candidate=None if evidence is None else dict(axis=row['id'],observed_s=self.clock(),evidence=evidence)
   context_monitor=getattr(self,'id2_context_monitor',None)
   context=context_monitor.update(row,decision)if context_monitor is not None else None
   for sid,monitor in((1,self.effort_monitor),(2,getattr(self,'id2_effort_monitor',None)),(4,getattr(self,'id4_effort_monitor',None))):
    if monitor is None:continue
    evidence=monitor.update({**decision,'position_raw':row.get('position_raw')})
    if (evidence['candidate_stop']and self.m is not None and sid in self.enabled_ids and
        self.core.phase in('PLAY','RETURNING')and self.core.pending is None):
     self.core.record('ID'+str(sid)+'_EXCESS_EFFORT_STOP_REQUEST',evidence=evidence)
     decision={**decision,'decision':'WOULD_STOP_RESISTANCE','reason':evidence['reason']}
   if(context and context['candidate_stop']and decision['decision']=='MONITOR'and self.m is not None and 2 in self.enabled_ids and self.core.phase in('PLAY','RETURNING')and self.core.pending is None):
    self.core.record('ID2_CONTEXT_EFFORT_STOP_REQUEST',evidence=context)
    decision={**decision,'decision':'WOULD_STOP_RESISTANCE','reason':context['reason']}
   super().observe(row,decision)
   w=self.stop_writer
   if self.auto_id1.active and row['id']==getattr(self.auto_id1,'sid',1):return
   if self.m is None or self.return_dispatch or self.core.phase not in('STOPPING','WAIT_CLEARANCE')or w is None or not w.verified:return
   try:w.guard_feedback(row)
   except RuntimeError as error:
    self.envelope_error=str(error);self.m.controller.last_error=str(error)
    self.core.error=str(error);self.core.phase='LATCHED'
    self.m.operator_stopped=True;self.m.follow_enabled=False;self.m.held=True;self.m.controller.state='FAULT'
    self.core.record('STOP_ENVELOPE_FAULT',id=row['id'],error=str(error))
  def allow_feedback_gap_recovery(self,event):
   candidate=self.scheduling_gap_candidate
   if (not auto_contacts or event.get('kind')!='feedback_gap' or candidate is None
       or event.get('axis')not in self.enabled_ids&{1,2,4}
       or event.get('axis')!=candidate['axis']or not 0<=self.clock()-candidate['observed_s']<=.5
       or self.m.stopping.is_set()or self.m.urgent_stop.is_set()
       or getattr(self.m.bus,'unsafe_damping_axes',())or not self.healthy()):return False
   self.scheduling_gap_serial=event['serial']
   self.core.record('RECOVERABLE_SCHEDULING_GAP_ACCEPTED',evidence=candidate['evidence'],
                    native_hold_and_bounded_probe_required=True)
   return True
  def return_normal(self):
   # Supervisor changes WAIT_CLEARANCE -> RETURNING after this deliberate
   # Normal dispatch returns. Its new targets are not old stop-goal faults.
   self.core.record('NORMAL_RETURN_AUTHORIZATION',source=self.clearance_source)
   self.return_dispatch=True;self.needs_return_recovery=True
   try:return super().return_normal()
   finally:self.return_dispatch=False
  def park(self):
   self.m.operator_stopped=True;self.m.follow_enabled=False;self.m.held=True;self.m.behavior_trial='normal'
   blackout_output(self.m);self.needs_return_recovery=False;self.normal_arrival_candidate=False
  def static_normal_after_pause(self):
   if not self.normal_arrival_candidate or not self.id1_contact_released():return None
   token=(self.core.serial,self.core.hold_epoch)
   def permitted():
    return (self.core.phase=='WAIT_CLEARANCE'and self.core.allow_return and self.core.reset_done and
            self.core.pending is None and self.core.error is None and self.m.operator_stopped and
            not self.m.stopping.is_set()and not self.m.urgent_stop.is_set()and
            token==(self.core.serial,self.core.hold_epoch))
   if not permitted()or not self.healthy()or not self.stopped():return None
   rows=self.m.controller.last_rows;c=self.m.controller
   if {r['id']for r in rows}!=set(range(1,6)):return None
   for r in rows:
    i=r['id'];t=c.normal_tolerances[i]
    if (abs(r['position_raw']-c.normal[i])>t or abs(r['goal_raw']-c.normal[i])>t or
        abs(r['internal_target_raw']-r['goal_raw'])>2 or r['speed_raw']or r['moving_raw']):return None
   sensor=self.sensor_state()
   if sensor in('near','hardware_fault')or self.sensor_snapshot['kind']not in('range','no_target','unreliable'):return None
   if not permitted()or not self.healthy():return None
   return {str(r['id']):dict(position_raw=r['position_raw'],goal_raw=r['goal_raw'],internal_target_raw=r['internal_target_raw'],normal_raw=c.normal[r['id']],tolerance_ticks=c.normal_tolerances[r['id']])for r in rows}
  def sensor_state(self):
   source=getattr(self.m,'physical_distance',None);sample=None if source is None else source.latest()
   returning=self.core.phase=='RETURNING'and self.manual_clearance(self.core.event)
   self.sensor_snapshot=self.return_distance_policy.update(sample,self.m.now(),returning)
   degraded=not self.sensor_snapshot.get('protection_available',True)if isolate_tof else self.sensor_snapshot['quality']=='recent_clear_grace'
   if degraded!=self.tof_degraded:
    self.core.record('TOF_RETURN_DEGRADED'if degraded else'TOF_RETURN_QUALITY_RECOVERED',quality=self.sensor_snapshot['quality'],last_confirmed_clear_s=self.return_distance_policy.last_clear_s)
   self.tof_degraded=degraded
   return self.sensor_snapshot['state']
  def queue_clearance(self):
   # GUI copies only the last owner-published token. It never validates
   # standstill or accesses UART and cannot grant a token to a future stop.
   with self.m.lock:
    if self.m.stopping.is_set()or self.m.urgent_stop.is_set():return False
    token=self.m._view.get('trial_safety',{}).get('clearance_token')
    self.pending_r=None if token is None else tuple(token)
    self.m.keys=[k for k in self.m.keys if k not in(ord('r'),ord('R'))]+[ord('r')]
   return True
  def confirm_clearance(self,token,deferred=False):
   if not self.in_r_owner:raise RuntimeError('R validation belongs to UART owner')
   if self.auto_id1.active:
    self.core.record('MANUAL_R_REJECTED',reason='Bounded ID1 probe in progress; H/Q can stop');return False
   checked=(self.core.serial,self.core.hold_epoch)
   eligible=(token is not None and token==checked and self.core.phase=='WAIT_CLEARANCE'and self.core.allow_return
          and not self.m.stopping.is_set()and not self.m.urgent_stop.is_set()and self.core.pending is None and self.healthy())
   stationary=eligible and self.stopped()
   released=eligible and self.id1_contact_released()
   clear=eligible and self.sensor_state()in(('clear','unavailable')if isolate_tof else('clear',))
   valid=eligible and stationary and released and clear
   # Reads during validation may discover a new request. Never bind the
   # acknowledgment to the newer event merely because it is now current.
   valid=valid and self.core.phase=='WAIT_CLEARANCE'and self.healthy()and checked==(self.core.serial,self.core.hold_epoch)and self.core.pending is None and not self.m.urgent_stop.is_set()and not self.m.stopping.is_set()
   if deferred:valid=valid and self.r_wait is not None and self.r_wait['token']==checked and self.clock()<self.r_wait['expires_s']
   if not valid:
    if eligible and not stationary and released and clear and not deferred and checked==(self.core.serial,self.core.hold_epoch)and self.core.pending is None and not self.m.urgent_stop.is_set()and not self.m.stopping.is_set():
     self.r_wait=dict(token=checked,expires_s=self.clock()+2.)
     self.core.record('MANUAL_R_WAIT_STILL',expires_s=self.r_wait['expires_s'],reason='R recorded for this stop only; unchanged standstill/release/clearance checks must pass')
    elif not deferred:self.core.record('MANUAL_R_REJECTED',reason='Fresh displayed stop token / stationary healthy clear path required')
    return False
   self.r_wait=None;self.clear_token=checked;self.clearance_source='operator_R';self.core.record('OPERATOR_CLEARANCE_R',source='operator confirms foam removed and return path clear',deferred=deferred);return True
  def service_r_wait(self):
   request=getattr(self,'r_wait',None)
   if request is None:return
   invalid=(request['token']!=(self.core.serial,self.core.hold_epoch)or self.core.phase!='WAIT_CLEARANCE'or self.core.pending is not None or not self.core.allow_return or not self.healthy()or self.m.stopping.is_set()or self.m.urgent_stop.is_set())
   if invalid or self.clock()>=request['expires_s']:
    self.r_wait=None;self.core.record('MANUAL_R_WAIT_CANCELLED'if invalid else'MANUAL_R_WAIT_EXPIRED');return
   self.in_r_owner=True
   try:self.confirm_clearance(request['token'],deferred=True)
   finally:self.in_r_owner=False
  def contact_release_verified(self,fresh_rows,parked=False):
   w=self.stop_writer
   if w is None:return True
   rows={r['id']:r for r in fresh_rows}
   if 'id1_contact_deflection'in w.audit:
    r=rows.get(1)
    if not(r and not r['speed_raw']and not r['moving_raw']and
      abs(r['position_raw']-r['goal_raw'])<=12 and(r['load_raw']&1023)<32 and r['current_raw']<3):return False
   for sid in(2,3,4,5):
    if 'id'+str(sid)+'_contact_deflection'not in w.audit:continue
    r=rows.get(sid);limits=self.session.detector.config['ids'][str(sid)]
    tolerance=self.m.controller.normal_tolerances[sid]
    if sid==2 and not parked and self.core.phase not in('NORMAL_PARKED','CLOSED'):tolerance=min(16,tolerance)
    if not(r and not r['speed_raw']and not r['moving_raw']and
      abs(r['position_raw']-r['goal_raw'])<=tolerance and
      abs(r['internal_target_raw']-r['goal_raw'])<=2 and
      (r['load_raw']&1023)<=limits['pwm_limit_raw']and r['current_raw']<=limits['current_limit_raw']):return False
   return True
  def id1_contact_released(self):return self.contact_release_verified(self.m.controller.last_rows)
  def hold(self,epoch):
   last=self.core.events[-1]if self.core.events else{}
   self.normal_arrival_candidate=bool(self.needs_return_recovery and last.get('event')=='RETURN_PAUSED'and last.get('reason')=='unknown'and self.core.allow_return and self.core.reset_done)
   self.clear_token=None;self.clearance_source=None;self.r_wait=None
   self.restart_gate=None;self.restart_request=None;self.restart_claimed=False
   # Zero speed may mean blocked; cancel the triggering contact axis too.
   event=self.core.event or{}
   contact_axis=event.get('axis')if event.get('kind')in('resistance','test_stop')and event.get('axis')in self.enabled_ids else None
   self.stop_writer=GroupStop({i:self.m.controller.feedback_window(i)for i in range(1,6)},clock=self.clock,contact_axis=contact_axis);self.writers.append(self.stop_writer)
   self.stop_writer.allow_id1_contact_deflection=effort_stop
   # Manual-only trial: separate the16tick quality metric from verified
   # group support, bounded by EXISTING per-joint hold tolerances. No new goals.
   self.stop_writer.allow_contact_deflection_ids=set(range(1,6))if id2_contact_recovery else set()
   if id2_contact_recovery:self.stop_writer.poststop_quality_limits=dict(self.m.controller.normal_tolerances)
   self.needs_return_recovery=False
   # Cancel deferred writes from the interrupted behavior. Recreate the
   # ordinary acceleration-restoration helper after confirmed standstill.
   self.old_acceleration_restore=getattr(self.m.bus,'acceleration_restore',None);self.m.bus.acceleration_restore=None
   result=super().hold(epoch)
   # On failure, Supervisor invokes native fallback BEFORE decorative I/O.
   blackout_output(self.m,'stopping')
   return result
  def service(self,m):
   if self.core.phase=='WAIT_CLEARANCE'and not self.id1_contact_released():self.clear_token=None
   if isolate_tof:self.sensor_state()
   super().service(m)
   self.service_r_wait()
   if self.envelope_error and self.core.phase=='LATCHED':
    self.core.error=self.envelope_error;self.save()
   if self.core.phase!='NORMAL_PARKED':
    # GUI may claim a verified parked token immediately before this owner
    # processes stopping -> CLOSED. Preserve that in-flight claim only for
    # deliberate retirement; final fresh native proof is still mandatory.
    retiring=(self.retiring_parked_owner and self.restart_claimed and self.core.phase=='CLOSED'
              and not self.core.error and self.core.pending is None and not m.urgent_stop.is_set())
    self.restart_gate=None;self.restart_request=None
    if not retiring:self.restart_claimed=False
    return
   if not self.id1_contact_released():
    self.restart_gate=None;self.restart_request=None;return
   if m.stopping.is_set()or m.urgent_stop.is_set()or self.core.pending is not None:
    self.restart_request=None;return
   if resume_after_normal:
    from .recovery_sequence import arm_automatic_resume
    arm_automatic_resume(self);self.save();return
   source=getattr(m,'physical_button',None)
   if source is None:return
   diagnostics=source.diagnostics()
   if self.restart_gate is None:
    self.restart_gate=ButtonRestartGate(diagnostics);self.core.record('BUTTON_RESTART_ARMED',count=0)
   count=self.restart_gate.count
   if self.restart_gate.update(diagnostics)and not self.restart_claimed and self.restart_request is None and self.healthy()and self.stopped():
    self.restart_hold_goals={r['id']:r['goal_raw']for r in m.controller.last_rows}
    self.restart_request=(self.core.serial,self.core.hold_epoch);self.core.record('BUTTON_RESTART_READY',count=5)
   if count!=self.restart_gate.count:self.core.record('BUTTON_RESTART_COUNT',count=self.restart_gate.count)
   self.save()
  def stopped(self):
   if not super().stopped():return False
   if self.stop_writer is not None:
    if not self.stop_writer.restore(True):return False
    self._reset_acceleration_helper()
   return True
  def _reset_acceleration_helper(self):
   if getattr(self.m.bus,'acceleration_restore',None)is None:
    from acceleration_restore import AccelerationRestore
    self.m.bus.acceleration_restore=AccelerationRestore()
  def failure_hold(self,reason):
   try:return self._failure_hold(reason)
   finally:
    if self.m is not None and getattr(self.m,'safety_recovery_led_off',False):blackout_output(self.m,'recovery_fault')
  def _failure_hold(self,reason):
   if self.auto_id1.active or self.auto_id1.failed:
    self.auto_id1.failure(reason)
    self.fallback_report=dict(attempted=True,confirmed=not self.probe_cleanup_failed,reason=reason,probe_recovery=True)
    self.m.operator_stopped=True;self.m.follow_enabled=False;self.m.held=True;self.m.controller.state='FAULT';return
   if self.needs_return_recovery:
    # Intentional Normal commands invalidate the previous stop-goal proof.
    # Recover exactly once from fresh current feedback, then remain latched.
    self.needs_return_recovery=False
    self.m.operator_stopped=True;self.m.follow_enabled=False;self.m.held=True
    self.m.pending_behavior=None;self.m.pending_happy_from_touch=False
    route=getattr(self.m.controller,'pose_route',None)
    if route is not None:route.cancel()
    self.m.bus.acceleration_restore=None
    self.stop_writer=GroupStop({i:self.m.controller.feedback_window(i)for i in range(1,6)},clock=self.clock);self.writers.append(self.stop_writer)
    self.core.record('RETURN_FAILURE_FRESH_HOLD',reason=reason)
   if self.stop_writer is not None:
    if not self.stop_writer.attempted:
     try:self._safety(lambda:self.stop_writer.recover_after_unstarted_failure(self.m.bus,reason))
     except BaseException as error:self.core.record('PRECOMMIT_RECOVERY_ERROR',reason=repr(error))
    # GroupStop already attempted bounded recovery for every affected ID.
    # Never follow an uncertain damping state with a legacy far-goal write.
    unsafe=sorted(getattr(self.m.bus,'unsafe_damping_axes',()))
    self.fallback_report=dict(attempted=True,confirmed=self.stop_writer.verified,unsafe_ids=unsafe,reason=reason)
    self.m.operator_stopped=True;self.m.follow_enabled=False;self.m.held=True;self.m.controller.state='FAULT'
    self.core.record('TRIAL_RECOVERY_LATCHED',fallback=self.fallback_report);return
   return super().failure_hold(reason)
  def prepare_close(self):
   if self.close_prepared:return
   self.auto_id1.close()
   self.close_prepared=True;w=self.stop_writer
   if w is None or w.restored:return
   if not w.verified or getattr(self.m.bus,'unsafe_damping_axes',()):
    self.core.record('CLOSE_RAM_RESTORE_NOT_SAFE',reason='Unverified active hold; Emergency and readback required');self.save();return
   from normal_gaze_motor import decode_state
   gate=RestorationGate();deadline=self.clock()+4.
   try:
    while self.clock()<deadline:
     rows=[decode_state(i,self.m.bus.read(i,33,38))for i in range(1,6)]
     for row in rows:w.guard_feedback(row)
     if gate.update(rows,self.clock())and all(r['goal_raw']==r['internal_target_raw']for r in rows):
      if not w.restore(True):raise RuntimeError('Original ACC restoration refused')
      self._reset_acceleration_helper();self.core.record('CLOSE_SOURCE_ACC_RESTORED');self.save();return
     time.sleep(.001)
    raise RuntimeError('Stationary hold not confirmed during close; no RAM restore')
   except Exception as e:self.core.record('CLOSE_RAM_RESTORE_FAILED',reason=str(e));self.save()
  def save(self):
   signature=(self.core.phase,len(self.core.events),len(self.packet_events),self.clear_token,tuple(w.restored for w in self.writers))
   if signature==self.trial_save_signature:return
   path=self.session.recorder.out/'CENTRAL_SAFETY.json'
   d=dict(phase=self.core.phase,error=self.core.error,events=self.core.events,stops=self.packet_events,
          reset=getattr(self,'reset_snapshot',None),sensor=getattr(self,'sensor_snapshot',None),fallback=getattr(self,'fallback_report',None))
   d.update(evidence='OFFLINE_SIMULATION'if self.simulation else'PHYSICAL_SUPERVISED_EXPERIMENT_NOT_QUALIFIED',enabled_ids=sorted(self.enabled_ids),id2_contact_recovery=id2_contact_recovery,id2_excess_effort_stop=id2_effort_stop,id1_excess_effort_stop=effort_stop,auto_id1_return=auto_id1_return,auto_probe=dict(active=self.auto_id1.active,phase=self.auto_id1.phase,attempts=self.auto_id1.attempts),tof_isolation=isolate_tof,clearance_method='ID1_bounded_probe_token_other_axes_operator_R'if auto_id1_return else'operator_R_after_removing_foam',physically_qualified=False,strict_brake_criteria_waived_for_trial=True,group_brakes=[w.audit for w in self.writers])
   d['automatic_contact_recovery']=auto_contacts;d['automatic_resume_after_normal']=resume_after_normal
   d['id4_excess_effort_stop']=id4_effort_stop
   d['trigger_event']=self.core.event
   timing=getattr(self,'pipeline_timing',None)
   if timing is not None:d['pipeline_timing']=timing.snapshot()
   if auto_contacts:d['clearance_method']='bounded_per_joint_encoder_progress_probe_not_whole_path_clearance'
   d['id2_context_effort']=dict(enabled=self.id2_context_monitor is not None,stats={}if self.id2_context_monitor is None else self.id2_context_monitor.stats,last={}if self.id2_context_monitor is None else self.id2_context_monitor.last)
   spool=getattr(self.session,'log_spool',None);text=json.dumps(d,indent=2)
   if spool is None:path.write_text(text)
   else:spool.snapshot(path,text)
   self.trial_save_signature=signature
 return TrialAdapter

@contextmanager
def hooks(root,output,config,clock,enabled_ids=(),simulation=False,clearance_proof=None,trial_consent=None,startup_cancelled=None,isolate_tof=False,effort_stop=False,auto_id1_return=False,id2_contact_recovery=False,id2_effort_stop=False,resume_after_normal=False,auto_contacts=False,id4_effort_stop=False,accepted_coordination=False):
 c=trial_consent or(consent()if simulation else None);cls=adapter_class(c,isolate_tof=isolate_tof,effort_stop=effort_stop,auto_id1_return=auto_id1_return,id2_contact_recovery=id2_contact_recovery,id2_effort_stop=id2_effort_stop,resume_after_normal=resume_after_normal,auto_contacts=auto_contacts,id4_effort_stop=id4_effort_stop)
 from bio_inspire.runtime import camera_motor as mod,presentation_led,presentation_tempo
 distance_behavior=import_module('bio_inspire.runtime.distance_behavior')
 import led_ring,physical_distance
 from bio_inspire.runtime.presentation_accepted_20261110 import AcceptedRhythms
 # The original source must be captured before base hooks install their
 # 5-8% wrapper. This file never installs into the ordinary presentation.
 original_led=presentation_led.service_breathing
 trial_driver=led_ring.LedRing if simulation else build_driver(led_ring.LedRing)
 from .tof_isolation import isolated_source_factory,isolated_gate
 from contextlib import ExitStack
 trial_distance=(isolated_source_factory(physical_distance.PhysicalDistance,startup_cancelled)if isolate_tof else build_source_factory(physical_distance.PhysicalDistance,simulation=simulation,external_cancelled=startup_cancelled))
 original_open=mod.open_bus
 def prepared_open():
  if accepted_coordination:
   from .sleepy_matched_native import open_factory
   bus=open_factory(original_open)()
  else:bus=original_open()
  try:
   if not simulation:
    from pathlib import Path
    from .startup import prepare_cold_pid_restore
    from .native_profile import require_default_caps
    require_default_caps(bus)
    profile=json.loads(Path(__file__).with_name('profile.json').read_text())
    bus.experimental_startup_pid_restore=prepare_cold_pid_restore(bus,profile)
   from .close_sync import close_aware_sync
   bus.sync_positions=close_aware_sync(bus.sync_positions,bus)
   return bus
  except BaseException:
   bus.close();raise
 with ExitStack()as extra,patch.object(mod,'open_bus',prepared_open),patch.object(base,'Adapter',cls),base.hooks(root,output,config,clock,enabled_ids=(),simulation=simulation)as sessions:
  from bio_inspire.runtime import automatic_fsm
  from .approach_policy import policy_class,scan_service
  extra.enter_context(patch.object(automatic_fsm,'AutomaticFSM',policy_class(automatic_fsm)))
  from bio_inspire.runtime import yaw_face_scan
  extra.enter_context(patch.object(yaw_face_scan,'service',scan_service(yaw_face_scan)))
  from bio_inspire.runtime import state_rhythms
  from .sleepy_coordination import coordinated_driver,sleepy_setter
  from .interested_coordination import pitch_service
  from bio_inspire.runtime import sleepy_trial
  source_setter=sleepy_trial.set_sleepy_trial
  if accepted_coordination:
   from .sleepy_matched_native import matched_driver,setter,fold_weight
   from .angry_phase_sync import coordinated_route
   from .sleepy_release_probe import fullspan_plan
   from . import auto_release
   from bio_inspire.runtime import angry_approach
   coordinated_driver=matched_driver
   source_setter=setter(source_setter)
   extra.enter_context(patch.object(sleepy_trial,'sleepy_native_fold_weight',fold_weight(sleepy_trial.sleepy_native_fold_weight)))
   extra.enter_context(patch.object(angry_approach,'AngryApproachRoute',coordinated_route(angry_approach.AngryApproachRoute)))
   extra.enter_context(patch.object(auto_release,'ReleasePlan',fullspan_plan(auto_release.ReleasePlan)))
  extra.enter_context(patch.object(state_rhythms,'BodyRhythmDriver',coordinated_driver(state_rhythms.BodyRhythmDriver)))
  extra.enter_context(patch.object(sleepy_trial,'set_sleepy_trial',sleepy_setter(source_setter)))
  extra.enter_context(patch.object(mod.CameraMotor,'_apply_pitch',pitch_service(mod.CameraMotor._apply_pitch)))
  import normal_gaze_motor
  from .restart_settle import wrap_start
  settle_wait=getattr(clock,'advance',time.sleep)if simulation else time.sleep
  import startup_preflight
  from .initial_settle import wrap_preflight
  extra.enter_context(patch.object(startup_preflight,'prepare_operator_start',wrap_preflight(startup_preflight.prepare_operator_start,clock,settle_wait,startup_cancelled or(lambda:False))))
  extra.enter_context(patch.object(normal_gaze_motor.NormalGaze,'start',wrap_start(normal_gaze_motor.NormalGaze.start,clock,settle_wait,startup_cancelled or(lambda:False))))
  if isolate_tof:extra.enter_context(patch.object(distance_behavior,'DistanceGate',isolated_gate(distance_behavior.DistanceGate)))
  if not simulation:
   import physical_button
   from .inputs import SampledButton
   extra.enter_context(patch.object(physical_button,'PhysicalButton',SampledButton))
  original_key=mod.CameraMotor.key;original_owned=mod.CameraMotor._key;original_publish=mod.CameraMotor._publish
  def key(m,k):
   a=m.bus.central_feedback.brake_capture
   if k in(ord('r'),ord('R')):a.queue_clearance();return
   return original_key(m,k)
  def owned(m,k):
   a=m.bus.central_feedback.brake_capture
   if k in(ord('r'),ord('R')):
    with m.lock:token=a.pending_r;a.pending_r=None
    a.in_r_owner=True
    try:a.confirm_clearance(token)
    finally:a.in_r_owner=False
    return
   return original_owned(m,k)
  def publish(m,ms):
   original_publish(m,ms);a=m.bus.central_feedback.brake_capture
   with m.lock:m._view['trial_safety']=dict(phase=a.core.phase,error=a.core.error,enabled_ids=sorted(a.enabled_ids),manual_r=not(auto_id1_return or auto_contacts),clearance_wait=getattr(a,'r_wait',None)is not None,auto_probe=dict(active=a.auto_id1.active,phase=a.auto_id1.phase,attempts=a.auto_id1.attempts,id=getattr(a.auto_id1,'sid',1)),contact_held=not a.id1_contact_released(),clearance_token=(a.core.serial,a.core.hold_epoch)if a.core.phase=='WAIT_CLEARANCE'else None,restart_count=0 if a.restart_gate is None else a.restart_gate.count,restart_token=a.restart_request,tof_quality=getattr(a,'sensor_snapshot',{}).get('quality'),led=dict(getattr(m,'presentation_led_output',{})))
  with patch.object(mod.CameraMotor,'key',key),patch.object(mod.CameraMotor,'_key',owned),patch.object(mod.CameraMotor,'_publish',publish),patch.object(presentation_led,'service_breathing',build_service(original_led)),patch.object(presentation_tempo,'PresentationRhythms',AcceptedRhythms),patch.object(led_ring,'LedRing',trial_driver),patch.object(physical_distance,'PhysicalDistance',trial_distance),patch.object(distance_behavior,'poll_distance',build_recovery_poll(distance_behavior.poll_distance)):
   try:yield sessions
   finally:
    if accepted_coordination and not simulation:
     from .sleepy_matched_native import cleanup_sessions
     cleanup_sessions(original_open,sessions)
