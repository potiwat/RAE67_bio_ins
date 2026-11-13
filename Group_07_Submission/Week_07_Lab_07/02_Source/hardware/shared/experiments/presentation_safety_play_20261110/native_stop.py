"""Experimental single-owner bounded-axis trajectory cancellation and hold.

Only SRAM40..47. No PID/mode/EEPROM/torque-off/cap writes. Not qualified as
collision protection. Source ACC is restored only after verified standstill.
"""
import time
from write_ack import receive_write_ack

class ResetDeadlineExceeded(RuntimeError):pass

class GroupStop:
 def __init__(self,windows,clock=None,contact_axis=None):
  if set(windows)!=set(range(1,6))or any(not 0<=a<=b<=4095 for a,b in windows.values()):raise ValueError('Five reviewed windows required')
  if contact_axis is not None and(type(contact_axis)is not int or contact_axis not in range(1,6)):raise ValueError('Explicit contact axis must be ID1-5')
  self.contact_axis=contact_axis
  self.windows=dict(windows);self.clock=clock or time.monotonic;self.affected=[];self.original={};self.expected={};self.verified=False;self.restored=False;self.attempted=False
  self.audit=dict(contact_axis=contact_axis,method='EXPERIMENTAL_AXISWISE_NATIVE_RESET_HOLD',writes=[],reads=[],axis_transitions=[],physically_qualified=False)
  self.allow_id1_contact_deflection=False;self.allow_contact_deflection_ids=set();self.poststop_quality_limits={}
 def _travel_valid(self,i,q):
  travel=abs(q-self.reset_q[i])
  if travel<=16:return True
  allowed=(i==1 and self.allow_id1_contact_deflection)or i in self.allow_contact_deflection_ids
  if not self.verified or not allowed:return False
  limit=self.poststop_quality_limits.get(i)
  if i in self.allow_contact_deflection_ids and(type(limit)is not int or limit not in(16,22,34)):return False
  if limit is not None and travel>limit:return False
  evidence=self.audit.setdefault('id'+str(i)+'_contact_deflection',dict(first_seen_s=self.clock(),stop_quality_bound_exceeded=True,physical_cause_not_inferred=True,clearance_proven=False,maximum_travel_ticks=travel))
  evidence['maximum_travel_ticks']=max(evidence['maximum_travel_ticks'],travel)
  return True
 def _read(self,b,i):
  raw=b.read(i,33,38)
  if len(raw)!=38:raise RuntimeError('Incomplete native feedback ID'+str(i))
  q=int.from_bytes(raw[23:25],'little');lo,hi=self.windows[i]
  if raw[0]or raw[32]or raw[7]not in(1,2)or not lo<=q<=hi:raise RuntimeError('Unhealthy/out-of-window ID'+str(i))
  if i in self.original and(raw[11:17]!=self.original[i][11:17]):raise RuntimeError('Speed/aux/cap changed ID'+str(i))
  self.audit['reads'].append(dict(id=i,time_s=self.clock(),ram33_70_hex=raw.hex()))
  return raw
 def _packet(self,b,address,values):
  width=len(next(iter(values.values())))
  if(address,width)not in((40,1),(40,8))or not values or any(i not in self.affected or len(v)!=width for i,v in values.items()):raise ValueError('Only affected-ID native stop frames')
  for i,v in values.items():
   if width==1 and v!=b'\2':raise ValueError('Only damping cancellation')
   if width==8 and(v[0]!=1 or v[4:]!=self.original[i][11:15]or not self.windows[i][0]<=int.from_bytes(v[2:4],'little')<=self.windows[i][1]):raise ValueError('Invalid active-hold frame')
  payload=b''.join(bytes((i,))+v for i,v in sorted(values.items()));body=bytes((254,len(payload)+4,131,address,width))+payload
  packet=b'\xff\xff'+body+bytes((~sum(body)&255,));self.audit['writes'].append(dict(time_s=self.clock(),packet_hex=packet.hex()))
  b.port.reset_input_buffer()
  if b.port.write(packet)!=len(packet):raise RuntimeError('Partial native broadcast; fresh recovery required')
 def _individual(self,b,i,address,data):
  if address not in(40,41):raise ValueError('No unsupported register write')
  body=bytes((i,len(data)+3,3,address))+data;packet=b'\xff\xff'+body+bytes((~sum(body)&255,))
  self.audit['writes'].append(dict(time_s=self.clock(),packet_hex=packet.hex(),individual=True));b.port.reset_input_buffer()
  if b.port.write(packet)!=len(packet):raise RuntimeError('Partial native recovery write')
  try:receive_write_ack(b.port,i,packet)
  except Exception:
   if b.read(i,address,len(data))!=data:raise
   self.audit.setdefault('lost_ack_readback_proof',[]).append(i)
 def _block(self,i,raw):
  goal=int.from_bytes(raw[34:36],'little');q=int.from_bytes(raw[23:25],'little')
  if abs(goal-q)>2 or not self.windows[i][0]<=goal<=self.windows[i][1]:raise RuntimeError('Reset reference unconfirmed ID'+str(i))
  return bytes((1,self.brake_acc[i]))+goal.to_bytes(2,'little')+self.original[i][11:15]
 def _verify(self,b,i):
  raw=self._read(b,i);expected=self.expected[i]
  if raw[7:15]!=expected:raise RuntimeError('Active hold command readback differs ID'+str(i))
  goal=int.from_bytes(expected[2:4],'little');ref=int.from_bytes(raw[34:36],'little')
  lo,hi=self.windows[i]
  if not lo<=ref<=hi or abs(ref-goal)>16:raise RuntimeError('Active hold reference outside transition bound ID'+str(i))
  if not self._travel_valid(i,int.from_bytes(raw[23:25],'little')):raise RuntimeError('Native transition travel bound exceeded ID'+str(i))
  if abs(ref-goal)>2:
   pending=self.audit.setdefault('native_reference_pending',{})
   pending.setdefault(str(i),dict(first_seen_s=self.clock(),goal_raw=goal,internal_target_raw=ref))
  return raw
 def guard_feedback(self,row):
  """Check accepted-hold bounds on every owner sample, without extra UART."""
  i=row['id']
  if i not in self.expected:return
  expected=self.expected[i];goal=int.from_bytes(expected[2:4],'little');lo,hi=self.windows[i]
  valid=(row['mode']==0 and row['status_raw']==0 and row['torque_raw']==1 and
         row['goal_raw']==goal and row['acceleration_raw']==expected[1]and
         row['target_speed_raw']==int.from_bytes(expected[6:8],'little')and
         ('torque_limit_raw'not in row or row['torque_limit_raw']==int.from_bytes(self.original[i][15:17],'little'))and
         lo<=row['position_raw']<=hi and
         lo<=row['internal_target_raw']<=hi and abs(row['internal_target_raw']-goal)<=16)
  if valid:valid=self._travel_valid(i,row['position_raw'])
  if valid:return
  self.verified=False;self.bus.unsafe_damping_axes=set(getattr(self.bus,'unsafe_damping_axes',()))|{i}
  self.audit.setdefault('feedback_envelope_errors',[]).append(dict(id=i,time_s=row.get('time_s',self.clock()),position_raw=row['position_raw'],internal_target_raw=row['internal_target_raw'],goal_raw=row['goal_raw']))
  raise RuntimeError('Accepted stop envelope violated ID'+str(i))
 def _recover(self,b):
  # Every axis gets independent fresh evidence, including axes whose first
  # preflight read failed. Never suppress recovery just because a writer exists.
  unsafe=[]
  for i in range(1,6):
   try:
    raw=self._read(b,i)
    if i not in self.original:
     if raw[7]!=1:raise RuntimeError('Unknown pre-existing damping state')
     self.original[i]=raw
    if i in self.expected and raw[7:15]==self.expected[i]:self._verify(b,i);continue
    stationary=i!=self.contact_axis and raw[7]==1 and raw[25:27]==b'\0\0'and raw[33]==0 and raw[9:11]==raw[34:36]
    if stationary:
     if raw[8]!=self.original[i][8]:raise RuntimeError('Unknown resting ACC')
     if i in self.affected:self.affected.remove(i)
     continue
    if i not in self.affected:self.affected.append(i)
    self.brake_acc.setdefault(i,self.original[i][8]) # conservative source profile if preflight failed
    if raw[8]not in(self.original[i][8],self.brake_acc[i]):raise RuntimeError('Unknown recovery ACC')
    start=self.clock() # before transmission and ACK
    if raw[7]==1:self._individual(b,i,40,b'\2')
    while True:
     raw=self._read(b,i)
     if raw[7]!=2:raise RuntimeError('Damping not confirmed')
     elapsed=self.clock()-start
     if elapsed>.01:
      self.audit.setdefault('recovery_deadline_exceeded_ids',[]).append(i)
      # This is an error salvage, not a timing pass. A fresh bounded reset
      # can still be caught once rather than leaving a loaded joint damping.
      if abs(int.from_bytes(raw[34:36],'little')-int.from_bytes(raw[23:25],'little'))>2:raise RuntimeError('Late and unconfirmed recovery reset')
      break
     if abs(int.from_bytes(raw[34:36],'little')-int.from_bytes(raw[23:25],'little'))<=2:break
    self.reset_q[i]=int.from_bytes(raw[23:25],'little');self.expected[i]=self._block(i,raw)
    self._individual(b,i,40,self.expected[i]);self._verify(b,i)
   except BaseException as e:unsafe.append(i);self.audit.setdefault('recovery_errors',{})[i]=repr(e)
  if unsafe:b.unsafe_damping_axes=set(getattr(b,'unsafe_damping_axes',()))|set(unsafe)
  self.audit['recovery_verified']=not unsafe;self.verified=not unsafe
 def recover_after_unstarted_failure(self,b,reason):
  """The caller's preliminary read/goal validation failed before commit()."""
  if self.attempted:raise RuntimeError('Recovery already belongs to attempted transaction')
  self.attempted=True;self.bus=b;self.reset_q={};self.brake_acc={};self.audit['primary_error']=str(reason)
  self.audit['failed_before_commit']=True;self._recover(b)
  return self.verified
 def commit(self,b,goals,cancelled):
  if self.attempted:raise RuntimeError('Group stop cannot be replayed')
  self.attempted=True;self.bus=b;self.reset_q={};self.brake_acc={};effective=dict(goals)
  try:
   if cancelled():raise RuntimeError('Cancelled before stop')
   for i in range(1,6):
    raw=self._read(b,i)
    if raw[7]!=1:raise RuntimeError('Original active support required')
    self.original[i]=raw
    stationary=i!=self.contact_axis and raw[25:27]==b'\0\0'and raw[33]==0 and raw[9:11]==raw[34:36]
    if stationary:effective[i]=int.from_bytes(raw[9:11],'little')
    else:self.affected.append(i)
   if cancelled():raise RuntimeError('Cancelled before cancellation dispatch')
   # Capture the obstructed joint before healthy moving peers queue UART work.
   # Complete its reset/active hold before damping another loaded axis.
   if self.contact_axis in self.affected:
    self.affected.remove(self.contact_axis);self.affected.insert(0,self.contact_axis)
   self.audit['cancellation_order']=list(self.affected)
   for i in self.affected:
    value={1:0,3:50,4:48}.get(i,self.original[i][8])
    if i in(3,4):
     body=bytes((i,4,2,85,1));p=b'\xff\xff'+body+bytes((~sum(body)&255,));cap=b._read_response(p,i,1)
     if len(cap)!=1 or value>cap[0]:raise RuntimeError('Brake ACC exceeds measured factory limit ID'+str(i))
    self.brake_acc[i]=value
   if not self.affected:self.verified=True;self.restored=True;return dict(status='goal_readback_verified',verified_ids=list(range(1,6)),effective_goals=effective,method='already_stationary_equilibrium_retained')
   for i in self.affected:
    # Do not place every loaded joint in damping while serial reads queue.
    # Complete the same bounded reset/hold transaction on one axis before
    # cancelling the next. Keep the existing 10ms limit; never extend it to
    # hide cumulative bus latency. Refresh the travel origin immediately
    # before cancellation, since the other axes still have active support.
    if cancelled():raise RuntimeError('Cancelled before axis cancellation')
    before=self._read(b,i)
    if before[7]!=1 or before[8]!=self.original[i][8]:raise RuntimeError('Source support/profile changed before cancellation')
    start=self.clock();self.audit.setdefault('damping_begin_s',start)
    transition=dict(id=i,damping_begin_s=start);self.audit['axis_transitions'].append(transition)
    self._packet(b,40,{i:b'\2'})
    while True:
     raw=self._read(b,i);q=int.from_bytes(raw[23:25],'little')
     if raw[7]!=2 or abs(q-int.from_bytes(before[23:25],'little'))>16:raise RuntimeError('Damping/reset travel unconfirmed ID'+str(i))
     if self.clock()-start>.01:raise ResetDeadlineExceeded('Axis reset deadline exceeded ID'+str(i))
     if abs(int.from_bytes(raw[34:36],'little')-q)<=2:break
    self.reset_q[i]=q;self.expected[i]=self._block(i,raw)
    if cancelled():raise RuntimeError('Cancelled during reset; active support recovery required')
    self._packet(b,40,{i:self.expected[i]});transition['position_sent_s']=self.clock()
    if transition['position_sent_s']-start>.01:raise ResetDeadlineExceeded('Axis support dispatch deadline exceeded ID'+str(i))
    self._verify(b,i);transition['verified_s']=self.clock()
   self.verified=True;self.audit['position_restored_s']=self.clock()
  except BaseException as e:
   self.audit['primary_error']=repr(e);self._recover(b)
   # This trial explicitly waives timing qualification, never support proof.
   # A scheduling miss is not permission to clear an uncertain hardware
   # state: independently recover, then verify all five native states and
   # the unchanged bounded travel before allowing STOPPING to confirm still.
   if not isinstance(e,ResetDeadlineExceeded):raise
   self.audit['timing_criterion_met']=False
   if not self.verified or getattr(b,'unsafe_damping_axes',())or cancelled():raise
   uncertain_id=None
   try:
    if set(self.original)!=set(range(1,6)):raise RuntimeError('Incomplete original support evidence')
    for i in range(1,6):
     uncertain_id=i
     raw=self._read(b,i)
     if raw[7]!=1 or abs(int.from_bytes(raw[23:25],'little')-int.from_bytes(self.original[i][23:25],'little'))>16:
      raise RuntimeError('Recovered support/travel bound unconfirmed ID'+str(i))
     if i in self.expected:self._verify(b,i)
     elif raw[7:15]!=self.original[i][7:15]or raw[9:11]!=raw[34:36]:raise RuntimeError('Resting equilibrium changed ID'+str(i))
     uncertain_id=None
    if cancelled():raise RuntimeError('Cancelled after timing recovery')
   except BaseException as proof_error:
    self.audit['timing_recovery_rejected']=repr(proof_error)
    if uncertain_id is not None:
     self.verified=False
     b.unsafe_damping_axes=set(getattr(b,'unsafe_damping_axes',()))|{uncertain_id}
     self.audit.setdefault('unconfirmed_final_proof_ids',[]).append(uncertain_id)
    raise
   self.audit['timing_recovery_support_verified']=True
  for i in self.affected:effective[i]=int.from_bytes(self.expected[i][2:4],'little')
  self.audit.update(affected_ids=self.affected,effective_goals=effective,source_acc={i:r[8]for i,r in self.original.items()},brake_acc=self.brake_acc)
  return dict(status='goal_readback_verified',verified_ids=list(range(1,6)),effective_goals=effective,method=self.audit['method'])
 def restore(self,stationary_confirmed):
  if self.restored:return True
  if stationary_confirmed is not True or not self.verified or getattr(self.bus,'unsafe_damping_axes',()):return False
  for i in self.affected:
   raw=self._verify(self.bus,i)
   # Cached standstill is not a promise that the next native sample is
   # stationary. Keep the unchanged supported brake and await fresh proof;
   # _verify still rejects profile, mode, reference and travel violations.
   if raw[25:27]!=b'\0\0'or raw[33]:return False
   # Command acceptance is not native trajectory completion. Keep active
   # support at the single frozen goal and let the existing owner feedback
   # prove convergence; do not rewrite goals or restore ACC prematurely.
   if abs(int.from_bytes(raw[34:36],'little')-int.from_bytes(self.expected[i][2:4],'little'))>2:return False
  for i in self.affected:
   if self.expected[i][1]!=self.original[i][8]:
    self._individual(self.bus,i,41,self.original[i][8:9]);self.expected[i]=self.expected[i][:1]+self.original[i][8:9]+self.expected[i][2:]
   self._verify(self.bus,i)
  for i in self.affected:
   raw=self._verify(self.bus,i)
   if raw[25:27]!=b'\0\0'or raw[33]or abs(int.from_bytes(raw[34:36],'little')-int.from_bytes(self.expected[i][2:4],'little'))>2:return False
  self.restored=True;self.audit['source_acc_restored']=True;return True
