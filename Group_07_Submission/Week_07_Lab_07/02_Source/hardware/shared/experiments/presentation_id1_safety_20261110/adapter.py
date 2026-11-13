"""Process-local bus guard. Never changes accepted runtime files or feedback."""
from contextlib import contextmanager

class SafetyInterrupt(BaseException):
 """Caught only at the UART worker boundary, never by behavior retry handlers."""
 def __init__(self,kind,row=None,reason=None):
  self.kind=kind;self.row=row;self.reason=reason
  super().__init__(reason or kind)

class Adapter:
 def __init__(self,bus):
  self.bus=bus;self.blocked=False;self.latest_goal=None;self.depth=0;self.owner=None
  self.read_original=bus.read;self.write_original=bus.write;self.sync_original=bus.sync_positions;self.close_original=bus.close
  bus.read=self.read;bus.write=self.write;bus.sync_positions=self.sync;bus.close=self.close;bus.id1_safety_adapter=self
 def before_io(self):
  if self.owner is not None and not self.depth:self.owner.poll()
 def read(self,sid,address,count):
  self.before_io()
  return self.read_original(sid,address,count)
 @contextmanager
 def internal(self):
  self.depth+=1;old=getattr(self.bus,'acceleration_restore',None)
  if old is not None:self.bus.acceleration_restore=None
  try:yield
  finally:
   if old is not None:self.bus.acceleration_restore=old
   self.depth-=1
 def write(self,sid,address,data):
  if address not in (40,41,42,46):raise ValueError('Safety version forbids PID/EEPROM and unreviewed writes')
  self.before_io()
  if sid==1 and not self.depth:
   if address==42:self.latest_goal=int.from_bytes(data,'little')
   if self.blocked:return
  return self.write_original(sid,address,data)
 def sync(self,goals,cancelled):
  self.before_io()
  goals=dict(goals)
  if 1 in goals and not self.depth:
   self.latest_goal=goals[1]
   if self.blocked:goals.pop(1)
  if not goals or cancelled():return dict(status='safety_suppressed',verified_ids=[])
  if len(goals)==1:
   sid,q=next(iter(goals.items()));self.write(sid,42,q.to_bytes(2,'little'))
   return dict(status='single_goal_written',verified_ids=[sid])
  return self.sync_original(goals,cancelled)
 def close(self):
  error=None
  try:
   if self.owner is not None:self.owner.cleanup()
  except Exception as e:error=e
  finally:
   try:self.close_original()
   finally:
    if self.owner is not None:self.owner.finish(error)
  if error is not None:raise error
