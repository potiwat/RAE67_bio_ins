"""ID1-only supervised hardware-ramp baseline. No SPI, GPIO or EEPROM writes."""
from dataclasses import dataclass
from pathlib import Path
import sys,time,math
if not Path(__file__).with_name('read_only_bus.py').exists():
 sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'calibration_readonly'))
from read_only_bus import ReadOnlyBus,READS

EXTRA_READS={(18,1),(41,1),(42,2),(46,2),(64,1)}
POSITION_TOLERANCE=6
MONITOR_ALLOWANCE=11

@dataclass(frozen=True)
class TrialConfig:
 delta_deg:float
 speed_raw:int
 acceleration_raw:int
 def __post_init__(self):
  if not math.isfinite(self.delta_deg) or not 0<self.delta_deg<=3:raise ValueError('This baseline only supports positive excursions up to 3 degrees')
  if type(self.speed_raw) is not int or self.speed_raw!=1:raise ValueError('Only reviewed minimum nonzero speed=1')
  if type(self.acceleration_raw) is not int or self.acceleration_raw!=1:raise ValueError('Only reviewed minimum nonzero acceleration=1')
 @property
 def ticks(self):return round(self.delta_deg*4096/360)

def write_packet(sid,address,payload,window):
 payload=bytes(payload)
 if sid!=1:raise ValueError('This test only writes ID1')
 if address==42:
  if len(payload)!=2 or window is None or not window[0]<=int.from_bytes(payload,'little')<=window[1]:raise ValueError('Goal outside locked window')
 elif address==40:
  if payload not in (b'\0',b'\1'):raise ValueError('Only torque OFF/ON; no calibration command')
 elif address==41:
  if payload!=b'\1':raise ValueError('Only acceleration=1')
 elif address==46:
  if payload!=b'\1\0':raise ValueError('Only speed=1')
 else:raise ValueError('Register not authorized for baseline')
 body=bytes([sid,len(payload)+3,3,address])+payload
 return b'\xff\xff'+body+bytes([~sum(body)&255])

class BaselineBus(ReadOnlyBus):
 def __init__(self):
  super().__init__();self.window=None;self.enable_checked=False
 def read(self,sid,address,count):
  if sid not in (1,2,3,4,5) or (address,count) not in READS|EXTRA_READS:raise ValueError('Read denied')
  body=bytes([sid,4,2,address,count])
  return self._read_response(b'\xff\xff'+body+bytes([~sum(body)&255]),sid,count)
 def _verified_write(self,packet,address,payload):
  self.port.reset_input_buffer();self.port.write(packet);self.port.flush()
  if self.read(1,address,len(payload))!=bytes(payload):raise RuntimeError(f'ID1 register {address} readback mismatch')
 def write_register(self,address,payload):
  packet=write_packet(1,address,payload,self.window)
  if address==40 and payload==b'\1' and not self.enable_checked:raise RuntimeError('Cannot enable before verified fresh hold')
  self._verified_write(packet,address,payload)
  if address==40 and payload==b'\0':self.enable_checked=False
 def feedback(self):
  d=self.read(1,56,8);s=self.read(1,65,2)
  return dict(position_raw=int.from_bytes(d[:2],'little'),speed_raw=int.from_bytes(d[2:4],'little'),load_raw=int.from_bytes(d[4:6],'little'),voltage_V=d[6]/10,temperature_C=d[7],status_raw=s[0],moving_raw=s[1],torque_raw=self.read(1,40,1)[0])
 def hold_actual(self):
  fb=self.feedback();p=fb['position_raw']
  if not 0<=p<=4095:raise RuntimeError('Invalid actual position; no guessed hold')
  data=p.to_bytes(2,'little')
  self._verified_write(write_packet(1,42,data,(p,p)),42,data)
  return fb

