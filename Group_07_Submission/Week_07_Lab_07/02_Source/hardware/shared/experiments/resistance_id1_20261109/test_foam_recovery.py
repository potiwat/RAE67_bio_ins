import unittest
from shared.experiments.resistance_id1_20261109.foam_recovery import Recovery

class RecoveryTests(unittest.TestCase):
 def test_short_rest_waits_half_second_after_stationary_confirmation(self):
  p=Recovery(2347,native_probe=True,rest_s=.5);p.pause(0.)
  first=None
  for k in range(11):
   t=k*.1;action=p.update(self.row(t),t)
   if action:first=(t,action);break
  self.assertIsNotNone(first);self.assertEqual(first[1],'PROBE');self.assertGreaterEqual(first[0],.8-1e-9);self.assertLessEqual(first[0],.9)
 def test_short_rest_never_skips_new_motion_or_settling(self):
  p=Recovery(2347,rest_s=.5);p.pause(0.)
  for k in range(4):self.assertIsNone(p.update(self.row(k*.1),k*.1))
  for k in range(4,10):self.assertIsNone(p.update(self.row(k*.1,speed=50),k*.1))
  for k in range(10,13):self.assertIsNone(p.update(self.row(k*.1),k*.1))
 def test_unreviewed_probe_wait_is_rejected(self):
  for value in (0,.1,1.,True,None):
   with self.assertRaises(ValueError):Recovery(2347,rest_s=value)
 def test_recorded_low_progress_probe_explains_pause_instead_of_silent_wait(self):
  p=Recovery(2347,native_probe=True);self.ready(p);p.issued(3.)
  action=None
  for k in range(1,7):
   r=self.row(3.+k*.1,torque=1,goal=2012);r.update(target_speed_raw=600,acceleration_raw=3,load_raw=38,current_raw=1)
   action=p.update(r,3.+k*.1)
   if action:break
  self.assertEqual(action,'PAUSE');self.assertIn('sustained',p.pause_reason)
 def row(self,t,q=2000,torque=2,speed=0,goal=2000):return dict(id=1,sampled_monotonic_s=t,mode=0,torque_raw=torque,status_raw=0,position_raw=q,cap=160,speed_raw=speed,moving_raw=bool(speed),goal_raw=goal,internal_target_raw=goal,current_raw=0,load_raw=0,target_speed_raw=17 if torque==1 else 600,acceleration_raw=1 if torque==1 else 3)
 def ready(self,p,t=0):
  p.pause(t)
  for k in range(27):
   a=p.update(self.row(t+k*.1),t+k*.1)
   if a is not None:break
  return a
 def test_probe_waits_for_stationary_then_has_bounded_goal(self):
  p=Recovery(2347);self.assertEqual(self.ready(p),'PROBE');self.assertEqual(p.probe_target,2016);self.assertEqual(p.attempts,1)
 def test_no_encoder_progress_cannot_resume_even_with_zero_effort(self):
  p=Recovery(2347);self.ready(p);p.issued(2.6)
  action=None
  for k in range(1,62):action=p.update(self.row(2.6+k*.1,torque=1,goal=2016),2.6+k*.1)
  self.assertEqual(action,'PAUSE');self.assertNotEqual(p.phase,'RESUMED')
 def test_actual_progress_and_settling_allow_resume(self):
  p=Recovery(2347);self.ready(p);p.issued(2.6)
  a=None
  for k in range(1,27):
   a=p.update(self.row(2.6+k*.1,q=2014,torque=1,goal=2016),2.6+k*.1)
   if a is not None:break
  self.assertEqual(a,'RESUME')
 def test_fault_or_motion_never_counts_as_clearance(self):
  p=Recovery(2347);p.pause(0)
  for k in range(30):self.assertNotEqual(p.update(self.row(k*.1,speed=100),k*.1),'PROBE')
  with self.assertRaises(RuntimeError):p.update(self.row(3.),3.3)
 def test_obstruction_retries_continue_beyond_three_without_ratcheting(self):
  p=Recovery(2347);t=0
  for _ in range(7):
   self.assertEqual(self.ready(p,t),'PROBE');self.assertEqual(p.probe_target,2016);p.issued(t+2.6);t+=6.
  self.assertEqual(p.attempts,7)
 def test_repeated_partial_progress_cannot_advance_probe_target(self):
  p=Recovery(2347);self.ready(p);p.issued(2.6);p.pause(6.)
  for k in range(30):
   action=p.update(self.row(6.+k*.1,q=2006,goal=2006),6.+k*.1)
   if action=='PROBE':break
  self.assertEqual(action,'PROBE');self.assertEqual(p.probe_target,2016)
 def test_probe_command_starts_at_actual_then_moves_smoothly_to_pinned_target(self):
  p=Recovery(2347);self.ready(p);p.issued(3.)
  qs=[p.command_goal(3.+i*.02) for i in range(121)]
  self.assertEqual(qs[0],2000);self.assertEqual(qs[-1],2016)
  self.assertTrue(all(0<=b-a<=1 for a,b in zip(qs,qs[1:])))
  self.assertLess(p.command_goal(3.2),2016)
 def test_delayed_iteration_cannot_send_large_probe_step(self):
  p=Recovery(2347);self.ready(p);p.issued(3.)
  self.assertEqual(p.command_goal(3.),2000)
  self.assertEqual(p.command_goal(4.9),2001)
 def test_reverse_probe_is_gradual_and_bounded(self):
  p=Recovery(1691);self.ready(p);p.issued(3.)
  qs=[p.command_goal(3.+i*.02) for i in range(121)]
  self.assertEqual((qs[0],qs[-1]),(2000,1984))
  self.assertTrue(all(-1<=b-a<=0 for a,b in zip(qs,qs[1:])))
 def test_encoder_progress_cannot_resume_before_ramp_finishes(self):
  p=Recovery(2347);self.ready(p);p.issued(3.)
  for k in range(1,19):self.assertIsNone(p.update(self.row(3.+k*.1,q=2014,torque=1,goal=2016),3.+k*.1))
 def test_low_effort_motion_can_handoff_without_stopping_first(self):
  p=Recovery(2347);self.ready(p);p.issued(3.)
  actions=[p.update(self.row(4.4+k*.04,q=2010+k,torque=1,speed=50,goal=2014),4.4+k*.04) for k in range(4)]
  self.assertEqual(actions,[None,None,None,'RESUME']);self.assertEqual(p.resume_kind,'moving')
 def test_single_zero_speed_sample_does_not_erase_encoder_progress(self):
  p=Recovery(2347);self.ready(p);p.issued(3.)
  actions=[p.update(self.row(4.4+k*.04,q=2004+2*k,torque=1,speed=v,goal=2012),4.4+k*.04) for k,v in enumerate((50,0,50,50))]
  self.assertEqual(actions,[None,None,None,'RESUME'])
 def test_fixed_native_profile_uses_same_limits_and_encoder_evidence(self):
  p=Recovery(2347,native_probe=True);self.ready(p);p.issued(3.)
  actions=[]
  for k in range(4):
   r=self.row(4.4+k*.04,q=2004+2*k,torque=1,speed=50,goal=2012);r.update(target_speed_raw=600,acceleration_raw=3)
   actions.append(p.update(r,4.4+k*.04))
  self.assertEqual(actions,[None,None,None,'RESUME']);self.assertEqual(p.probe_target,2016)
 def test_motion_history_qualifies_before_probe_reaches_its_stop(self):
  p=Recovery(2347);self.ready(p);p.issued(3.)
  actions=[p.update(self.row(4.4+k*.04,q=2004+2*k,torque=1,speed=50,goal=2012),4.4+k*.04) for k in range(4)]
  self.assertEqual(actions,[None,None,None,'RESUME']);self.assertEqual(p.resume_kind,'moving')
 def test_reverse_motion_can_handoff_in_its_original_direction(self):
  p=Recovery(1691);self.ready(p);p.issued(3.)
  actions=[p.update(self.row(4.4+k*.04,q=1996-2*k,torque=1,speed=32818,goal=1988),4.4+k*.04) for k in range(4)]
  self.assertEqual(actions,[None,None,None,'RESUME'])
 def test_handoff_rejects_no_progress_effort_or_wrong_direction(self):
  for case in ('stationary','effort','backward','duplicate'):
   p=Recovery(2347);self.ready(p);p.issued(3.)
   for k in range(4):
    t=4.4+(0 if case=='duplicate' else k*.04)
    r=self.row(t,q=2010 if case=='stationary' else 2010+k,torque=1,speed=32818 if case=='backward' else 50,goal=2014)
    if case=='effort':r['load_raw']=40
    self.assertNotEqual(p.update(r,t),'RESUME')
