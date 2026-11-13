"""Authorized ID1 volatile phase-bit test. No EEPROM unlock or PID writes."""
import time
from write_ack import receive_write_ack
from .damping_brake import _write

class PhaseStop:
 def __init__(self,bus,ack=receive_write_ack,clock=time.monotonic):
  self.bus=bus;self.ack=ack;self.clock=clock
  self.audit=dict(original=12,trial=4,lock_required=1,applied=False,restored=False)
  if bus.read(1,18,1)!=bytes((12,)) or bus.read(1,55,1)!=bytes((1,)):
   raise RuntimeError('Unknown phase or unlocked EEPROM; no phase writes permitted')
 def healthy(self,b):
  q=int.from_bytes(b[23:25],'little')
  return (len(b)==38 and b[0]==0 and b[7]==1 and b[32]==0
          and int.from_bytes(b[15:17],'little')==160 and self.bus.windows[1][0]<=q<=self.bus.windows[1][1])
 def settled(self,b):
  q=int.from_bytes(b[23:25],'little');g=int.from_bytes(b[9:11],'little')
  return (self.healthy(b) and not b[33] and b[25:27]==bytes((0,0)) and abs(q-g)<=4
          and int.from_bytes(b[34:36],'little')==g and b[8]==3 and int.from_bytes(b[13:15],'little')==600)
 def apply(self):
  if self.bus.read(1,55,1)!=bytes((1,)) or self.bus.read(1,18,1)!=bytes((12,)) or not self.settled(self.bus.read(1,33,38)):
   raise RuntimeError('Phase change requires fresh stationary original configuration')
  _write(self.bus,18,bytes((4,)),self.ack,self.clock)
  if self.bus.read(1,18,1)!=bytes((4,)) or self.bus.read(1,55,1)!=bytes((1,)):raise RuntimeError('Trial phase readback mismatch')
  self.audit['applied']=True
 def stop(self):
  if not self.audit['applied'] or self.bus.read(1,18,1)!=bytes((4,)) or self.bus.read(1,55,1)!=bytes((1,)):
   raise RuntimeError('Never issue speed zero without verified phase4 and lock1')
  b=self.bus.read(1,33,38);q=int.from_bytes(b[23:25],'little')
  if not self.healthy(b) or b[8]!=3 or int.from_bytes(b[13:15],'little')!=600:raise RuntimeError('Unexpected pre-stop configuration')
  data=bytes((0,))+q.to_bytes(2,'little')+bytes((0,0,0,0))
  begin,sent,acked=_write(self.bus,41,data,self.ack,self.clock)
  if self.bus.read(1,33,38)[8:15]!=data:raise RuntimeError('Zero-speed stop readback mismatch')
  return dict(hold_goal=q,write_begin_s=begin,write_flushed_s=sent,ack_s=acked,readback_s=self.clock(),register41_47=list(data),pre_feedback=list(b),method='phase4_speed_zero')
 def restore(self):
  p=self.bus.read(1,18,1)
  if p not in (bytes((4,)),bytes((12,))) or self.bus.read(1,55,1)!=bytes((1,)) or not self.settled(self.bus.read(1,33,38)):
   raise RuntimeError('Phase restore requires healthy stopped hold and original run parameters')
  if p==bytes((4,)):_write(self.bus,18,bytes((12,)),self.ack,self.clock)
  if self.bus.read(1,18,1)!=bytes((12,)):raise RuntimeError('Original phase restore unconfirmed')
  self.audit['restored']=True
