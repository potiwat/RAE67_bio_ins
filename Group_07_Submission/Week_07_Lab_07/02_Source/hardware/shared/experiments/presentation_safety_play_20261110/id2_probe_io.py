"""Isolated loaded ID2 probe. Retain preload; no encoder-goal rebase.

Normal writes are only goal42 and cap48. Emergency capture is delegated to the
existing verified GroupStop; this module never grants clearance or auto-return.
"""
import math
from normal_gaze_motor import decode_state
from write_ack import receive_write_ack

class LoadedProbeIO:
 def __init__(self,bus,window,cancelled,clock):
  lo,hi=window
  if not 0<=lo<hi<=4095:raise ValueError('Reviewed command window required')
  self.bus=bus;self.window=window;self.feedback_window=(lo,hi);self.cancelled=cancelled;self.clock=clock
  self.anchor_goal=self.anchor_q=self.goal=None;self.original=self.expected=None;self.prepared=False;self.restored=False;self.uncertain_write=False;self.pending=None;self.phase='NEW';self.audit=[];self.still=[];self.abort_adopted=False
 def _decode(self):
  raw=self.bus.read(2,33,38)
  if len(raw)!=38:raise RuntimeError('ID2 native read incomplete')
  r=decode_state(2,raw);r.update(time_s=self.clock(),torque_limit_raw=int.from_bytes(raw[15:17],'little'))
  if r['mode']or r['torque_raw']!=1 or r['status_raw']or r['voltage_V']<6.:raise RuntimeError('ID2 native support/supply fault')
  if any(not self.feedback_window[0]<=r[k]<=self.feedback_window[1]for k in('goal_raw','internal_target_raw','position_raw')):raise RuntimeError('ID2 reviewed feedback window violated')
  if self.anchor_q is not None and abs(r['position_raw']-self.anchor_q)>20:raise RuntimeError('ID2 pinned encoder travel exceeded')
  if abs(r['internal_target_raw']-r['goal_raw'])>16:raise RuntimeError('ID2 native trajectory reference unconfirmed')
  return r,raw
 def read(self):
  if self.uncertain_write:raise RuntimeError('ID2 pending write requires independent stop reconciliation')
  r,raw=self._decode()
  if self.expected is not None and raw[7:17]!=bytes(self.expected[7:17]):raise RuntimeError('ID2 support/profile/goal changed')
  return r,raw
 def _write(self,address,data,recovery=False):
  if not self.prepared or address not in(42,48)or len(data)!=2:raise ValueError('Only scoped ID2 goal/cap writes')
  if self.uncertain_write:raise RuntimeError('ID2 unconfirmed write forbids new probe writes')
  if self.cancelled()and not recovery:raise RuntimeError('ID2 probe cancelled')
  value=int.from_bytes(data,'little')
  if address==42 and(not self.window[0]<=value<=self.window[1]or abs(value-self.anchor_goal)>16):raise RuntimeError('ID2 pinned command excursion')
  if address==48 and value!=(1000 if recovery else 400):raise ValueError('Unreviewed ID2 probe cap')
  self.pending=dict(address=address,value=value,goal=value if address==42 else self.goal,previous_goal=self.goal);self.uncertain_write=True
  body=bytes((2,len(data)+3,3,address))+data;packet=bytes((255,255))+body+bytes((~sum(body)&255,));self.bus.port.reset_input_buffer()
  if self.bus.port.write(packet)!=len(packet):raise RuntimeError('ID2 partial probe write')
  ack_error=None
  try:receive_write_ack(self.bus.port,2,packet)
  except Exception as e:ack_error=str(e)
  r,raw=self._decode();expected=bytearray(self.expected);offset=address-33;expected[offset:offset+2]=data
  if raw[7:17]!=bytes(expected[7:17]):raise RuntimeError('ID2 probe write/readback differs')
  self.expected=expected;self.goal=value if address==42 else self.goal;self.uncertain_write=False;self.pending=None
  if address==42 or not recovery:self.still=[]
  self.audit.append(dict(time_s=self.clock(),id=2,address=address,data_hex=data.hex(),ack_error=ack_error))
 def prepare(self,entry_source=None):
  if self.prepared:raise RuntimeError('ID2 prepare cannot repeat')
  r,raw=self._decode()
  if entry_source is not None and(any(r[k]!=entry_source[k]for k in('mode','torque_raw','status_raw','goal_raw','internal_target_raw','target_speed_raw','acceleration_raw','torque_limit_raw'))or abs(r['position_raw']-entry_source['position_raw'])>2):raise RuntimeError('ID2 source changed since ENTRY')
  if r['goal_raw']!=2835:raise RuntimeError('Authorized diagnostic preload goal2835 required')
  # A loaded joint can hold a verified Normal pose with residual error.
  # Use the existing 34-tick loaded support bound, not the 16-tick command
  # excursion. Absolute feedback/travel windows below remain unchanged.
  if r['speed_raw']or r['moving_raw']or r['internal_target_raw']!=r['goal_raw']or abs(r['position_raw']-r['goal_raw'])>34 or(r['load_raw']&1023)>=300 or r['current_raw']>40 or r['torque_limit_raw']!=1000 or r['target_speed_raw']!=600 or r['acceleration_raw']!=8:raise RuntimeError('ID2 known static source/preload profile required')
  if not self.window[0]<=r['goal_raw']-16<=r['goal_raw']+16<=self.window[1]:raise RuntimeError('ID2 full command space required')
  self.original=raw;self.expected=bytearray(raw);self.anchor_goal=self.goal=r['goal_raw'];self.anchor_q=r['position_raw']if entry_source is None else entry_source['position_raw'];self.prepared=True;self.phase='PREPARING';self._write(48,(400).to_bytes(2,'little'));self.phase='PROBE';return self.read()[0]
 def command(self,goal):
  if not self.prepared or self.restored or self.phase!='PROBE'or type(goal)is not int or abs(goal-self.goal)>1:raise RuntimeError('ID2 one-tick probe command required')
  self.read();self._write(42,goal.to_bytes(2,'little'))
 def _static_ok(self,r):
  try:return(self.prepared and not self.uncertain_write and r['id']==2 and r['mode']==0 and r['torque_raw']==1 and r['status_raw']==0 and r['voltage_V']>=6. and r['goal_raw']==self.goal and r['internal_target_raw']==self.goal and not r['speed_raw']and not r['moving_raw']and r['target_speed_raw']==600 and r['acceleration_raw']==8 and r['torque_limit_raw']==int.from_bytes(self.expected[15:17],'little')and all(self.feedback_window[0]<=r[k]<=self.feedback_window[1]for k in('position_raw','internal_target_raw','goal_raw'))and abs(r['position_raw']-self.anchor_q)<=20 and abs(r['position_raw']-r['goal_raw'])<=34 and(r['load_raw']&1023)<300 and r['current_raw']<=40)
  except(KeyError,TypeError,ValueError):return False
 def observe_still(self,r):
  t=r.get('time_s');now=self.clock()
  if type(t)not in(int,float)or not math.isfinite(t)or not 0<=now-t<=.18 or not self._static_ok(r):self.still=[];return False
  if self.still and t<=self.still[-1][0]:return False
  if self.still and t-self.still[-1][0]>.2:self.still=[]
  self.still.append((t,r['position_raw'],self.goal,self.phase))
  while len(self.still)>4 and t-self.still[1][0]>=.15:self.still.pop(0)
  return len(self.still)>=4 and t-self.still[0][0]>=.15-1e-9 and max(v[1]for v in self.still)-min(v[1]for v in self.still)<=2
 def adopt_stop(self,w):
  from .native_stop import GroupStop
  if not isinstance(w,GroupStop)or w.bus is not self.bus or w.contact_axis!=2 or not w.verified or not w.restored or getattr(self.bus,'unsafe_damping_axes',()):raise RuntimeError('ID2 supported stop proof required')
  old=w.original[2];known={self.goal}
  if self.pending and self.pending['address']==42:known.add(self.pending['goal'])
  if int.from_bytes(old[9:11],'little')not in known or old[0]!=0 or old[7]!=1 or old[8]!=8 or old[11:15]!=self.original[11:15]or int.from_bytes(old[15:17],'little')not in(400,1000):raise RuntimeError('ID2 stop cannot reconcile unknown goal/profile')
  allowed_caps={int.from_bytes(self.expected[15:17],'little')}
  if self.pending and self.pending['address']==48:allowed_caps.add(self.pending['value'])
  if int.from_bytes(old[15:17],'little')not in allowed_caps:raise RuntimeError('ID2 unrecognized cap change before stop')
  r,raw=self._decode();expected=bytearray(old);expected[7:15]=w.expected[2]
  if raw[7:17]!=bytes(expected[7:17])or r['internal_target_raw']!=r['goal_raw']or r['speed_raw']or r['moving_raw']:raise RuntimeError('ID2 captured native support not confirmed')
  self.expected=expected;self.goal=r['goal_raw'];self.uncertain_write=False;self.pending=None;self.still=[];self.phase='ABORT_HELD';self.abort_adopted=True
  self.audit.append(dict(time_s=self.clock(),kind='ID2_SUPPORTED_STOP_ADOPTED_WITHOUT_ENCODER_REBASE',goal=self.goal,pinned_source_goal=self.anchor_goal,pinned_source_encoder=self.anchor_q))
 def restore(self,original_goal=True):
  if self.restored:return
  if not self.prepared or self.uncertain_write:raise RuntimeError('ID2 source restoration lacks known support')
  if original_goal and(self.phase!='PROBE'or self.goal!=self.anchor_goal):raise RuntimeError('ID2 normal restoration requires original preload goal')
  if not original_goal and not(self.phase=='ABORT_HELD'and self.abort_adopted):raise RuntimeError('ID2 abort restoration requires verified captured hold')
  if len(self.still)<4 or self.still[-1][0]-self.still[0][0]<.15-1e-9 or not 0<=self.clock()-self.still[-1][0]<=.18 or any(v[2:]!=(self.goal,self.phase)for v in self.still)or max(v[1]for v in self.still)-min(v[1]for v in self.still)>2:raise RuntimeError('ID2 temporal static support proof missing/stale')
  r,_=self.read()
  if not self._static_ok(r)or abs(r['position_raw']-self.still[-1][1])>2:raise RuntimeError('ID2 fresh static support differs before cap restore')
  if r['torque_limit_raw']!=1000:self._write(48,(1000).to_bytes(2,'little'),recovery=True)
  r,raw=self.read()
  if not self._static_ok(r)or r['torque_limit_raw']!=1000 or abs(r['position_raw']-self.still[-1][1])>2:raise RuntimeError('ID2 source cap restored but static support unconfirmed')
  self.restored=True;self.phase='RESTORED'
