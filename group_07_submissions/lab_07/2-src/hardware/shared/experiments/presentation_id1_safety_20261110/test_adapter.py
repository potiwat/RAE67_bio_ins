import unittest
from unittest.mock import Mock
from types import SimpleNamespace
from shared.experiments.presentation_id1_safety_20261110.adapter import Adapter,SafetyInterrupt

class AdapterTests(unittest.TestCase):
 def test_close_always_closes_uart_even_when_cleanup_fails(self):
  a,b,c=self.fixture();a.close_original=Mock();error=RuntimeError('hold unconfirmed')
  a.owner=SimpleNamespace(cleanup=Mock(side_effect=error),finish=Mock())
  with self.assertRaises(RuntimeError):b.close()
  a.close_original.assert_called_once();a.owner.finish.assert_called_once_with(error)
 def fixture(self):
  calls=[]
  b=SimpleNamespace(read=lambda *a:b'actual',write=lambda *a:calls.append(a),sync_positions=lambda goals,cancelled:calls.append(('sync',goals)),close=lambda:None)
  a=Adapter(b);return a,b,calls
 def test_each_uart_boundary_services_owner_and_preserves_real_read(self):
  a,b,c=self.fixture();a.owner=SimpleNamespace(poll=Mock())
  self.assertEqual(b.read(1,33,38),b'actual')
  b.write(1,42,(2019).to_bytes(2,'little'));b.sync_positions({1:2019,2:2800},lambda:False)
  self.assertEqual(a.owner.poll.call_count,3)
  with a.internal():b.read(1,33,38)
  self.assertEqual(a.owner.poll.call_count,3)
 def test_trip_interrupts_command_before_write_even_inside_runtime_exception_handler(self):
  a,b,c=self.fixture();signal=SafetyInterrupt('resistance',{'id':1})
  a.owner=SimpleNamespace(poll=Mock(side_effect=signal));caught=False
  with self.assertRaises(SafetyInterrupt):
   try:b.write(1,42,(2300).to_bytes(2,'little'))
   except Exception:caught=True
  self.assertFalse(caught);self.assertEqual(c,[])
 def test_no_pid_or_eeprom_write_even_from_startup(self):
  a,b,c=self.fixture()
  for sid in range(1,6):
   for address in (18,21,23,33,55):
    with self.assertRaises(ValueError):b.write(sid,address,b'\1')
  self.assertEqual(c,[])
 def test_happy_profile_is_not_silently_clamped(self):
  a,b,c=self.fixture();b.write(1,46,(1000).to_bytes(2,'little'));b.write(1,41,b'\10')
  self.assertEqual(c,[(1,46,(1000).to_bytes(2,'little')),(1,41,b'\10')])
 def test_paused_base_goal_and_profile_are_suppressed_but_feedback_not_faked(self):
  a,b,c=self.fixture();a.blocked=True;b.write(1,42,(2100).to_bytes(2,'little'));b.write(1,41,b'\10');b.write(2,42,(2800).to_bytes(2,'little'))
  self.assertEqual(c,[(2,42,(2800).to_bytes(2,'little'))]);self.assertEqual(a.latest_goal,2100)
 def test_mixed_sync_does_not_resend_paused_id1(self):
  a,b,c=self.fixture();a.blocked=True;b.sync_positions({1:2100,2:2800,3:2700},lambda:False)
  self.assertEqual(c,[('sync',{2:2800,3:2700})]);self.assertEqual(a.latest_goal,2100)
 def test_one_remaining_joint_uses_unicast_and_checks_cancel(self):
  a,b,c=self.fixture();a.blocked=True;b.sync_positions({1:2100,5:2696},lambda:False)
  self.assertEqual(c,[(5,42,(2696).to_bytes(2,'little'))])
  c.clear();b.sync_positions({1:2100,5:2696},lambda:True);self.assertEqual(c,[])
 def test_internal_safety_writes_do_not_replace_original_target(self):
  a,b,c=self.fixture();a.blocked=True;a.latest_goal=2200
  with a.internal():b.write(1,42,(2100).to_bytes(2,'little'))
  self.assertEqual(a.latest_goal,2200);self.assertEqual(c,[(1,42,(2100).to_bytes(2,'little'))])
