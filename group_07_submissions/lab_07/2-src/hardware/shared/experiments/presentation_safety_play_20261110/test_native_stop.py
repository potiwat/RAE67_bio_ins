import unittest
from types import SimpleNamespace as NS
from .native_stop import GroupStop

class Port:
 def __init__(self,b):self.b=b;self.rx=bytearray()
 def reset_input_buffer(self):self.rx.clear()
 def read(self,n):r=bytes(self.rx[:n]);del self.rx[:n];return r
 @property
 def in_waiting(self):return len(self.rx)
 def write(self,p):
  p=bytes(p);self.b.frames.append(p)
  assert sum(p[2:])&255==255
  if p[4]==131:
   a,w=p[5:7]
   for j in range(7,len(p)-1,w+1):self.b.apply(p[j],a,p[j+1:j+1+w])
  else:
   i=p[2];self.b.apply(i,p[5],p[6:-1]);body=bytes((i,2,0));self.rx+=b'\xff\xff'+body+bytes((~sum(body)&255,))
  return len(p)

class Bus:
 def __init__(self):
  self.ram={i:bytearray(80)for i in range(1,6)};self.frames=[];self.port=Port(self);self.fail_reads=0;self.t=10.
  for i,a in self.ram.items():
   q=3000 if i==3 else 2000;a[40]=1;a[41]={1:8,2:1,3:16,4:24,5:1}[i];a[46:48]=(1000).to_bytes(2,'little');a[48:50]=(1000).to_bytes(2,'little')
   a[56:58]=q.to_bytes(2,'little');a[42:44]=(q+100).to_bytes(2,'little');a[67:69]=(q+60).to_bytes(2,'little');a[58:60]=(500).to_bytes(2,'little');a[66]=1
  # Already resting under load: preserve this command, not sagged encoder.
  a=self.ram[2];a[42:44]=(1970).to_bytes(2,'little');a[67:69]=a[42:44];a[58:60]=b'\0\0';a[66]=0
 def clock(self):self.t+=.0001;return self.t
 def apply(self,i,address,data):
  a=self.ram[i];a[address:address+len(data)]=data
  if address==40 and data==b'\2':a[67:69]=a[56:58]
  if address==40 and len(data)==8:a[67:69]=a[42:44];a[58:60]=b'\0\0';a[66]=0
 def read(self,i,a,n):
  self.clock()
  if self.fail_reads:self.fail_reads-=1;raise OSError('injected read loss')
  return bytes(self.ram[i][a:a+n])
 def _read_response(self,packet,sid,count):
  assert packet[4:7]==bytes((2,85,1));return b'\x32'

