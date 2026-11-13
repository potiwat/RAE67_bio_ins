import unittest
from shared.experiments.resistance_id1_20261109.brake import atomic_hold

class Bus:
 def __init__(self):
  self.b=bytearray(38);self.b[7]=1;self.b[8]=3;self.b[13:15]=(600).to_bytes(2,'little');self.b[15:17]=(160).to_bytes(2,'little');self.b[23:25]=(2019).to_bytes(2,'little')
  self.port=self;self.packets=[];self.windows={1:(1691,2347)};self.corrupt=False
 def read(self,sid,addr,count):
  assert (sid,addr,count)==(1,33,38);return bytes(self.b)
 def reset_input_buffer(self):pass
 def flush(self):pass
 def write(self,p):
  self.packets.append(p)
  if not self.corrupt:self.b[8:15]=p[6:13]
  return len(p)

class BrakeTests(unittest.TestCase):
 def test_only_native_motion_block_same_parameters_and_fresh_position(self):
  b=Bus();r=atomic_hold(b,ack=lambda *a:None)
  self.assertEqual(len(b.packets),1);p=b.packets[0]
  self.assertEqual(p[2:6],bytes((1,10,3,41)))
  self.assertEqual(p[6:13],bytes((3,227,7,0,0,88,2)))
  self.assertEqual(sum(p[2:])&255,255)
  self.assertEqual(r['hold_goal'],2019)
 def test_unhealthy_unknown_parameters_or_outside_window_cannot_write(self):
  for index,value in ((0,1),(7,0),(8,0),(13,17),(15,255),(23,255),(32,1)):
   b=Bus();b.b[index]=value
   # position low-byte255 remains in bounds; change high byte instead.
   if index==23:b.b[24]=15
   with self.assertRaises(RuntimeError):atomic_hold(b,ack=lambda *a:None)
   self.assertEqual(b.packets,[])
 def test_ack_or_readback_error_never_reports_stop_confirmed(self):
  b=Bus()
  with self.assertRaises(TimeoutError):atomic_hold(b,ack=lambda *a:(_ for _ in ()).throw(TimeoutError()))
  b=Bus();b.corrupt=True
  with self.assertRaises(RuntimeError):atomic_hold(b,ack=lambda *a:None)
 def test_brake_zero_only_explicitly_selected_and_other_values_rejected(self):
  b=Bus();r=atomic_hold(b,ack=lambda *a:None,brake_acc=0)
  self.assertEqual(b.packets[0][6],0);self.assertEqual(r['register41_47'][0],0)
  for value in (1,8,True):
   b=Bus()
   with self.assertRaises(ValueError):atomic_hold(b,ack=lambda *a:None,brake_acc=value)
   self.assertEqual(b.packets,[])
 def test_slow_brake_only_permitted_with_explicit_zero_acceleration(self):
  b=Bus();atomic_hold(b,ack=lambda *a:None,brake_acc=0,brake_speed=1)
  self.assertEqual(b.packets[0][11:13],bytes((1,0)))
  b=Bus()
  with self.assertRaises(ValueError):atomic_hold(b,ack=lambda *a:None,brake_speed=1)
  self.assertFalse(b.packets)
