import unittest
from shared.experiments.resistance_id1_20261109.test_phase_stop import Bus
from shared.experiments.resistance_id1_20261109.velocity_stop import VelocityStop

class VelocityTests(unittest.TestCase):
 def bus(self):
  b=Bus();original=b.write
  def write(p):
   if p[5]==33:b.packets.append(p);b.b[0]=p[6];return len(p)
   return original(p)
  b.write=write;return b
 def test_velocity_zero_is_prepared_before_mode_change_no_pid_unlock_or_torque_off(self):
  b=self.bus();s=VelocityStop(b,ack=lambda *a:None);s.stop()
  self.assertEqual([p[5] for p in b.packets],[41,33]);self.assertEqual(b.b[0],1)
  self.assertEqual(b.b[13:15],bytes((0,0)));self.assertEqual(b.lock,1)
 def test_no_stop_write_if_wrong_mode_cap_or_lock(self):
  for what in ('mode','cap','lock'):
   b=self.bus()
   if what=='mode':b.b[0]=2
   elif what=='cap':b.b[15]=255
   else:b.lock=0
   with self.assertRaises(RuntimeError):VelocityStop(b,ack=lambda *a:None).stop()
   self.assertFalse(b.packets)
 def test_failed_preparation_ack_never_switches_mode(self):
  b=self.bus();s=VelocityStop(b,ack=lambda *a:(_ for _ in ()).throw(TimeoutError()))
  with self.assertRaises(TimeoutError):s.stop()
  self.assertEqual(b.b[0],0);self.assertEqual(len(b.packets),1)
 def test_stationary_mode_restore_returns_original_values(self):
  b=self.bus();raw=b.write
  def write(*args):
   if len(args)==1:return raw(args[0])
   sid,addr,data=args;self.assertEqual(sid,1)
   if addr==41:b.b[8]=data[0]
   elif addr==46:b.b[13:15]=data
   else:self.fail('Unexpected native restore register')
  b.write=write;s=VelocityStop(b,ack=lambda *a:None);s.stop();clock=[0.];s.clock=lambda:clock[0];s.pause=lambda dt:clock.__setitem__(0,clock[0]+dt)
  s.restore();self.assertTrue(s.audit['restored']);self.assertEqual(b.b[0],0);self.assertEqual(b.b[8],3);self.assertEqual(int.from_bytes(b.b[13:15],'little'),600)
 def test_moving_motor_never_reenters_position_mode(self):
  b=self.bus();s=VelocityStop(b,ack=lambda *a:None);s.stop();count=len(b.packets);b.b[25]=200
  with self.assertRaises(RuntimeError):s.restore()
  self.assertEqual(len(b.packets),count);self.assertEqual(b.b[0],1)
