import unittest
from unittest.mock import patch
from .id2_probe_io import LoadedProbeIO

class Port:
 def __init__(self,b):self.b=b
 def reset_input_buffer(self):pass
 def write(self,p):
  assert p[2]==2 and p[4]==3 and sum(p[2:])&255==255
  a=p[5];data=p[6:-1];self.b.writes.append((a,bytes(data)));self.b.ram[a:a+len(data)]=data
  if a==42:self.b.ram[67:69]=data;self.b.ram[56:58]=(int.from_bytes(data,'little')+7).to_bytes(2,'little')
  return len(p)
class Bus:
 def __init__(self):
  a=self.ram=bytearray(100);a[40]=1;a[41]=8;a[42:44]=(2835).to_bytes(2,'little');a[46:48]=(600).to_bytes(2,'little');a[48:50]=(1000).to_bytes(2,'little');a[56:58]=(2842).to_bytes(2,'little');a[60:62]=(64).to_bytes(2,'little');a[62]=70;a[67:69]=(2835).to_bytes(2,'little');a[69:71]=(3).to_bytes(2,'little');self.port=Port(self);self.writes=[]
 def read(self,i,a,n):assert i==2;return bytes(self.ram[a:a+n])
class Tests(unittest.TestCase):
 def setUp(self):
  self.t=1.;self.ack=patch('shared.experiments.presentation_safety_play_20261110.id2_probe_io.receive_write_ack',return_value=None);self.ack.start();self.addCleanup(self.ack.stop)
 def fixture(self):
  b=Bus();return b,LoadedProbeIO(b,(2815,2861),lambda:False,lambda:self.t)
 def still(self,io):
  for _ in range(4):self.t+=.05;io.observe_still(io.read()[0])
 def test_prepare_preserves_loaded_goal_not_encoder_and_source_speed_acc(self):
  b,io=self.fixture();io.prepare();self.assertEqual(b.writes,[(48,(400).to_bytes(2,'little'))]);self.assertEqual(io.anchor_goal,2835);self.assertEqual(io.anchor_q,2842);self.assertEqual(int.from_bytes(b.ram[42:44],'little'),2835);self.assertEqual(b.ram[41],8)
 def test_normal_return_requires_original_goal_and_loaded_static_support(self):
  b,io=self.fixture();io.prepare()
  for q in range(2836,2852):io.command(q)
  self.still(io)
  with self.assertRaises(RuntimeError):io.restore()
  for q in range(2850,2834,-1):io.command(q)
  self.still(io);io.restore();self.assertTrue(io.restored);self.assertEqual(int.from_bytes(b.ram[42:44],'little'),2835);self.assertEqual(int.from_bytes(b.ram[48:50],'little'),1000);self.assertTrue(all(a in(42,48)for a,_ in b.writes))
 def test_one_tick_and_pinned_goal_and_travel_bounds(self):
  b,io=self.fixture();io.prepare()
  with self.assertRaises(RuntimeError):io.command(2837)
  for q in range(2836,2852):io.command(q)
  with self.assertRaises(RuntimeError):io.command(2852)
  b.ram[56:58]=(2863).to_bytes(2,'little')
  with self.assertRaises(RuntimeError):io.read()
 def test_no_cap_raise_on_motion_stale_proof_high_effort_or_reference_pending(self):
  for field in('speed','stale','pwm','current','reference'):
   b,io=self.fixture();io.prepare();self.still(io)
   if field=='speed':b.ram[58:60]=(1).to_bytes(2,'little')
   elif field=='stale':self.t+=.3
   elif field=='pwm':b.ram[60:62]=(300).to_bytes(2,'little')
   elif field=='current':b.ram[69:71]=(41).to_bytes(2,'little')
   else:b.ram[67:69]=(2836).to_bytes(2,'little')
   n=len(b.writes)
   with self.subTest(field=field),self.assertRaises(RuntimeError):io.restore()
   self.assertEqual(n,len(b.writes));self.assertEqual(int.from_bytes(b.ram[48:50],'little'),400)
 def test_ambiguous_write_blocks_normal_commands_and_cap_raise(self):
  b,io=self.fixture();io.prepare();read=b.read;state={'bad':True}
  def bad_once(i,a,n):
   raw=read(i,a,n)
   if state['bad']and int.from_bytes(b.ram[42:44],'little')==2836:
    state['bad']=False;raw=bytearray(raw);raw[29]=59;return bytes(raw)
   return raw
  b.read=bad_once
  with self.assertRaises(RuntimeError):io.command(2836)
  self.assertTrue(io.uncertain_write);self.assertEqual(io.pending['goal'],2836)
  with self.assertRaises(RuntimeError):io.restore()
  self.assertEqual(int.from_bytes(b.ram[48:50],'little'),400)
 def test_missing_ack_is_accepted_only_with_matching_native_readback(self):
  b,io=self.fixture()
  with patch('shared.experiments.presentation_safety_play_20261110.id2_probe_io.receive_write_ack',side_effect=TimeoutError('ack')):io.prepare()
  self.assertFalse(io.uncertain_write);self.assertTrue(io.audit[0]['ack_error'])
 def test_source_profile_or_source_support_fault_refuses_before_cap(self):
  for field in('acc','cap','mode','moving'):
   b,io=self.fixture()
   if field=='acc':b.ram[41]=3
   elif field=='cap':b.ram[48:50]=(400).to_bytes(2,'little')
   elif field=='mode':b.ram[33]=1
   else:b.ram[66]=1
   with self.subTest(field=field),self.assertRaises(RuntimeError):io.prepare()
   self.assertFalse(b.writes)
 def test_preload_rebase_is_not_an_available_api(self):
  b,io=self.fixture();self.assertFalse(hasattr(io,'hold'));self.assertFalse(b.writes)

 def test_diagnostic_rejects_changed_original_held_goal_before_cap(self):
  b,io=self.fixture();b.ram[42:44]=(2834).to_bytes(2,'little');b.ram[67:69]=b.ram[42:44]
  with self.assertRaises(RuntimeError):io.prepare()
  self.assertFalse(b.writes)
 def test_entry_encoder_anchor_is_not_rebased_by_small_read_jitter(self):
  b,io=self.fixture();entry=io.read()[0];b.ram[56:58]=(2843).to_bytes(2,'little');io.prepare(entry_source=entry);self.assertEqual(io.anchor_q,2842)
 def test_entry_control_change_refuses_without_cap_write(self):
  b,io=self.fixture();entry=io.read()[0];b.ram[46:48]=(601).to_bytes(2,'little')
  with self.assertRaises(RuntimeError):io.prepare(entry_source=entry)
  self.assertFalse(b.writes)
 def test_final_static_scalar_cannot_accept_position_outside_absolute_feedback_window(self):
  b,io=self.fixture();io.prepare();r=io.read()[0];r['position_raw']=2862;self.assertFalse(io._static_ok(r))
 def test_loaded_entry_uses_existing_support_error_bound_without_rebase(self):
  b,io=self.fixture();b.ram[56:58]=(2855).to_bytes(2,'little');b.ram[60:62]=(168).to_bytes(2,'little');b.ram[69:71]=(16).to_bytes(2,'little')
  io.prepare();self.assertEqual(io.anchor_goal,2835);self.assertEqual(io.anchor_q,2855)
  self.assertEqual(b.writes,[(48,(400).to_bytes(2,'little'))])
