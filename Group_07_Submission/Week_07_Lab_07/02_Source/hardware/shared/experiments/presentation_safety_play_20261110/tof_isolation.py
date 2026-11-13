"""Opt-in ToF degradation isolation. Missing range is NEVER clearance.

Manual R supplies the independent operator path confirmation. Confirmed Near
still vetoes return until a real clear frame; native motor faults stay global.
"""
from physical_distance import distance_input_kind
from shared.experiments.central_safety_controller_20261110.supervisor import Supervisor

class IsolatedDistancePolicy:
 def __init__(self):self.near=False;self.last_clear_s=None
 def update(self,sample,now,returning=False):
  sample=sample or {};kind=distance_input_kind(sample,now)
  if kind=='range':
   self.near=sample['distance_cm']<28.
   if not self.near:self.last_clear_s=sample['received_s']
  elif kind=='no_target':self.near=False;self.last_clear_s=sample['received_s']
  available=kind in ('range','no_target')
  return dict(state='near'if self.near else'clear'if available else'unavailable',
   quality=kind if available else'unavailable_'+kind,kind=kind,
   last_confirmed_clear_s=self.last_clear_s,observed_s=now,sample=sample,
   protection_available=available,operator_confirmation_required=True)

def isolated_gate(original):
 from .range_conditioning import behavior_frame
 class Gate(original):
  def step(self,sample,now):
   # Retain positive Near evidence; neither missing nor ambiguous input
   # generates a fake Clear or whole-motor fault.
   if distance_input_kind(sample,now)not in('range','no_target'):return None
   return super().step(behavior_frame(sample),now)
 return Gate

def isolated_source_factory(factory,cancelled=None):
 def create(*args,**kwargs):
  def check():
   if cancelled is not None and cancelled():raise RuntimeError('Startup cancelled')
  check();source=factory(*args,**kwargs)
  # The worker remains the original physical producer. No sample replacement,
  # fabricated heartbeat, blocking I2C access, or motor access in these checks.
  def available(*args,**kwargs):
   check()
   if getattr(source,'stop',None)is not None and source.stop.is_set():raise RuntimeError('Distance source is closing')
  source.wait_first_sample=available;source.require_fresh=available
  return source
 return create

class IsolatedSupervisor(Supervisor):
 """Same motor stop/reset sequence; ToF availability is not a motor fault."""
 def _step(self):
  if self.pending:
   e=self.pending;self.pending=None
   if e['kind']=='close':self.phase='CLOSED';self.record('CLOSED');return
   if e['kind']in('hardware_fault','operator_stop'):
    self.allow_return=False;self.event=e;self._start_hold(False)
   else:
    self.serial+=1;self.event=dict(e,serial=self.serial)
    self.allow_return=e['kind']in('resistance','test_stop')or bool(getattr(self.a,'allow_feedback_gap_recovery',lambda event:False)(self.event))
    self._start_hold(True)
  if self.phase in('PLAY','CLOSED','LATCHED'):return
  sensor=self.a.sensor_state()
  if self.phase=='STOPPING'and not self.hold_sent:
   self.hold_sent=True;self.a.hold(self.hold_epoch);self.record('HOLD_SENT',epoch=self.hold_epoch)
  permitted=sensor in('clear','unavailable')and self.a.clearance_verified(self.event)
  if self.phase=='RETURNING'and not permitted:
   self.record('RETURN_PAUSED',reason=sensor);self._start_hold(False)
   self.hold_sent=True;self.a.hold(self.hold_epoch);self.record('HOLD_SENT',epoch=self.hold_epoch);return
  self.a.tick_feedback()
  if not self.a.healthy():
   self.error='Native feedback fault';self.phase='LATCHED';self.record('FAULT_LATCHED');return
  if self.phase=='STOPPING'and self.a.clock()-self.hold_started>8. and not self.a.stopped():
   self.error='Stop not confirmed within 8 seconds';self.phase='LATCHED';self.record('STOP_NOT_CONFIRMED');return
  if self.phase=='STOPPING'and self.a.stopped():
   if not self.allow_return:self.phase='LATCHED';self.record('OPERATOR_OR_FAULT_LATCHED');return
   if not self.reset_done:self.a.reset();self.reset_done=True;self.record('MODELS_RESET')
   self.phase='WAIT_CLEARANCE'
  elif self.phase=='WAIT_CLEARANCE':
   if self.a.stopped()and self.a.sensor_state()in('clear','unavailable')and self.a.clearance_verified(self.event):
    self.a.return_normal();self.phase='RETURNING';self.record('NORMAL_RETURN_STARTED')
  elif self.phase=='RETURNING'and self.a.normal_complete()and self.a.stopped():
   self.a.park();self.phase='NORMAL_PARKED';self.record('NORMAL_PARKED')
