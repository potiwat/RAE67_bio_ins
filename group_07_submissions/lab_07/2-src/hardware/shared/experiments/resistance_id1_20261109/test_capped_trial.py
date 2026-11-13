import unittest
try:
 from shared.experiments.resistance_id1_20261109.capped_trial import EarlyGuard,CappedNative,CapSession
except ImportError:EarlyGuard=CappedNative=CapSession=None

class EarlyTests(unittest.TestCase):
 def row(self,t,q=2000,error=70,duty=150,current=5):
  return dict(id=1,sampled_monotonic_s=t,mode=0,torque_raw=1,status_raw=0,position_raw=q,goal_raw=q+error,internal_target_raw=q+error,load_raw=duty,current_raw=current)
 def test_early_guard_can_trip_while_axis_still_moves(self):
  self.assertIsNotNone(EarlyGuard);g=EarlyGuard()
  self.assertFalse(g.update(self.row(0.),0.)['trip'])
  self.assertTrue(g.update(self.row(.06,q=2020),.06)['trip'])
 def test_duplicate_and_single_peak_are_not_early_contact(self):
  self.assertIsNotNone(EarlyGuard);g=EarlyGuard()
  g.update(self.row(0.),0.);self.assertFalse(g.update(self.row(0.),.01)['trip'])
  self.assertFalse(g.update(self.row(.06,error=45,duty=100,current=1),.06)['trip'])
 def test_stale_is_fault_not_automatic_retry(self):
  self.assertIsNotNone(EarlyGuard);g=EarlyGuard()
  self.assertEqual(g.update(self.row(0.),.3)['state'],'FAULT_HOLD')

class FakeBus:
 def __init__(self):
  self.block=bytearray(38);self.block[7]=1;self.block[15:17]=(1000).to_bytes(2,'little');self.block[9:11]=(2000).to_bytes(2,'little');self.block[23:25]=(2000).to_bytes(2,'little')
  self.packets=[];self.closes=0;self.bad_readback=False;self.port=self
 def read(self,sid,address,count):
  assert (sid,address,count)==(1,33,38)
  return bytes(self.block)
 def reset_input_buffer(self):pass
 def flush(self):pass
 def write(self,packet):
  self.packets.append(packet)
  if not self.bad_readback:self.block[15:17]=packet[6:8]
  return len(packet)
 def close(self):self.closes+=1

class CapTests(unittest.TestCase):
 def test_only_id1_ram48_is_written_then_restored_with_readback(self):
  b=FakeBus();c=CapSession(b,ack=lambda *args:None);c.install()
  self.assertEqual(int.from_bytes(b.block[15:17],'little'),160)
  b.close();self.assertTrue(c.audit['restored']);self.assertEqual(b.closes,1)
  self.assertEqual([p[5] for p in b.packets],[48,48]);self.assertEqual([p[2] for p in b.packets],[1,1])
  self.assertEqual(int.from_bytes(b.block[15:17],'little'),1000)
 def test_unknown_entry_and_readback_mismatch_are_rejected(self):
  b=FakeBus();b.block[15:17]=(300).to_bytes(2,'little')
  with self.assertRaises(RuntimeError):CapSession(b)
  self.assertEqual(b.packets,[])
  b=FakeBus();c=CapSession(b,ack=lambda *args:None);b.bad_readback=True
  with self.assertRaisesRegex(RuntimeError,'readback'):c.install()
 def test_cap_drift_is_fault(self):
  b=FakeBus();c=CapSession(b,ack=lambda *args:None);c.install();b.block[15:17]=(1000).to_bytes(2,'little')
  with self.assertRaisesRegex(RuntimeError,'drift'):b.read(1,33,38)
 def test_unconfirmed_hold_never_increases_cap_and_still_closes(self):
  clock=[0.];b=FakeBus();c=CapSession(b,ack=lambda *args:None,clock=lambda:clock[0],pause=lambda dt:clock.__setitem__(0,clock[0]+dt));c.install()
  b.block[33]=1;b.close()
  self.assertFalse(c.audit['restored']);self.assertEqual(b.closes,1)
  self.assertEqual(int.from_bytes(b.block[15:17],'little'),160);self.assertEqual(len(b.packets),1)
 def test_ack_error_is_not_reported_as_applied(self):
  b=FakeBus();c=CapSession(b,ack=lambda *args:(_ for _ in ()).throw(TimeoutError('no ack')))
  with self.assertRaises(TimeoutError):c.install()
  self.assertFalse(c.audit['applied']);self.assertEqual(len(b.packets),1)
 def test_capped_pause_latches_without_any_auto_probe(self):
  from shared.experiments.resistance_id1_20261109.test_native_retry import NativeTests
  test=NativeTests();m,d,b=test.motor();p=CappedNative()
  for k in range(200):test.tick(p,m,d,b,k*.05,follow=False,effort=4 if k<20 else 0)
  self.assertEqual(p.phase,'LATCHED');self.assertEqual(p.attempts,0)
  self.assertFalse(any(e['event']=='probe_begin' for e in p.events))
