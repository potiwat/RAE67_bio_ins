import unittest
from shared.experiments.resistance_id1_20261109 import test_native_retry as native_tests
from shared.experiments.resistance_id1_20261109.capped_retry import CappedRetry
from shared.experiments.resistance_id1_20261109.capped_retry import RetryCapSession
from shared.experiments.resistance_id1_20261109.test_capped_trial import FakeBus

class RetryTests(unittest.TestCase):
 def setup_trial(self):
  helper=native_tests.NativeTests();m,d,b=helper.motor();original=b.write
  def write(sid,addr,data):
   if addr==46:
    self.assertEqual(sid,1);m.controller.last_rows[0]['target_speed_raw']=int.from_bytes(data,'little')
   else:original(sid,addr,data)
  b.write=write
  b.id1_probe_speed=lambda value:write(1,46,value.to_bytes(2,'little'))
  p=CappedRetry();helper.tick(p,m,d,b,0.)
  return helper,m,d,b,p
 def test_clearance_requires_actual_progress_not_effort_drop(self):
  h,m,d,b,p=self.setup_trial()
  # Initial free probe is itself mandatory; no progress must latch, never sweep.
  for k in range(1,220):h.tick(p,m,d,b,k*.05,follow=False,effort=0)
  self.assertEqual(p.phase,'LATCHED');self.assertFalse(p.probe_qualified)
  self.assertFalse(any(e['event']=='auto_resume' for e in p.events))
 def test_free_probe_qualifies_then_contact_remove_resumes(self):
  h,m,d,b,p=self.setup_trial()
  for k in range(1,100):
   h.tick(p,m,d,b,k*.05,follow=True,effort=0)
   if p.phase=='RUN':break
  self.assertTrue(p.probe_qualified);self.assertEqual(p.phase,'RUN')
  now=k*.05;p.waiting(m,now,'test_contact')
  for j in range(1,160):
   h.tick(p,m,d,b,now+j*.05,follow=True,effort=0)
   if any(e['event']=='auto_resume' and e['attempt']==1 for e in p.events):break
  self.assertEqual(p.phase,'RUN');self.assertEqual(p.attempts,1)
  self.assertTrue(any(e['event']=='auto_resume' for e in p.events))
 def test_moving_hold_never_starts_probe(self):
  h,m,d,b,p=self.setup_trial();p.probe_qualified=True;p.waiting(m,.0,'test')
  m.controller.last_rows[0]['moving_raw']=1
  for k in range(1,100):h.tick(p,m,d,b,k*.05,follow=False,effort=0)
  self.assertEqual(p.phase,'LATCHED');self.assertEqual(p.attempts,0)
 def test_stop_blocks_probe_and_stale_faults(self):
  h,m,d,b,p=self.setup_trial();count=len(b.writes);m.urgent_stop.set()
  h.tick(p,m,d,b,.05);self.assertEqual(len(b.writes),count)
  m.urgent_stop.clear();h.tick(p,m,d,b,.1)
  with self.assertRaisesRegex(RuntimeError,'feedback'):p.step(d,m,.29)
 def test_retries_bounded_and_probe_goals_limited(self):
  h,m,d,b,p=self.setup_trial();p.probe_qualified=True;p.waiting(m,0.,'test')
  for k in range(1,650):
   h.tick(p,m,d,b,k*.05,follow=False,effort=0)
  self.assertEqual(p.attempts,3);self.assertEqual(p.phase,'LATCHED')
  probes=[e for e in p.events if e['event']=='probe_begin']
  self.assertEqual(len(probes),3)
  self.assertTrue(all(abs(e['target']-e['start'])==16 for e in probes))

class PacketTests(unittest.TestCase):
 def bus(self):
  b=FakeBus();b.block[13:15]=(600).to_bytes(2,'little')
  def write(packet):
   b.packets.append(packet)
   self.assertEqual(packet[2],1);self.assertIn(packet[5],(46,48))
   self.assertEqual(sum(packet[2:])&255,255)
   at={46:13,48:15}[packet[5]];b.block[at:at+2]=packet[6:8]
   return len(packet)
  b.write=write;return b
 def test_speed_and_cap_restored_after_stationary_close(self):
  b=self.bus();s=RetryCapSession(b,ack=lambda *a:None);s.install()
  b.id1_probe_speed(17);b.close()
  self.assertTrue(s.audit['restored'])
  self.assertEqual(int.from_bytes(b.block[13:15],'little'),600)
  self.assertEqual(int.from_bytes(b.block[15:17],'little'),1000)
  self.assertEqual([p[5] for p in b.packets],[48,46,46,48])
 def test_no_pid_torque_release_or_other_axis_packet(self):
  b=self.bus();s=RetryCapSession(b,ack=lambda *a:None);s.install()
  for value in (0,25,1000):
   with self.assertRaises(ValueError):b.id1_probe_speed(value)
  self.assertEqual(len(b.packets),1)
 def test_unhealthy_feedback_prevents_probe_speed_write(self):
  b=self.bus();s=RetryCapSession(b,ack=lambda *a:None);s.install();b.block[32]=1
  with self.assertRaises(RuntimeError):b.id1_probe_speed(17)
  self.assertEqual(len(b.packets),1)
