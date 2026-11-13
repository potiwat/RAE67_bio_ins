import unittest
import io
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock
from shared.experiments.presentation_id1_safety_20261110.owner import Owner

@contextmanager
def internal():yield

class OwnerTests(unittest.TestCase):
 def fixture(self,state='normal'):
  from shared.experiments.resistance_id1_20261109.capped_trial import EarlyGuard
  from shared.experiments.resistance_id1_20261109.test_fast_stop import FastTests
  b=FastTests().bus();b.snapshot=lambda:[];clock=[10.]
  c=SimpleNamespace(state='READY',last_rows=[],last_error='')
  m=SimpleNamespace(controller=c,behavior_trial=state,follow_enabled=True,_hold=Mock(),automatic_fsm=SimpleNamespace(discard_inputs=Mock()))
  o=Owner.__new__(Owner);o.m=m;o.b=b;o.clock=lambda:clock[0];o.a=SimpleNamespace(blocked=False,internal=internal);o.phase='MONITOR';o.guard=EarlyGuard();o.event=Mock();o.log=io.StringIO();o.brake=Mock();o.damp=Mock();o.freeze=Owner.freeze.__get__(o)
  o.armed=True
  o.row=lambda:dict(c.last_rows[0])
  return o,c,b,clock
 def test_startup_profile_work_finishes_before_feedback_watchdog_baseline(self):
  o,c,b,clock=self.fixture();o.armed=False
  old=dict(id=1,sampled_monotonic_s=10.,mode=0,torque_raw=1,status_raw=0,position_raw=2019,goal_raw=2019,internal_target_raw=2019,load_raw=0,current_raw=0,speed_raw=0)
  c.last_rows=[old]
  self.assertFalse(o.observe());self.assertIsNone(o.guard.last_stamp)
  clock[0]=10.272;o.row=Mock(return_value=dict(old,sampled_monotonic_s=10.272))
  self.assertFalse(o.arm_if_ready());self.assertTrue(o.armed);self.assertEqual(o.guard.last_stamp,10.272)
  clock[0]=10.322;c.last_rows=[dict(old,sampled_monotonic_s=10.322)]
  self.assertFalse(o.observe());self.assertEqual(o.phase,'MONITOR')
 def test_real_feedback_gap_after_arming_still_latches(self):
  o,c,b,clock=self.fixture()
  row=dict(id=1,sampled_monotonic_s=10.,mode=0,torque_raw=1,status_raw=0,position_raw=2019,goal_raw=2019,internal_target_raw=2019,load_raw=0,current_raw=0,speed_raw=0)
  c.last_rows=[row];self.assertFalse(o.observe())
  clock[0]=10.272;c.last_rows=[dict(row,sampled_monotonic_s=10.272)]
  self.assertTrue(o.observe());self.assertEqual(o.phase,'FAULT')
 def test_resistance_pauses_worker_from_each_emotion(self):
  for state in ('normal','interested','happy','angry','afraid','sleepy'):
   with self.subTest(state=state):
    o,c,b,clock=self.fixture(state)
    for t in (10.,10.06):
     clock[0]=t;c.last_rows=[dict(id=1,sampled_monotonic_s=t,mode=0,torque_raw=1,status_raw=0,position_raw=2019,goal_raw=2200,internal_target_raw=2100,load_raw=160,current_raw=8,speed_raw=200)]
     result=o.observe()
    self.assertTrue(result);self.assertEqual(o.phase,'RECOVERY');self.assertTrue(o.a.blocked)
    o.brake.assert_called_once();o.m._hold.assert_called_once();self.assertEqual(o.recovery.rest_s,.5)
 def test_stale_feedback_fault_is_latched_without_auto_resume(self):
  o,c,b,clock=self.fixture();c.last_rows=[dict(id=1,sampled_monotonic_s=8.,mode=0,torque_raw=1,status_raw=0,position_raw=2019,goal_raw=2200,internal_target_raw=2100,load_raw=160,current_raw=8,speed_raw=200)]
  self.assertTrue(o.observe());self.assertEqual(o.phase,'FAULT');self.assertEqual(c.state,'FAULT');self.assertTrue(o.service())
 def test_long_profile_work_remains_monitored_between_uart_operations_all_states(self):
  from shared.experiments.presentation_id1_safety_20261110.adapter import Adapter
  for state in ('normal','interested','happy','angry','afraid','sleepy'):
   with self.subTest(state=state):
    o,c,b,clock=self.fixture(state)
    writes=[]
    fake=SimpleNamespace(read=lambda *a:b'actual',write=lambda *a:writes.append(a),sync_positions=lambda *a:None,close=lambda:None)
    o.a=Adapter(fake);o.a.owner=o
    def row():return dict(id=1,sampled_monotonic_s=clock[0],mode=0,torque_raw=1,status_raw=0,position_raw=2019,goal_raw=2019,internal_target_raw=2019,load_raw=0,current_raw=0,speed_raw=0)
    o.row=row
    for n in range(40):
     clock[0]=10.+n*.016
     fake.read(2,41,1);fake.write(2,41,b'\10')
    self.assertEqual(len(writes),40);self.assertEqual(o.phase,'MONITOR')
    samples=[__import__('json').loads(line)['row']['sampled_monotonic_s'] for line in o.log.getvalue().splitlines()]
    self.assertGreater(len(samples),10);self.assertLessEqual(max(y-x for x,y in zip(samples,samples[1:])),.064)
 def test_q_cleanup_cannot_raise_monitor_interrupt_or_send_new_base_goal(self):
  import threading
  o,c,b,clock=self.fixture();o.m.stopping=threading.Event();o.m.stopping.set()
  o.guard.last_stamp=1.;o.row=Mock(side_effect=AssertionError('No extra monitoring during Q cleanup'))
  o.poll();self.assertTrue(o.a.blocked);o.row.assert_not_called()
 def test_controller_fault_latches_safety_instead_of_continuing_monitor(self):
  o,c,b,clock=self.fixture();c.state='FAULT';c.last_error='camera stale'
  self.assertTrue(o.observe());self.assertEqual(o.phase,'FAULT');self.assertTrue(o.a.blocked)
  self.assertIn('camera stale',o.reason)
 def test_each_open_path_case_starts_new_guard_after_settling_gap(self):
  from unittest.mock import patch
  from shared.experiments.resistance_id1_20261109.test_fast_stop import FastTests
  b=FastTests().bus();o=Owner.__new__(Owner);o.b=b;o.a=SimpleNamespace(internal=internal);o.clock=lambda:10.;o.test={'case':0};o.event=Mock();old=object();o.guard=old
  def write(bus,address,data,ack,clock):b.b[8:15]=data
  with patch('shared.experiments.presentation_id1_safety_20261110.owner._write',write):o.start_test_case()
  self.assertIsNot(o.guard,old);self.assertIsNone(o.guard.last_stamp)
 def test_manual_stop_cancels_recovery_and_never_autoresumes(self):
  o=Owner.__new__(Owner);o.a=SimpleNamespace(blocked=False);o.phase='RECOVERY';o.recovery=object();o.test=object();o.brake=Mock();o.event=Mock()
  o.manual_stop();self.assertEqual(o.phase,'MANUAL');self.assertIsNone(o.recovery);self.assertTrue(o.a.blocked)
  self.assertTrue(o.service());o.brake.assert_called_once()
 def test_six_states_clear_to_normal_without_replaying_queued_inputs(self):
  import test_three_state_behavior
  for state in ('normal','interested','happy','angry','afraid','sleepy'):
   with self.subTest(state=state):
    m,b=test_three_state_behavior.Tests().motor();m.behavior_trial=state;m.presentation_normal_preserve_yaw=True
    m.automatic_fsm=SimpleNamespace(discard_inputs=Mock(),fsm=object(),applied=state,faulted=False)
    o=Owner.__new__(Owner);o.m=m;o.b=b;o.a=SimpleNamespace(internal=internal,blocked=True);o.event=Mock()
    o.return_normal()
    self.assertEqual(o.phase,'MONITOR');self.assertFalse(o.a.blocked);self.assertIsNone(m.automatic_fsm.fsm)
    self.assertEqual(m.behavior_trial,'normal_transition');self.assertTrue(m.controller.pose_route.force_normal)
    m.automatic_fsm.discard_inputs.assert_called_once()
 def test_no_target_is_not_a_block_but_near_and_missing_feedback_are(self):
  from distance_behavior import DistanceGate
  sample={'received_s':10.,'range_status_raw':4,'measurement_state':'no_target','distance_cm':None}
  o=Owner.__new__(Owner);o.m=SimpleNamespace(now=lambda:10.,distance_gate=DistanceGate(),physical_distance=SimpleNamespace(latest=lambda:sample))
  self.assertTrue(o.tof_allows())
  sample.update(distance_cm=15.,range_status_raw=9,measurement_state='range');self.assertFalse(o.tof_allows())
  sample.update(received_s=5.);self.assertFalse(o.tof_allows())
