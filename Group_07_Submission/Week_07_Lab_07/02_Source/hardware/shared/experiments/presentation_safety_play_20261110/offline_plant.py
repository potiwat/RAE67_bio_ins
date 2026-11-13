"""Protocol emulator ONLY: ideal encoder follower, never opens hardware."""
import threading
from collections import deque
from physical_button import BufferedInput

class Clock:
 def __init__(self):self.t=100.
 def __call__(self):return self.t
 def advance(self,dt):self.t+=max(0.,dt)

class Plant:
 def __init__(self,profile,clock):
  self.clock=clock;self.frames=[];self.mutations=[];self.contact=set();self.bad_status={};self.on_packet=None;self.on_readback=None
  self.ram={i:bytearray(80) for i in range(1,6)};self.closed=False;self.drop_responses=0
  for i,a in self.ram.items():
   a[8]=1;a[18]=12;a[21:24]=bytes((profile['startup_pid_by_id'][str(i)]['p'],profile['startup_pid_by_id'][str(i)]['d'],profile['startup_pid_by_id'][str(i)]['i']))
   a[40]=1;a[41]=1;a[46:48]=(600).to_bytes(2,'little');a[48:50]=(1000).to_bytes(2,'little');a[55]=1
   q=profile['normal_raw'][str(i)];a[42:44]=q.to_bytes(2,'little');a[56:58]=q.to_bytes(2,'little');a[62]=72;a[63]=30
 def refresh(self,i):
  a=self.ram[i];goal=int.from_bytes(a[42:44],'little')
  if i not in self.contact:a[56:58]=a[42:44];a[60:62]=(16).to_bytes(2,'little');a[69:71]=(1).to_bytes(2,'little')
  else:
   # Fault injection is above the recorded baseline envelope. This is not a
   # model of real contact force or an assertion of physical sensitivity.
   a[60:62]=(950).to_bytes(2,'little');a[69:71]=(120).to_bytes(2,'little')
  a[58:60]=b'\0\0';a[65]=self.bad_status.get(i,0);a[66]=0
  a[67:69]=((min(4095,goal+200)) if i in self.contact else goal).to_bytes(2,'little')
 def apply(self,i,addr,data):
  if i==4 and addr==40 and len(data)==8 and getattr(self,'allow_id4_active_hold',False):
   if not(data[:2]==b'\1\0'or data[:2]==b'\1\x30'and getattr(self,'allow_id4_acc48',False))or data[4:8]!=self.ram[4][44:48]:raise AssertionError('Unapproved ID4 active-hold block')
   self.ram[4][40:48]=data;self.ram[4][67:69]=data[2:4]
   self.mutations.append(dict(time_s=self.clock(),id=i,address=40,data_hex=data.hex()));return
  if i==3 and addr==40 and len(data)==8 and getattr(self,'allow_id3_active_hold',False):
   allowed=(data[:2]==b'\1\0'or data[:2]==b'\1\xfe'and getattr(self,'allow_id3_acc254',False)or data[:2]==b'\1\x32'and getattr(self,'allow_id3_acc50',False))
   if not allowed or data[4:8]!=self.ram[3][44:48]:raise AssertionError('Unapproved ID3 active-hold block')
   self.ram[3][40:48]=data;self.ram[3][67:69]=data[2:4]
   self.mutations.append(dict(time_s=self.clock(),id=i,address=40,data_hex=data.hex()));return
  if addr not in (40,41,42,46) or addr==40 and data!=b'\1':raise AssertionError('Forbidden PID/EEPROM/mode/torque-off write in emulator')
  self.ram[i][addr:addr+len(data)]=data;self.mutations.append(dict(time_s=self.clock(),id=i,address=addr,data_hex=data.hex()))
 def serial(self,*a,**kw):return Port(self)

