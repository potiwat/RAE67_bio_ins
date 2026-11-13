import unittest
from shared.experiments.resistance_id1_20261109.test_brake import Bus
from shared.experiments.resistance_id1_20261109.fast_stop import fast_stop

class FastTests(unittest.TestCase):
 def test_acc4_run_uses_same_brake_packets_only_when_explicit(self):
  b=self.bus();b.b[8]=4;b.b[25:27]=(250).to_bytes(2,'little')
  with self.assertRaises(RuntimeError):fast_stop(b,ack=lambda *a:None)
  self.assertFalse(b.packets)
  def feedback():
   if len(b.packets)>=2:b.b[25:27]=bytes((0,0))
   return b.read(1,33,38)
  result=fast_stop(b,ack=lambda *a:None,read_feedback=feedback,pulse=True,run_acc=4)
  self.assertEqual(b.packets[0][6:-1],bytes((2,)));self.assertEqual(b.packets[1][7],0)
  self.assertEqual(b.packets[-1][6:-1],bytes((2,)));self.assertLessEqual(abs(result['capture_goal']-result['capture_encoder']),16)
 def bus(self):
  b=Bus();b.reads=[]
  original=b.read
  def read(sid,addr,n):
   b.reads.append((addr,n,len(b.packets)))
   if addr==18:return bytes((12,))
   if addr==55:return bytes((1,))
   return original(sid,addr,n)
  b.read=read
  def write(p):
   b.packets.append(p)
   if len(p)==8:b.b[7]=p[6];b.b[34:36]=b.b[23:25]
   else:b.b[7:15]=p[6:14]
   return len(p)
  b.write=write;b.flush=lambda:(_ for _ in ()).throw(AssertionError('No blocking drain in fast path'))
  return b
 def test_two_acked_packets_no_intermediate_read_no_flush_and_bounded_counter_goal(self):
  b=self.bus();b.b[25:27]=(400).to_bytes(2,'little');acks=[]
  r=fast_stop(b,ack=lambda *a:acks.append(a[2]),read_feedback=lambda:b.read(1,33,38))
  self.assertEqual(len(acks),2);self.assertEqual(b.packets[0][6:-1],bytes((2,)))
  self.assertEqual(b.packets[1][6:8],bytes((1,0)))
  self.assertEqual(r['capture_goal'],2013);self.assertEqual(r['hold_goal'],2019)
  self.assertTrue(any(count==1 for _,_,count in b.reads))
 def test_reverse_rotation_uses_opposing_six_tick_goal(self):
  b=self.bus();b.b[25:27]=(32768+400).to_bytes(2,'little')
  self.assertEqual(fast_stop(b,ack=lambda *a:None,read_feedback=lambda:b.read(1,33,38))['capture_goal'],2025)
 def test_no_second_write_after_first_ack_failure(self):
  b=self.bus();b.b[25]=250
  with self.assertRaises(TimeoutError):fast_stop(b,ack=lambda *a:(_ for _ in ()).throw(TimeoutError()))
  self.assertEqual(len(b.packets),1)
 def test_fresh_low_velocity_selects_damping_without_active_pulse(self):
  for speed in (0,50,32818):
   b=self.bus();b.b[8]=4;b.b[25:27]=speed.to_bytes(2,'little')
   result=fast_stop(b,ack=lambda *a:None,read_feedback=lambda:b.read(1,33,38),pulse=True,run_acc=4)
   self.assertEqual(result['method'],'low_speed_damping');self.assertEqual(len(b.packets),1)
   self.assertEqual(b.packets[0][6:-1],bytes((2,)));self.assertEqual(b.b[7],2)
 def test_low_velocity_does_not_bypass_health_or_parameter_faults(self):
  for at,value in ((0,1),(7,0),(8,4),(15,0),(32,1)):
   b=self.bus();b.b[at]=value
   with self.assertRaises(RuntimeError):fast_stop(b,ack=lambda *a:None)
   self.assertFalse(b.packets)
 def test_pulse_ends_in_damping_after_velocity_falls(self):
  b=self.bus();b.b[25:27]=(250).to_bytes(2,'little')
  def feedback():
   if len(b.packets)>=2:b.b[25:27]=bytes((0,0))
   return b.read(1,33,38)
  r=fast_stop(b,ack=lambda *a:None,read_feedback=feedback,pulse=True)
  self.assertEqual(b.packets[-1][6:-1],bytes((2,)))
  self.assertEqual(r['method'],'velocity_terminated_bounded_pulse')
  self.assertLessEqual(abs(r['capture_goal']-r['capture_encoder']),16)
 def test_explicit_high_brake_acceleration_changes_only_brake_packet(self):
  b=self.bus();b.b[25:27]=(250).to_bytes(2,'little')
  def feedback():
   if len(b.packets)>=2:b.b[25:27]=bytes((0,0))
   return b.read(1,33,38)
  fast_stop(b,ack=lambda *a:None,read_feedback=feedback,pulse=True,brake_acc=254)
  self.assertEqual(b.packets[1][7],254)
  self.assertEqual(int.from_bytes(b.packets[1][12:14],'little'),600)
  b=self.bus()
  with self.assertRaises(ValueError):fast_stop(b,brake_acc=8)
  self.assertFalse(b.packets)
