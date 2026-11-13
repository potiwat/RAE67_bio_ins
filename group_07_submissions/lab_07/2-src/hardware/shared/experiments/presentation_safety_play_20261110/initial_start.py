"""GPIO-only initial five-release gate. No motor owner or UART access here."""
import time
from .restart import ButtonRestartGate

def button_source():
 from physical_button import PhysicalButton
 return PhysicalButton(.06)

class InitialButtonStart:
 def __init__(self,factory=button_source):
  self.factory=factory;self.source=None;self.gate=None;self.claimed=False;self.error='';self.released=False
 @property
 def count(self):return 0 if self.gate is None else self.gate.count
 def open(self):
  if self.source is not None or self.claimed or self.error:raise RuntimeError('Initial gate cannot be reopened')
  try:
   self.source=self.factory();diagnostics=self.source.diagnostics();self.gate=ButtonRestartGate(diagnostics)
   self.released=diagnostics.get('stable_pressed')is False
  except Exception as error:
   self.error='Base button unavailable: '+str(error);self.close()
  return self
 def close(self):
  source=self.source;self.source=None
  if source is not None:source.close()
 def filter_key(self,motor,key,visible):
  if motor is not None:
   self.close();self.claimed=True;return key
  if not visible or key in(27,ord('q')):return key
  if self.claimed or self.error:return 255 if key==ord('m')else key
  if key in(ord('h'),ord(' ')):
   if self.source is not None:self.gate=ButtonRestartGate(self.source.diagnostics())
   return key
  if key!=255:return 255 if key==ord('m')else key
  try:
   if self.source is None:raise RuntimeError('Initial input is closed')
   diagnostics=self.source.diagnostics()
   if diagnostics.get('sampler_error'):raise RuntimeError(diagnostics['sampler_error'])
   if 'last_sample_s'in diagnostics:
    stamp=diagnostics['last_sample_s']
    if stamp is None:return key
    now=time.clock_gettime(time.CLOCK_BOOTTIME)if hasattr(time,'CLOCK_BOOTTIME')else time.monotonic()
    if not 0<=now-stamp<=.25:raise RuntimeError('Base-button samples stale')
   if not self.released:
    self.gate=ButtonRestartGate(diagnostics)
    self.released=diagnostics.get('stable_pressed')is False
    return key
   if self.gate.update(diagnostics):
    self.close();self.claimed=True
    return ord('m')
  except Exception as error:
   self.error='Base button start blocked: '+str(error)
   self.close()
  return key

def with_initial_gate(source):
 """Filter initial M before the existing post-Safety restart arbitration."""
 anchor='                trial_button_restart = '
 if source.count(anchor)!=1:raise RuntimeError('Restart key boundary changed')
 return source.replace(anchor,"                key=trial_initial_gate.filter_key(motor,key,cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) >= 1)\n"+anchor)
