"""Prepared ID1 native closed-loop velocity-zero brake; hardware approval required."""
import time
from write_ack import receive_write_ack

class VelocityStop:
 def __init__(self,bus,ack=receive_write_ack,clock=time.monotonic,pause=time.sleep):
  self.bus=bus;self.ack=ack;self.clock=clock;self.pause=pause
  self.audit=dict(original_mode=0,trial_mode=1,restored=True,stop_attempted=False)
 def write(self,address,data):
  if (address,len(data)) not in ((33,1),(41,7)):raise ValueError('Velocity brake register denied')
  body=bytes((1,len(data)+3,3,address))+data;p=bytes((255,255))+body+bytes((~sum(body)&255,))
  port=self.bus.port;port.reset_input_buffer();start=self.clock()
  if port.write(p)!=len(p):raise IOError('Partial velocity brake write')
  self.ack(port,1,p);return dict(address=address,begin_s=start,ack_s=self.clock())
 def stop(self):
  if self.bus.read(1,55,1)!=bytes((1,)) or self.bus.read(1,18,1)!=bytes((12,)):raise RuntimeError('Original phase and locked EEPROM required')
  b=self.bus.read(1,33,38);q=int.from_bytes(b[23:25],'little')
  if b[0]!=0 or b[7]!=1 or b[8]!=3 or b[32]!=0 or int.from_bytes(b[13:15],'little')!=600 or int.from_bytes(b[15:17],'little')!=160 or not self.bus.windows[1][0]<=q<=self.bus.windows[1][1]:raise RuntimeError('Unexpected velocity brake precondition')
  data=bytes((0,))+q.to_bytes(2,'little')+bytes((0,0,0,0));reference=self.clock()
  self.audit.update(restored=False,stop_attempted=True)
  timings=[self.write(41,data),self.write(33,bytes((1,)))]
  b=self.bus.read(1,33,38)
  if b[0]!=1 or b[7]!=1 or b[32]!=0 or b[8:15]!=data:raise RuntimeError('Native velocity-zero readback mismatch')
  return dict(method='native_velocity_zero',hold_goal=q,reference_s=reference,write_flushed_s=None,flush_used=False,timings=timings,register41_47=list(data))
 def restore(self):
  b=self.bus.read(1,33,38);q=int.from_bytes(b[23:25],'little')
  if self.bus.read(1,55,1)!=bytes((1,)) or b[0]!=1 or b[7] not in (1,2) or b[32]!=0 or b[25:27]!=bytes((0,0)) or int.from_bytes(b[15:17],'little')!=160 or not self.bus.windows[1][0]<=q<=self.bus.windows[1][1]:raise RuntimeError('Stationary native speed-zero hold required before mode restore')
  self.write(41,bytes((0,))+q.to_bytes(2,'little')+bytes((0,0,0,0)))
  self.write(33,bytes((0,)));b=self.bus.read(1,33,38)
  if b[0]!=0 or abs(int.from_bytes(b[23:25],'little')-q)>4 or int.from_bytes(b[9:11],'little')!=q:raise RuntimeError('Position mode capture unconfirmed')
  if b[7]==2:self.bus.hold_actual(1);self.bus.armed.add(1);self.bus.write(1,40,bytes((1,)))
  self.bus.write(1,41,bytes((3,)));self.bus.write(1,46,(600).to_bytes(2,'little'))
  end=self.clock()+2.;since=None
  while self.clock()<end:
   b=self.bus.read(1,33,38);actual=int.from_bytes(b[23:25],'little')
   good=(b[0]==0 and b[7]==1 and b[32]==0 and b[25:27]==bytes((0,0)) and not b[33] and b[8]==3 and int.from_bytes(b[13:15],'little')==600 and abs(actual-q)<=4 and int.from_bytes(b[34:36],'little')==q)
   if good:
    if since is None:since=self.clock()
    if self.clock()-since>=.15:self.audit['restored']=True;return
   else:since=None
   self.pause(.02)
  raise RuntimeError('Original stationary position mode not confirmed')