class Tests(unittest.TestCase):
 def test_fresh_movement_during_restore_is_pending_without_profile_write_or_fault(self):
  b,w,g=self.fixture();w.commit(b,g,lambda:False);before=len(b.frames)
  b.ram[1][58:60]=(50).to_bytes(2,'little')
  self.assertFalse(w.restore(True));self.assertTrue(w.verified);self.assertFalse(w.restored);self.assertEqual(len(b.frames),before)
  b.ram[1][58:60]=bytes(2)
  self.assertTrue(w.restore(True));self.assertTrue(w.restored)
 def test_verified_id1_contact_deflection_is_not_an_unknown_command_fault(self):
  from normal_gaze_motor import decode_state
  b,w,g=self.fixture();w.allow_id1_contact_deflection=True;w.commit(b,g,lambda:False)
  b.ram[1][56:58]=(w.reset_q[1]-17).to_bytes(2,'little')
  row=decode_state(1,b.read(1,33,38));w.guard_feedback(row)
  self.assertTrue(w.verified);self.assertFalse(getattr(b,'unsafe_damping_axes',set()))
  self.assertTrue(w.audit['id1_contact_deflection']['stop_quality_bound_exceeded'])
  b.ram[1][42:44]=(row['goal_raw']+1).to_bytes(2,'little')
  with self.assertRaisesRegex(RuntimeError,'envelope'):w.guard_feedback(decode_state(1,b.read(1,33,38)))
 def test_acc_restoration_rechecks_native_convergence_before_release(self):
  b,w,g=self.fixture();w.commit(b,g,lambda:False);apply=b.apply
  def pending_after_acc(i,a,data):
   apply(i,a,data)
   if i==3 and a==41:
    b.ram[i][67:69]=(int.from_bytes(b.ram[i][42:44],'little')+3).to_bytes(2,'little')
  b.apply=pending_after_acc
  self.assertFalse(w.restore(True));self.assertFalse(w.restored)
  count=len(b.frames);b.ram[3][67:69]=b.ram[3][42:44]
  self.assertTrue(w.restore(True));self.assertEqual(len(b.frames),count)
 def test_accepted_hold_can_have_a_bounded_pending_internal_reference(self):
  b,w,g=self.fixture();apply=b.apply
  def pending(i,a,data):
   apply(i,a,data)
   if i==3 and a==40 and len(data)==8:
    b.ram[i][67:69]=(int.from_bytes(data[2:4],'little')+3).to_bytes(2,'little')
  b.apply=pending
  report=w.commit(b,g,lambda:False)
  self.assertEqual(report['status'],'goal_readback_verified')
  frames=len(b.frames)
  self.assertFalse(w.restore(True)) # no return/ACC restore while ref is pending
  self.assertEqual(len(b.frames),frames)
  b.ram[3][67:69]=b.ram[3][42:44]
  self.assertTrue(w.restore(True))
  self.assertTrue(w.audit['native_reference_pending'])
 def test_pending_internal_reference_does_not_allow_bad_control_or_far_ref(self):
  for fault in ('goal','reference'):
   b,w,g=self.fixture();apply=b.apply
   def invalid(i,a,data):
    apply(i,a,data)
    if i==3 and a==40 and len(data)==8:
     address=42 if fault=='goal'else 67
     b.ram[i][address:address+2]=(int.from_bytes(data[2:4],'little')+30).to_bytes(2,'little')
   b.apply=invalid
   with self.subTest(fault=fault),self.assertRaises(RuntimeError):w.commit(b,g,lambda:False)
   self.assertFalse(w.verified);self.assertIn(3,b.unsafe_damping_axes)
 def test_five_axis_read_latency_does_not_leave_all_axes_in_damping(self):
  b,w,g=self.fixture();read=b.read
  # Real return-stop failure: five ~2.5ms reads exceed the *group* 10ms
  # budget although each axis can be captured and supported in <10ms.
  def delayed(i,a,n):b.t+=.0025;return read(i,a,n)
  b.read=delayed
  w.commit(b,g,lambda:False)
  self.assertTrue(w.verified)
  for stamp in w.audit['axis_transitions']:
   self.assertLessEqual(stamp['position_sent_s']-stamp['damping_begin_s'],.01)
  damped=set()
  for p in b.frames:
   if p[4]!=131:continue
   width=p[6]
   for j in range(7,len(p)-1,width+1):
    if width==1:damped.add(p[j])
    else:damped.discard(p[j])
   self.assertLessEqual(len(damped),1)
  self.assertFalse(damped)
 def test_slow_single_axis_still_fails_deadline_and_recovers(self):
  b,w,g=self.fixture();read=b.read
  def delayed(i,a,n):
   if b.ram[i][40]==2:b.t+=.012
   return read(i,a,n)
  b.read=delayed
  report=w.commit(b,g,lambda:False)
  self.assertEqual(report['status'],'goal_readback_verified')
  self.assertTrue(w.audit['recovery_verified']);self.assertFalse(w.audit['physically_qualified'])
  self.assertFalse(w.audit['timing_criterion_met']);self.assertIn('deadline',w.audit['primary_error'])
  self.assertTrue(w.restore(True))
 def test_deadline_with_uncertain_recovery_still_latches(self):
  b,w,g=self.fixture();read=b.read
  def delayed(i,a,n):
   if b.ram[i][40]==2:
    b.t+=.012
    if i==4:raise OSError('axis4 recovery unreadable')
   return read(i,a,n)
  b.read=delayed
  with self.assertRaises(RuntimeError):w.commit(b,g,lambda:False)
  self.assertFalse(w.verified);self.assertIn(4,b.unsafe_damping_axes)
  self.assertFalse(w.restore(True))
 def test_timing_recovery_does_not_waive_travel_bound_or_cancellation(self):
  for fault in ('travel','cancel'):
   b,w,g=self.fixture();read=b.read;injected=[False]
   def delayed(i,a,n):
    if b.ram[i][40]==2:b.t+=.012
    if fault=='travel'and w.audit.get('recovery_verified')and i==3 and not injected[0]:
     injected[0]=True;b.ram[i][56:58]=(3020).to_bytes(2,'little')
    return read(i,a,n)
   b.read=delayed
   with self.subTest(fault=fault),self.assertRaises(RuntimeError):
    w.commit(b,g,lambda:fault=='cancel'and bool(w.audit.get('recovery_verified')))
   self.assertNotIn('timing_recovery_support_verified',w.audit)
 def test_final_recovery_proof_failure_blocks_cleanup_dispatch_for_that_axis(self):
  from shared.experiments.central_safety_controller_20261110.runtime import damping_dispatch_guard
  for fault in ('read','window','torque'):
   b,w,g=self.fixture();read=b.read
   def delayed(i,a,n):
    if b.ram[i][40]==2:b.t+=.012
    if w.audit.get('recovery_verified')and i==4:
     if fault=='read':raise OSError('final proof link loss')
     if fault=='window':b.ram[i][56:58]=(4000).to_bytes(2,'little')
     if fault=='torque':b.ram[i][40]=2
    return read(i,a,n)
   b.read=delayed
   with self.subTest(fault=fault),self.assertRaises((RuntimeError,OSError)):w.commit(b,g,lambda:False)
   self.assertFalse(w.verified)
   self.assertIn(4,b.unsafe_damping_axes)
   with self.assertRaises(RuntimeError):damping_dispatch_guard(b,(4,))
   damping_dispatch_guard(b,(1,2,3,5))
 def fixture(self):
  b=Bus();w=GroupStop({i:(1500,3500)for i in range(1,6)},clock=b.clock)
  return b,w,{i:int.from_bytes(a[56:58],'little')for i,a in b.ram.items()}
 def test_cancel_all_moving_native_targets_once_preserve_resting_load_and_source(self):
  b,w,g=self.fixture();source={i:bytes(a[40:50])for i,a in b.ram.items()};r=w.commit(b,g,lambda:False)
  self.assertEqual(r['verified_ids'],[1,2,3,4,5]);self.assertEqual(r['effective_goals'][2],1970)
  self.assertEqual(w.affected,[1,3,4,5]);self.assertEqual(len(b.frames),2*len(w.affected))
  self.assertTrue(all(p[4]==131 for p in b.frames));self.assertEqual(b.frames[0][5:7],bytes((40,1)))
  self.assertEqual(b.frames[1][5:7],bytes((40,8)))
  for i in w.affected:self.assertEqual(b.ram[i][42:44],b.ram[i][67:69]);self.assertEqual(b.ram[i][40],1)
  self.assertFalse(w.restore(False));self.assertTrue(w.restore(True))
  for i in range(1,6):self.assertEqual(b.ram[i][41],source[i][1]);self.assertEqual(b.ram[i][44:50],source[i][4:10])
  self.assertTrue(all(p[5]in(40,41)for p in b.frames))
 def test_cancel_before_dispatch_cancels_prior_motion_with_safe_recovery(self):
  b,w,g=self.fixture()
  with self.assertRaises(RuntimeError):w.commit(b,g,lambda:True)
  self.assertFalse(any(p[4]==131 for p in b.frames));self.assertTrue(w.audit['recovery_verified'])
  self.assertTrue(all(b.ram[i][40]==1 and b.ram[i][42:44]==b.ram[i][67:69]for i in range(1,6)))
 def test_preflight_read_failure_holds_freshly_proven_axes_before_latching(self):
  b,w,g=self.fixture();b.fail_reads=1
  with self.assertRaises(OSError):w.commit(b,g,lambda:False)
  self.assertTrue(w.audit['recovery_verified']);self.assertTrue(w.verified)
  self.assertTrue(all(b.ram[i][40]==1 and b.ram[i][42:44]==b.ram[i][67:69]for i in range(1,6)))
 def test_partial_broadcast_recovers_each_independently_verified_axis(self):
  b,w,g=self.fixture();write=b.port.write;first=[True]
  def partial(p):
   if p[4]==131 and first[0]:
    first[0]=False;b.frames.append(bytes(p));b.apply(p[7],40,b'\2');return len(p)-2
   return write(p)
  b.port.write=partial
  with self.assertRaisesRegex(RuntimeError,'Partial'):w.commit(b,g,lambda:False)
  self.assertTrue(w.audit['recovery_verified']);self.assertTrue(w.restore(True))
 def test_late_recovery_proof_is_logged_as_deadline_failure_not_a_timing_pass(self):
  b,w,g=self.fixture();read=b.read;n=[0]
  def delayed(i,a,count):
   if b.frames and i==1:
    n[0]+=1
    if n[0]==1:raise OSError('read lost')
    if n[0]==3:b.t+=.02
   return read(i,a,count)
  b.read=delayed
  with self.assertRaises(OSError):w.commit(b,g,lambda:False)
  self.assertIn(1,w.audit['recovery_deadline_exceeded_ids']);self.assertTrue(w.audit['recovery_verified'])
  self.assertIn('primary_error',w.audit);self.assertFalse(w.audit['physically_qualified'])
 def test_lost_damping_read_recovers_active_hold_but_preserves_primary_error(self):
  b,w,g=self.fixture();apply=b.apply;injected=[False]
  def lost(i,a,d):
   apply(i,a,d)
   if a==40 and d==b'\2'and not injected[0]:injected[0]=True;b.fail_reads=1
  b.apply=lost
  with self.assertRaises(OSError):w.commit(b,g,lambda:False)
  self.assertTrue(all(b.ram[i][40]==1 for i in range(1,6)));self.assertTrue(w.audit['recovery_verified'])
  self.assertTrue(w.restore(True));self.assertIn('primary_error',w.audit)
 def test_unreadable_axis_is_not_reenabled_with_a_guessed_target(self):
  b,w,g=self.fixture();read=b.read
  def lost(i,a,n):
   if b.frames and i==3:raise OSError('axis3 wire fault')
   return read(i,a,n)
  b.read=lost
  with self.assertRaises(OSError):w.commit(b,g,lambda:False)
  self.assertIn(3,b.unsafe_damping_axes)
  self.assertTrue(all(b.ram[i][40]==1 for i in (1,2,4,5)))
 def test_outside_reviewed_window_and_bad_status_send_no_damping(self):
  for field,value in ((56,(4000).to_bytes(2,'little')),(65,b'\1')):
   b,w,g=self.fixture();b.ram[4][field:field+len(value)]=value
   with self.assertRaises(RuntimeError):w.commit(b,g,lambda:False)
   self.assertIn(4,b.unsafe_damping_axes)
   self.assertFalse(any(p[2]==4 for p in b.frames))

