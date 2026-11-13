import unittest
try:
 from shared.experiments.resistance_id1_20261109.pause_guard import ID1PauseGuard
except ImportError:ID1PauseGuard=None

class Tests(unittest.TestCase):
 def test_guard_exists(self):self.assertIsNotNone(ID1PauseGuard,'Pilot pause guard not implemented')
 def setUp(self):
  if ID1PauseGuard is None and self._testMethodName!='test_guard_exists':self.skipTest('Not implemented')
 def row(self,t,q=2000,error=15,current=4,duty=40):
  return dict(id=1,sampled_monotonic_s=t,mode=0,torque_raw=1,status_raw=0,position_raw=q,goal_raw=q+error,
   internal_target_raw=q+error,current_raw=current,load_raw=duty)
 def test_blocked_sequence_latches_after_fresh_sustained_evidence(self):
  g=ID1PauseGuard()
  for i in range(3):self.assertEqual(g.update(self.row(i*.1),i*.1)['state'],'MONITORING')
  r=g.update(self.row(.3),.3);self.assertEqual(r['state'],'RESISTANCE_PAUSE');self.assertTrue(r['trip'])
  self.assertEqual(g.update(self.row(.4,error=0,current=0,duty=0),.4)['state'],'RESISTANCE_PAUSE')
 def test_normal_motion_with_large_error_does_not_trip(self):
  g=ID1PauseGuard()
  for i in range(30):self.assertEqual(g.update(self.row(i*.05,q=2000+i*5,error=100),i*.05)['state'],'MONITORING')
 def test_irregular_fresh_sampling_still_confirms_sustained_block(self):
  g=ID1PauseGuard()
  for t in (0.,.07,.14,.22):self.assertFalse(g.update(self.row(t),t)['trip'])
  self.assertTrue(g.update(self.row(.31),.31)['trip'])
 def test_paused_state_keeps_sampling_health_without_auto_resume(self):
  g=ID1PauseGuard()
  for i in range(4):g.update(self.row(i*.1),i*.1)
  for i in range(4,25):
   self.assertEqual(g.update(self.row(i*.1,error=0,current=0,duty=0),i*.1)['state'],'RESISTANCE_PAUSE')
 def test_low_error_low_effort_and_direction_reversal(self):
  for change in ('error','effort'):
   g=ID1PauseGuard()
   for i in range(20):
    row=self.row(i*.05,error=4 if change=='error' else 15,current=0,duty=4 if change=='effort' else 40)
    self.assertFalse(g.update(row,i*.05)['trip'])
  g=ID1PauseGuard()
  for i in range(6):self.assertFalse(g.update(self.row(i*.1,error=15 if i<3 else -15),i*.1)['trip'])
 def test_duplicate_frames_do_not_supply_confirmation_time(self):
  g=ID1PauseGuard();r=self.row(0.)
  g.update(r,0.)
  for t in (.05,.1):self.assertFalse(g.update(r,t)['trip'])
  self.assertEqual(g.update(r,.3)['state'],'FAULT_HOLD')
 def test_stale_bad_status_torque_and_missing_signal_hold(self):
  for patch in [dict(sampled_monotonic_s=-1.),dict(torque_raw=0),dict(status_raw=1),dict(mode=1),dict(current_raw=None),dict(load_raw=65535)]:
   g=ID1PauseGuard();r=g.update({**self.row(0.),**patch},0.);self.assertEqual(r['state'],'FAULT_HOLD')
   self.assertEqual(g.update(self.row(.1),.1)['state'],'FAULT_HOLD')
 def test_manual_clearance_required_and_fault_cannot_auto_reset(self):
  g=ID1PauseGuard()
  for i in range(4):g.update(self.row(i*.1),i*.1)
  with self.assertRaises(ValueError):g.resume(clearance_confirmed=False)
  g.resume(clearance_confirmed=True);self.assertEqual(g.state,'MONITORING')
  g.update({**self.row(.4),'status_raw':1},.4)
  with self.assertRaises(ValueError):g.resume(clearance_confirmed=True)
 def test_regressing_clock_and_wrong_joint_do_not_resume(self):
  for t in (-1.,float('nan'),1.):
   g=ID1PauseGuard();g.update(self.row(.1),.1)
   self.assertEqual(g.update(self.row(t),t)['state'],'FAULT_HOLD')
  g=ID1PauseGuard();self.assertEqual(g.update({**self.row(0.),'id':2},0.)['state'],'FAULT_HOLD')

if __name__=='__main__':unittest.main()
