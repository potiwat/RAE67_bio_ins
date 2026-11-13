"""State-independent safety sequence. No serial/GPIO or physical thresholds."""
class Supervisor:
 PRIORITY={'close':0,'hardware_fault':1,'operator_stop':2,'resistance':3,'test_stop':4,'feedback_gap':5}
 def __init__(self,adapter):
  self.a=adapter;self.phase='PLAY';self.pending=None;self.event=None;self.serial=0;self.hold_epoch=0
  self.hold_sent=False;self.reset_done=False;self.allow_return=False;self.error=None;self.events=[]
 def record(self,name,**values):self.events.append(dict(event=name,phase=self.phase,time_s=getattr(self.a,'clock',lambda:None)(),**values))
 def request(self,kind,axis=None):
  if kind not in self.PRIORITY:raise ValueError('Unknown safety event')
  if axis is not None and (type(axis)is not int or axis not in range(1,6)):raise ValueError('Expected ID1-5')
  if self.phase in ('LATCHED','CLOSED','NORMAL_PARKED') and kind not in ('close','hardware_fault','operator_stop'):return False
  if self.phase not in ('PLAY','RETURNING') and kind not in ('close','hardware_fault','operator_stop'):return False
  if self.pending and self.PRIORITY[kind]>=self.PRIORITY[self.pending['kind']]:return False
  self.pending=dict(kind=kind,axis=axis);return True
 def _start_hold(self,reset):
  self.hold_epoch+=1;self.hold_sent=False;self.phase='STOPPING'
  self.hold_started=getattr(self.a,'clock',lambda:0.)()
  if reset:self.reset_done=False
 def step(self):
  try:self._step()
  except Exception as error:
   self.error=str(error);self.phase='LATCHED';self.record('RECOVERY_ERROR',error=self.error)
   fallback=getattr(self.a,'failure_hold',None)
   if fallback is not None:fallback(self.error)
 def _step(self):
  if self.pending:
   e=self.pending;self.pending=None
   if e['kind']=='close':self.phase='CLOSED';self.record('CLOSED');return
   if e['kind'] in ('hardware_fault','operator_stop'):
    self.allow_return=False;self.event=e;self._start_hold(False)
   else:
    self.serial+=1;self.event=dict(e,serial=self.serial);self.allow_return=e['kind']in('resistance','test_stop')
    self._start_hold(True)
  if self.phase in ('PLAY','CLOSED'):return
  if self.phase=='LATCHED':return
  sensor=self.a.sensor_state()
  if sensor=='hardware_fault':
   self.allow_return=False
   if self.phase!='STOPPING':self._start_hold(False)
  if self.phase=='STOPPING' and not self.hold_sent:
   self.hold_sent=True;self.a.hold(self.hold_epoch);self.record('HOLD_SENT',epoch=self.hold_epoch)
  # Never advance a return trajectory through an unknown/near sensor frame.
  if self.phase=='RETURNING' and (sensor!='clear' or not self.a.clearance_verified(self.event)):
   self.record('RETURN_PAUSED',reason=sensor);self._start_hold(False)
   self.hold_sent=True;self.a.hold(self.hold_epoch);self.record('HOLD_SENT',epoch=self.hold_epoch);return
  self.a.tick_feedback()
  if not self.a.healthy():
   self.error='Native feedback fault';self.phase='LATCHED';self.record('FAULT_LATCHED');return
  if self.phase=='STOPPING' and getattr(self.a,'clock',lambda:0.)()-self.hold_started>8. and not self.a.stopped():
   self.error='Stop not confirmed within 8 seconds';self.phase='LATCHED';self.record('STOP_NOT_CONFIRMED');return
  if self.phase=='STOPPING' and self.a.stopped():
   if not self.allow_return:self.phase='LATCHED';self.record('OPERATOR_OR_FAULT_LATCHED');return
   if not self.reset_done:self.a.reset();self.reset_done=True;self.record('MODELS_RESET')
   self.phase='WAIT_CLEARANCE'
  elif self.phase=='WAIT_CLEARANCE':
   if self.a.stopped() and self.a.sensor_state()=='clear' and self.a.clearance_verified(self.event):
    self.a.return_normal();self.phase='RETURNING';self.record('NORMAL_RETURN_STARTED')
  elif self.phase=='RETURNING' and self.a.normal_complete() and self.a.stopped():
   self.a.park();self.phase='NORMAL_PARKED';self.record('NORMAL_PARKED')