class ID2QualityTests(unittest.TestCase):
 fixture=Tests.fixture
 def test_opted_id2_post_verified_deflection_records_quality_without_accepting_native_changes(self):
  from normal_gaze_motor import decode_state
  b,w,g=self.fixture();w.commit(b,g,lambda:False)
  w.allow_contact_deflection_ids={2};w.poststop_quality_limits={2:34}
  # Existing fixture ID2 rests and is not a reset/affected axis. Use moving ID2.
  self.assertTrue(w.verified)
  i=next(i for i in w.expected if i!=1)
  # This test specifically requires a known active reset frame for ID2.
  if 2 not in w.expected:
   b,w,g=self.fixture();b.ram[2][58:60]=(100).to_bytes(2,'little');b.ram[2][66]=1
   w.commit(b,g,lambda:False);w.allow_contact_deflection_ids={2};w.poststop_quality_limits={2:34}
  row=decode_state(2,b.read(2,33,38));row['position_raw']=w.reset_q[2]+18
  w.guard_feedback(row)
  self.assertTrue(w.verified);self.assertTrue(w.audit['id2_contact_deflection']['stop_quality_bound_exceeded'])
  bad=dict(row,goal_raw=row['goal_raw']+1)
  with self.assertRaises(RuntimeError):w.guard_feedback(bad)
 def test_id2_deflection_before_verified_stop_is_not_accepted(self):
  b,w,g=self.fixture();w.reset_q={2:2000};w.allow_contact_deflection_ids={2};w.poststop_quality_limits={2:34}
  self.assertFalse(w._travel_valid(2,2018))

