"""Wait for a newly completed ToF frame before the FIRST startup move only.

Retains the initial five-second deadline and all original per-move checks.
No actuator commands and no change to the 120ms freshness limit.
"""
import time

class FirstMotionGate:
 def __init__(self,source,require,wait_new,clock,deadline):
  self.source=source;self.original_require=require;self.wait_new=wait_new;self.clock=clock;self.deadline=deadline;self.first_passed=False
 def require(self):
  if self.first_passed:return self.original_require()
  try:self.original_require()
  except RuntimeError:
   error=(self.source.latest() or {}).get('error')
   if error and error!='invalid measurement':raise
  remaining=self.deadline-self.clock()
  if remaining<=0:raise RuntimeError('ToF: initial readiness deadline expired; no movement')
  self.wait_new(timeout_s=remaining)
  self.original_require();self.first_passed=True

def install():
 import physical_distance as mod
 original=mod.PhysicalDistance
 class StartupDistance(original):
  def wait_first_sample(self,timeout_s=5.):
   if not hasattr(self,'startup_deadline'):self.startup_deadline=time.monotonic()+timeout_s
   return super().wait_first_sample(timeout_s=max(0.,self.startup_deadline-time.monotonic()))
  def wait_new_frame(self,timeout_s):
   sequence=(self.latest() or {}).get('sequence');end=min(self.startup_deadline,time.monotonic()+timeout_s)
   while time.monotonic()<end and not self.stop.is_set():
    sample=self.latest();error=(sample or {}).get('error')
    if error and error!='invalid measurement':raise RuntimeError('ToF: '+error)
    if (sample or {}).get('sequence')!=sequence and mod.distance_input_kind(sample,self.clock())!='fault':return
    self.stop.wait(.002)
   raise RuntimeError('ToF: no new valid startup frame before original deadline')
  def require_fresh(self):
   if not hasattr(self,'first_motion_gate'):
    self.first_motion_gate=FirstMotionGate(self,super().require_fresh,self.wait_new_frame,time.monotonic,self.startup_deadline)
   return self.first_motion_gate.require()
 mod.PhysicalDistance=StartupDistance
