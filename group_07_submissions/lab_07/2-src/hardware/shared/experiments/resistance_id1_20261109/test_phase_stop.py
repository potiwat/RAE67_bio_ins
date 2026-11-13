import unittest
from shared.experiments.resistance_id1_20261109.phase_stop import PhaseStop

class Bus:
 def __init__(self):
  self.phase=12;self.lock=1;self.b=bytearray(38);self.b[7]=1;self.b[8]=3;self.b[13:15]=(600).to_bytes(2,'little');self.b[15:17]=(160).to_bytes(2,'little');self.b[23:25]=(2019).to_bytes(2,'little');self.b[9:11]=self.b[23:25];self.b[34:36]=self.b[23:25]
  self.port=self;self.windows={1:(1691,2347)};self.packets=[]
 def read(self,sid,addr,count):
  assert sid==1
  if (addr,count)==(18,1):return bytes((self.phase,))
  if (addr,count)==(55,1):return bytes((self.lock,))
  assert (addr,count)==(33,38);return bytes(self.b)
 def reset_input_buffer(self):pass
 def flush(self):pass
 def write(self,p):
  self.packets.append(p);assert p[2]==1
  if p[5]==18:self.phase=p[6]
  elif p[5]==41:self.b[8:15]=p[6:13]
  else:raise AssertionError('Unexpected register')
  return len(p)

class PhaseTests(unittest.TestCase):
 def make(self):
  b=Bus();s=PhaseStop(b,ack=lambda *a:None);return b,s
 def test_change_only_bit3_with_lock_preserved_and_restore(self):
  b,s=self.make();s.apply();self.assertEqual(b.phase,4);self.assertEqual(b.lock,1)
  s.restore();self.assertEqual(b.phase,12);self.assertEqual([p[5] for p in b.packets],[18,18]);self.assertTrue(s.audit['restored'])
 def test_zero_speed_command_only_when_phase_four_is_verified(self):
  b,s=self.make()
  with self.assertRaises(RuntimeError):s.stop()
  self.assertFalse(b.packets);s.apply();r=s.stop()
  self.assertEqual(r['register41_47'],[0,227,7,0,0,0,0]);self.assertEqual(b.phase,4)
 def test_wrong_phase_unlocked_or_moving_setup_writes_nothing(self):
  for key,value in (('phase',8),('lock',0),('moving',1)):
   b=Bus()
   if key=='moving':b.b[33]=value
   else:setattr(b,key,value)
   with self.assertRaises(RuntimeError):PhaseStop(b,ack=lambda *a:None).apply()
   self.assertFalse(b.packets)
 def test_restore_requires_stopped_hold_and_run_parameters(self):
  b,s=self.make();s.apply();b.b[33]=1
  with self.assertRaises(RuntimeError):s.restore()
  self.assertEqual(b.phase,4);self.assertFalse(s.audit['restored'])