class BaselineSession:
 def __init__(self,bus,config,event=None):
  self.bus=bus;self.config=config;self.event=event or (lambda *a,**k:None)
  self.state='IDLE';self.base=None;self.target=None;self.goal=None;self.may_be_enabled=False;self.stable=0;self.deadline=None;self.samples=[];self.last_error=None
 def arm(self):
  rows=self.bus.snapshot()
  if [r['id'] for r in rows]!=[1,2,3,4,5]:raise RuntimeError('Incomplete snapshot')
  if any(r['mode']!=0 or r['torque_raw'] not in ((0,1) if r['id']==1 else (0,)) or r['status_raw']!=0 or not 0<=r['position_raw']<=4095 for r in rows):raise RuntimeError('Inspect mode/torque/status first; this tool will not change other joints')
  if self.bus.read(1,18,1)!=b'\x0c' or self.bus.read(1,64,1)!=b'\0':raise RuntimeError('Phase or pending-write flag differs')
  fresh_start=self.bus.feedback()
  self.base=fresh_start['position_raw'];self.target=self.base+self.config.ticks
  if fresh_start['status_raw'] or fresh_start['torque_raw'] not in (0,1):raise RuntimeError('Unexpected start state')
  if fresh_start['torque_raw']==1 and abs(int.from_bytes(self.bus.read(1,42,2),'little')-self.base)>6:raise RuntimeError('Existing active goal is not a verified nearby hold')
  # Operator-observed ID1 endpoints only; not certification for all poses.
  if not 693<self.base<self.target<2969:raise RuntimeError('Trial outside interior of prior ID1 observations')
  self.bus.window=(self.base,self.target)
  self.event('preflight',before=rows,base_raw=self.base,target_raw=self.target,config=self.config.__dict__)
  # Goal writes/settings may activate holding on actual firmware: latch a
  # fresh no-displacement goal FIRST and conservatively track possible torque.
  self.may_be_enabled=True
  self.bus.write_register(42,self.base.to_bytes(2,'little'))
  self.bus.write_register(46,self.config.speed_raw.to_bytes(2,'little'))
  self.bus.write_register(41,bytes([self.config.acceleration_raw]))
  fresh=self.bus.feedback()
  if abs(fresh['position_raw']-self.base)>2 or fresh['torque_raw'] not in (0,1) or fresh['status_raw']!=0:raise RuntimeError(f'Arming changed: base={self.base}, fresh={fresh}')
  if int.from_bytes(self.bus.read(1,42,2),'little')!=self.base:raise RuntimeError('Fresh hold not verified')
  self.bus.enable_checked=True;self.may_be_enabled=True
  self.bus.write_register(40,b'\1');self.goal=self.base;self.state='ARMED'
  self.event('ID1_ENABLED_AT_FRESH_HOLD',position_raw=self.base)
 def begin(self,now):
  if self.state!='ARMED':raise RuntimeError('Not armed')
  self.bus.write_register(42,self.target.to_bytes(2,'little'));self.goal=self.target;self.state='OUTWARD';self.deadline=now+8.;self.stable=0
  self.event('OUTWARD_GOAL_SENT_ONCE',goal_raw=self.goal)
 def tick(self,now):
  if self.state not in ('OUTWARD','RETURN','HOLDING'):return None
  try:
   fb=self.bus.feedback();row=dict(time_s=now,state=self.state,goal_raw=self.goal,**fb);
   if self.state!='HOLDING':self.samples.append(row);self.event('feedback',**row)
   if fb['status_raw']!=0 or fb['torque_raw']!=1:raise RuntimeError('ID1 status or torque changed')
   if not self.base-MONITOR_ALLOWANCE<=fb['position_raw']<=self.target+MONITOR_ALLOWANCE:raise RuntimeError('Actual position escaped trial monitoring envelope')
   if self.state=='HOLDING':return fb
   if now>self.deadline:raise RuntimeError('Endpoint did not settle within 8 seconds; inspect rather than enlarge guard')
   arrived=abs(fb['position_raw']-self.goal)<=POSITION_TOLERANCE and fb['moving_raw']==0 and fb['speed_raw']==0
   self.stable=self.stable+1 if arrived else 0
   if self.stable>=3:
    if self.state=='OUTWARD':
     self.bus.write_register(42,self.base.to_bytes(2,'little'));self.goal=self.base;self.state='RETURN';self.deadline=now+8.;self.stable=0;self.event('RETURN_GOAL_SENT_ONCE',goal_raw=self.base)
    else:self.state='HOLDING';self.event('CYCLE_RETURNED',position_raw=fb['position_raw'],residual_raw=fb['position_raw']-self.base)
   return fb
  except Exception as e:self.stop(str(e));return None
 def stop(self,reason):
  self.last_error=reason
  if not self.may_be_enabled:self.state='STOPPED_TORQUE_OFF';self.event('STOPPED_BEFORE_ENABLE',reason=reason);return
  try:
   fb=self.bus.hold_actual()
   if fb['torque_raw']==0:self.state='STOPPED_TORQUE_OFF';self.may_be_enabled=False
   elif fb['torque_raw']==1:self.state='STOPPED_HOLDING'
   else:self.state='STOPPED_UNCONFIRMED'
   self.event(self.state,reason=reason,feedback=fb)
  except Exception as e:self.state='STOPPED_UNCONFIRMED';self.event('STOPPED_UNCONFIRMED',reason=reason,hold_error=str(e))
 def release(self):
  self.bus.write_register(40,b'\0');self.may_be_enabled=False;self.state='RELEASED';self.event('ID1_RELEASED_BY_OPERATOR')