class Port:
 def __init__(self,plant):self.plant=plant;self.rx=bytearray();self.last_instruction=None;self.port=None;self.dtr=False;self.rts=False
 def open(self):pass
 def close(self):self.plant.closed=True
 def reset_input_buffer(self):self.rx.clear()
 def flush(self):self.plant.clock.advance(.008)
 @property
 def in_waiting(self):return len(self.rx)
 def read(self,n):
  if not self.rx:self.plant.clock.advance(.001)
  r=bytes(self.rx[:n]);del self.rx[:n];return r
 def reply(self,i,data=b''):
  if self.plant.drop_responses:
   self.plant.drop_responses-=1;return
  body=bytes((i,len(data)+2,0))+bytes(data);self.rx.extend(b'\xff\xff'+body+bytes((~sum(body)&255,)))
 def write(self,data):
  p=bytes(data)
  if p[:2]!=b'\xff\xff' or len(p)!=p[3]+4 or sum(p[2:])&255!=255:raise AssertionError('Malformed protocol frame')
  self.plant.clock.advance(.00064);i=p[2];op=p[4];self.last_instruction=op
  self.plant.frames.append(dict(time_s=self.plant.clock(),packet=list(p),instruction=op))
  if op==2:
   addr,count=p[5:7];self.plant.refresh(i)
   if self.plant.on_readback:self.plant.on_readback(i,addr,count)
   self.reply(i,self.plant.ram[i][addr:addr+count])
  elif op==3:self.plant.apply(i,p[5],p[6:-1]);self.reply(i)
  elif op==131:
   addr,width=p[5:7]
   if i!=254 or (addr,width)not in((42,2),(41,3)):raise AssertionError('Unreviewed broadcast')
   for j in range(7,len(p)-1,width+1):
    sid=p[j]
    if addr==41:
     native3=(sid==3 and getattr(self.plant,'allow_native_id3_brake',False)and self.plant.ram[sid][41]==16 and p[j+1]==0)
     if sid!=4 and not native3 and p[j+1]!=self.plant.ram[sid][41]:raise AssertionError('Unapproved non-ID4 acceleration change')
     self.plant.apply(sid,41,p[j+1:j+2]);self.plant.apply(sid,42,p[j+2:j+4])
    else:self.plant.apply(sid,42,p[j+1:j+3])
  else:raise AssertionError('Unexpected instruction '+str(op))
  if self.plant.on_packet:self.plant.on_packet(op)
  return len(p)

class Input(BufferedInput):
 def __init__(self,debounce=.06):super().__init__(debounce);self.pressed=False
 def refresh(self,now):self.sample(self.pressed,now)
 def close(self):self.discard_pending()

class Distance:
 def __init__(self,clock):self.clock=clock;self.kind='range';self.cm=50.;self.sequence=0
 def latest(self):
  self.sequence+=1;stamp=self.clock()-(.3 if self.kind=='stale'else 0.)
  return dict(distance_cm=self.cm if self.kind=='range'else None,received_s=stamp,error='I2C failure' if self.kind=='hardware_error'else None,
   sequence=self.sequence,measurement_state='range'if self.kind=='range'else 'no_target'if self.kind in('no_target','stale')else'unreliable',range_status_raw=9 if self.kind=='range'else 4 if self.kind in('no_target','stale')else 5)
 def wait_first_sample(self,*a,**kw):pass
 def require_fresh(self):
  if self.kind in ('stale','hardware_error'):raise RuntimeError('Synthetic ToF unavailable')
 def close(self):pass

class Led:
 def show_color(self,*a,**kw):pass
 def close(self):pass
 def __getattr__(self,n):return lambda *a,**kw:None

class PumpEvent:
 def __init__(self,clock,pump):self.clock=clock;self.pump=pump;self.value=False
 def is_set(self):return self.value
 def set(self):self.value=True
 def clear(self):self.value=False
 def wait(self,dt=0):self.clock.advance(max(.001,dt));self.pump();return self.value
