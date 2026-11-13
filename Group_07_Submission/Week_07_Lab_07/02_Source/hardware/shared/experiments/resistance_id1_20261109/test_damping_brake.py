import unittest
from shared.experiments.resistance_id1_20261109.test_brake import Bus
from shared.experiments.resistance_id1_20261109.damping_brake import damping_stop,restore_position_hold,reset_hold_stop

class DampingTests(unittest.TestCase):
 def bus(self):
  b=Bus()
  def write(p):
   b.packets.append(p);b.b[7]=p[6];return len(p)
  b.write=write;return b
 def test_damping_packet_never_disables_torque_and_keeps_original_run_values(self):
  b=self.bus();r=damping_stop(b,ack=lambda *a:None)
  p=b.packets[0];self.assertEqual(p[2:6],bytes((1,4,3,40)))
  self.assertEqual(p[6:-1],bytes((2,)))
  self.assertEqual(sum(p[2:])&255,255);self.assertEqual(r['hold_goal'],2019)
 def test_no_damping_write_if_health_or_cap_or_run_parameters_unknown(self):
  for at,value in ((7,2),(15,0),(8,0),(32,1)):
   b=self.bus();b.b[at]=value
   with self.assertRaises(RuntimeError):damping_stop(b,ack=lambda *a:None)
   self.assertFalse(b.packets)
 def recovery(self,internal_follows=True):
  b=Bus();b.b[7]=2;b.armed=set();b.enabled=[];b.b[34:36]=b.b[23:25] if internal_follows else bytes((0,0))
  def hold(sid):
   self.assertEqual(sid,1);b.b[9:11]=b.b[23:25]
  b.hold_actual=hold
  def write(*args):
   if len(args)==1:
    p=args[0];b.packets.append(p);b.b[8:15]=p[6:13]
    if internal_follows:b.b[34:36]=p[7:9]
    return len(p)
   sid,addr,data=args;self.assertEqual(sid,1)
   if addr==40:self.assertEqual(data,bytes((1,)));self.assertIn(1,b.armed);b.enabled.append(1);b.b[7]=1
   elif addr==41:self.assertEqual(data,bytes((3,)));b.b[8]=3
   elif addr==46:self.assertEqual(data,(600).to_bytes(2,'little'));b.b[13:15]=data
   else:self.fail('Unexpected register')
  b.write=write;clock=[0.]
  return b,lambda:clock[0],lambda dt:clock.__setitem__(0,clock[0]+dt)
 def test_reenable_only_after_internal_target_canceled_and_stationary(self):
  b,clock,pause=self.recovery();r=restore_position_hold(b,ack=lambda *a:None,clock=clock,pause=pause)
  self.assertTrue(r['position_hold_restored']);self.assertEqual(b.enabled,[1]);self.assertEqual(b.b[8],3)
 def test_no_reenable_if_old_native_target_persists_or_motor_moves(self):
  b,clock,pause=self.recovery(False)
  with self.assertRaises(RuntimeError):restore_position_hold(b,ack=lambda *a:None,clock=clock,pause=pause)
  self.assertEqual(b.enabled,[])
  b,clock,pause=self.recovery();b.b[25]=50
  with self.assertRaises(RuntimeError):restore_position_hold(b,ack=lambda *a:None,clock=clock,pause=pause)
  self.assertFalse(b.packets)
 def test_cleanup_after_slow_probe_restores_speed_as_well_as_acceleration(self):
  b,clock,pause=self.recovery();b.b[13:15]=(17).to_bytes(2,'little');b.b[8]=1
  r=restore_position_hold(b,ack=lambda *a:None,clock=clock,pause=pause)
  self.assertTrue(r['position_hold_restored']);self.assertEqual(int.from_bytes(b.b[13:15],'little'),600);self.assertEqual(b.b[8],3)
 def test_active_brake_follows_damping_with_bounded_position_capture(self):
  b=Bus()
  def write(p):
   b.packets.append(p)
   if len(p)==8:b.b[7]=2;b.b[34:36]=b.b[23:25]
   else:b.b[7:15]=p[6:14]
   return len(p)
  b.write=write;r=reset_hold_stop(b,ack=lambda *a:None)
  self.assertEqual(len(b.packets),2)
  self.assertEqual(b.packets[0][6:-1],bytes((2,)))
  self.assertEqual(b.packets[1][6:14],bytes((1,0,227,7,0,0,88,2)))
  self.assertEqual(r['method'],'damping_reset_then_active_hold')
 def test_higher_limit_only_after_confirmed_damping_not_position_drive(self):
  from shared.experiments.resistance_id1_20261109.damping_brake import damping_limit
  b=Bus()
  with self.assertRaises(RuntimeError):damping_limit(b,1000,ack=lambda *a:None)
  self.assertFalse(b.packets)
  b.b[7]=2
  def write(p):
   b.packets.append(p);b.b[15:17]=p[6:8];return len(p)
  b.write=write;damping_limit(b,1000,ack=lambda *a:None)
  self.assertEqual(b.packets[0][5],48);self.assertEqual(b.b[7],2)
  with self.assertRaises(ValueError):damping_limit(b,320,ack=lambda *a:None)
