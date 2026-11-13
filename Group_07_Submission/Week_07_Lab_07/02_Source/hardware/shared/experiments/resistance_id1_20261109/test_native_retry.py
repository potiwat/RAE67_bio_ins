import unittest
from shared.experiments.resistance_id1_20261109.test_pilot import Tests
try:
 from shared.experiments.resistance_id1_20261109.native_retry import NativeRetry
except ImportError:NativeRetry=None

class NativeTests(unittest.TestCase):
 def motor(self):
  m,d,b=Tests().motor();m.id1_tof_observe_only=True
  return m,d,b
 def tick(self,p,m,d,b,t,follow=True,effort=1):
  q=b.goals[1] if follow else b.actual
  b.actual=q
  for r in m.controller.last_rows:r['sampled_monotonic_s']=t
  m.controller.last_rows[0].update(position_raw=q,goal_raw=b.goals[1],internal_target_raw=b.goals[1],load_raw=40 if effort>=3 else 0,current_raw=effort)
  p.step(d,m,t)
 def test_native_sweep_uses_far_endpoint_not_incremental_20tick_goals(self):
  self.assertIsNotNone(NativeRetry)
  m,d,b=self.motor();p=NativeRetry();self.tick(p,m,d,b,0.);self.tick(p,m,d,b,.05)
  self.assertEqual(b.goals[1],2347);self.assertGreater(abs(b.goals[1]-2019),114)
 def test_low_effort_without_encoder_progress_cannot_resume_and_stops_after_three_probes(self):
  self.assertIsNotNone(NativeRetry)
  m,d,b=self.motor();p=NativeRetry()
  for k in range(350):self.tick(p,m,d,b,k*.05,follow=False,effort=4 if k<20 else 0)
  self.assertEqual(p.attempts,3);self.assertEqual(p.phase,'LATCHED')
  self.assertFalse(any(e['event']=='auto_resume' for e in p.events))
  count=len(b.writes)
  for k in range(350,370):self.tick(p,m,d,b,k*.05,follow=False,effort=0)
  self.assertEqual(len(b.writes),count)
 def test_success_requires_progress_and_resumes_only_after_probe_hold_settles(self):
  self.assertIsNotNone(NativeRetry)
  m,d,b=self.motor();p=NativeRetry()
  for k in range(25):self.tick(p,m,d,b,k*.05,follow=False,effort=4)
  self.assertEqual(p.phase,'WAIT')
  for k in range(25,150):
   self.tick(p,m,d,b,k*.05,follow=True,effort=0)
   if any(e['event']=='auto_resume' for e in p.events):break
  self.assertTrue(any(e['event']=='probe_pass' for e in p.events))
  self.assertTrue(any(e['event']=='auto_resume' for e in p.events));self.assertEqual(p.attempts,1)
 def test_stop_blocks_all_motion_and_attempts(self):
  self.assertIsNotNone(NativeRetry)
  m,d,b=self.motor();p=NativeRetry();m.urgent_stop.set()
  self.tick(p,m,d,b,0.);self.assertEqual(b.writes,[]);self.assertEqual(p.attempts,0)

 def test_stale_encoder_is_fault_and_does_not_start_retry(self):
  m,d,b=self.motor();p=NativeRetry();self.tick(p,m,d,b,0.)
  with self.assertRaisesRegex(RuntimeError,'feedback fault'):p.step(d,m,.19)
  self.assertEqual(p.attempts,0)
 def test_probe_commands_never_exceed_eight_ticks_from_start(self):
  m,d,b=self.motor();p=NativeRetry();probe=[]
  for k in range(200):
   self.tick(p,m,d,b,k*.05,follow=False,effort=4 if k<20 else 0)
   if p.phase=='PROBE':probe.append((b.goals[1],p.probe_start))
  self.assertTrue(probe);self.assertTrue(all(abs(q-start)<=8 for q,start in probe))

 def test_real_five_tick_settled_residual_reverses_without_offset_or_pid_change(self):
  m,d,b=self.motor();p=NativeRetry();self.tick(p,m,d,b,0.);self.tick(p,m,d,b,.05)
  b.actual=2342
  for k in range(2,9):self.tick(p,m,d,b,k*.05,follow=False,effort=0)
  self.assertEqual(b.goals[1],1691)
  b.actual=1696
  for k in range(9,16):self.tick(p,m,d,b,k*.05,follow=False,effort=0)
  self.assertEqual(b.goals[1],2347)
  self.assertEqual(p.phase,'RUN');self.assertEqual(p.attempts,0)
 def test_endpoint_residual_does_not_count_as_arrival_while_high_effort_or_moving(self):
  m,d,b=self.motor();p=NativeRetry();self.tick(p,m,d,b,0.);self.tick(p,m,d,b,.05)
  b.actual=2342
  for k in range(2,8):self.tick(p,m,d,b,k*.05,follow=False,effort=4)
  self.assertEqual(b.goals[1],2347)

 def test_repeated_native_cycles_finish_with_five_tick_encoder_residual(self):
  m,d,b=self.motor();p=NativeRetry()
  for k in range(920):
   if p.started is not None:
    b.actual=b.goals[1]-5 if b.goals[1]>2019 else b.goals[1]+5
   self.tick(p,m,d,b,k*.05,follow=False,effort=0)
   if p.complete:break
  self.assertTrue(p.complete);self.assertEqual(p.attempts,0)
  self.assertGreaterEqual(sum(e['event']=='settled_endpoint' for e in p.events),2)
 def test_endpoint_does_not_reverse_while_moving_even_with_small_error(self):
  m,d,b=self.motor();p=NativeRetry();self.tick(p,m,d,b,0.);self.tick(p,m,d,b,.05)
  b.actual=2342;m.controller.last_rows[0]['moving_raw']=1
  for k in range(2,9):self.tick(p,m,d,b,k*.05,follow=False,effort=0)
  self.assertEqual(b.goals[1],2347)