class SupportQualityTests(unittest.TestCase):
 fixture=Tests.fixture
 def test_loaded_support_axis19ticks_is_quality_miss_only_with_explicit_manual_limit(self):
  from normal_gaze_motor import decode_state
  for sid,limit in((2,34),(3,34),(4,22),(5,34)):
   b,w,g=self.fixture()
   if sid==2:b.ram[2][58:60]=(100).to_bytes(2,'little');b.ram[2][66]=1
   w.commit(b,g,lambda:False);w.allow_contact_deflection_ids={sid};w.poststop_quality_limits={sid:limit}
   row=decode_state(sid,b.read(sid,33,38));row['position_raw']=w.reset_q[sid]+19
   with self.subTest(sid=sid):
    w.guard_feedback(row);self.assertTrue(w.verified)
    self.assertTrue(w.audit['id'+str(sid)+'_contact_deflection']['stop_quality_bound_exceeded'])
    bad=dict(row,position_raw=w.reset_q[sid]+limit+1)
    with self.assertRaises(RuntimeError):w.guard_feedback(bad)


class BlockedContactTests(unittest.TestCase):
 fixture=Tests.fixture
 def test_contact_axis_is_captured_first_without_simultaneous_loaded_damping(self):
  for sid in (1,2,4):
   b,old,g=self.fixture();w=GroupStop(old.windows,clock=b.clock,contact_axis=sid)
   w.commit(b,g,lambda:False)
   with self.subTest(sid=sid):
    self.assertEqual(w.audit['axis_transitions'][0]['id'],sid)
    self.assertTrue(w.verified);self.assertTrue(w.restore(True))
    active=set()
    for packet in b.frames:
     if packet[4]!=131:continue
     width=packet[6]
     for j in range(7,len(packet)-1,width+1):
      if width==1:active.add(packet[j])
      else:active.discard(packet[j])
     self.assertLessEqual(len(active),1)
    self.assertFalse(active)
 def test_stationary_contact_axis_must_cancel_old_error_not_keep_pushing(self):
  b,old,g=self.fixture();w=GroupStop(old.windows,clock=b.clock,contact_axis=2)
  self.assertEqual(int.from_bytes(b.ram[2][42:44],'little'),1970)
  r=w.commit(b,g,lambda:False)
  self.assertIn(2,w.affected);self.assertEqual(int.from_bytes(b.ram[2][42:44],'little'),2000)
  self.assertEqual(r['effective_goals'][2],2000);self.assertTrue(w.verified)
  self.assertEqual(b.ram[2][40],1);self.assertEqual(int.from_bytes(b.ram[2][48:50],'little'),1000)
 def test_contact_axis_is_explicit_valid_id(self):
  for axis in (0,6,True,'2'):
   with self.assertRaises(ValueError):GroupStop({i:(0,4095)for i in range(1,6)},contact_axis=axis)
