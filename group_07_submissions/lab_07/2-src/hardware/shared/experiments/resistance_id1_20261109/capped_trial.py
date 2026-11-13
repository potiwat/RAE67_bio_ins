"""R4 ID1-only RAM cap + exploratory early contact pause. No PID/EEPROM writes."""
import time
from .pause_guard import ID1PauseGuard
from .native_retry import NativeRetry
from write_ack import receive_write_ack

AUDITS=[]

class EarlyGuard(ID1PauseGuard):
 def __init__(self):super().__init__();self.early_start=None;self.early_stamp=None;self.early_count=0
 def update(self,row,now):
  previous=self.last_stamp;result=super().update(row,now)
  if result['state']!='MONITORING' or row['sampled_monotonic_s']==previous:return result
  t=row['sampled_monotonic_s'];error=abs(row['internal_target_raw']-row['position_raw']);duty=row['load_raw']&1023;current=row['current_raw']
  suspect=(current>=4 and duty>=144 and error>=64) or current>=8
  if not suspect:self.early_start=None;self.early_count=0;return result
  if self.early_start is None:self.early_start=t
  self.early_count+=1
  if self.early_count>=2 and t-self.early_start>=.05-1e-9:
   self.state='RESISTANCE_PAUSE';self.reason='early excess effort/current; no stall requirement'
   return self._result(trip=True)
  return result

class CappedNative(NativeRetry):
 cap_limit=160
 def __init__(self):super().__init__();self.guard=EarlyGuard()
 def step(self,d,m,now):
  super().step(d,m,now)
  if self.samples:self.samples[-1]['cap_audit']=dict(getattr(m.controller.bus,'cap_audit',{}))
 def waiting(self,m,now,reason):
  self.hold(m,now,reason);self.paused=True;self.phase='LATCHED';self.phase_s=now
  self.events.append(dict(event='capped_contact_latched',time_s=now,automatic_retry=False))

class CapSession:
 limit=160
 def __init__(self,bus,ack=receive_write_ack,clock=time.monotonic,pause=time.sleep):
  self.bus=bus;self.ack=ack;self.clock=clock;self.pause=pause;self.active=False;self.closed=False
  self.read=bus.read;self.original_close=bus.close
  self.audit=dict(limit=self.limit,original=None,applied=False,restored=False,restore_error=None)
  block=self.read(1,33,38);self.old=int.from_bytes(block[15:17],'little');self.audit['original']=self.old
  if self.old!=1000 or block[0]!=0 or block[32]!=0 or block[7] not in (0,1) or block[25:27]!=b'\0\0' or block[33]!=0:
   raise RuntimeError('R4 requires known cap1000 and healthy stationary ID1')
 def write_cap(self,value):
  if value not in (self.limit,self.old):raise ValueError('R4 cap value denied')
  body=bytes((1,5,3,48))+int(value).to_bytes(2,'little');packet=b'\xff\xff'+body+bytes((~sum(body)&255,))
  port=self.bus.port;port.reset_input_buffer()
  if port.write(packet)!=len(packet):raise IOError('Partial RAM48 write')
  port.flush();self.ack(port,1,packet)
  if int.from_bytes(self.read(1,33,38)[15:17],'little')!=value:raise RuntimeError('RAM48 readback mismatch')
 def install(self):
  self.write_cap(self.limit);self.active=True;self.audit['applied']=True
  original=self.read
  def read(sid,address,count):
   data=original(sid,address,count)
   if self.active and sid==1 and address==33 and count>=17 and int.from_bytes(data[15:17],'little')!=self.limit:
    raise RuntimeError('ID1 torque cap drift')
   return data
  self.bus.read=read;self.bus.close=self.close;self.bus.cap_audit=self.audit
  return self.bus
 def close(self):
  if self.closed:return
  self.closed=True;self.active=False
  try:
   end=self.clock()+2.;safe=False
   while self.clock()<end:
    b=self.read(1,33,38)
    known=int.from_bytes(b[15:17],'little')==self.limit
    q=int.from_bytes(b[23:25],'little');goal=int.from_bytes(b[9:11],'little')
    safe=(known and b[0]==0 and b[32]==0 and (b[7]==0 or b[7]==1 and b[25:27]==b'\0\0' and b[33]==0 and abs(q-goal)<=4))
    if safe:break
    self.pause(.02)
   if safe:self.write_cap(self.old);self.audit['restored']=True
   else:self.audit['restore_error']='Safe stationary hold unconfirmed; low cap retained'
  except Exception as error:self.audit['restore_error']=str(error)
  finally:
   if self.audit['restore_error']:print('R4_CAP_RESTORE_UNCONFIRMED',self.audit['restore_error'],flush=True)
   self.original_close()

def install(camera_motor_module):
 original=camera_motor_module.open_bus
 def open_capped():
  b=original();session=None
  try:
   session=CapSession(b);AUDITS.append(session.audit);return session.install()
  except BaseException:
   # Never increase a cap after failed setup/unknown WRITE result.
   b.close();raise
 camera_motor_module.open_bus=open_capped
