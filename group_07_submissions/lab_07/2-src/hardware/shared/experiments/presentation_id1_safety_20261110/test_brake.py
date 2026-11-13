import unittest
from shared.experiments.resistance_id1_20261109.test_fast_stop import FastTests
from shared.experiments.presentation_id1_safety_20261110.brake import brake_id1

class BrakeProfileTests(unittest.TestCase):
 def test_happy_profile_retains_same_bounded_braking_pulse(self):
  b=FastTests().bus();b.b[8]=8;b.b[13:15]=(1000).to_bytes(2,'little');b.b[25:27]=(250).to_bytes(2,'little')
  def feedback():
   if len(b.packets)>=2:b.b[25:27]=b'\0\0'
   return b.read(1,33,38)
  result=brake_id1(b,ack=lambda *a:None,read_feedback=feedback,pulse=True,run_acc=8,run_speed=1000)
  self.assertEqual(result['method'],'velocity_terminated_bounded_pulse')
  self.assertEqual(b.packets[1][7],0);self.assertEqual(int.from_bytes(b.packets[1][12:14],'little'),600)
  self.assertLessEqual(abs(result['capture_goal']-result['capture_encoder']),16)
  self.assertEqual(b.packets[-1][6:-1],b'\2')
 def test_unqualified_actual_speed_cannot_issue_active_pulse(self):
  b=FastTests().bus();b.b[8]=8;b.b[13:15]=(1000).to_bytes(2,'little');b.b[25:27]=(700).to_bytes(2,'little')
  with self.assertRaises(RuntimeError):brake_id1(b,ack=lambda *a:None,pulse=True,run_acc=8,run_speed=1000)
  self.assertFalse(b.packets)
