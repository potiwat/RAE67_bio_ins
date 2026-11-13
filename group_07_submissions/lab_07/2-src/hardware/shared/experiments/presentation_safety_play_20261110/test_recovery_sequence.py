import unittest
from types import SimpleNamespace as NS
from .recovery_sequence import immediate_reset_supervisor,ready_for_automatic_resume,arm_automatic_resume
from shared.experiments.central_safety_controller_20261110.supervisor import Supervisor

class Adapter:
 def __init__(self):self.calls=[];self.still=False
 def clock(self):return 1.
 def blackout_detection(self):self.calls.append('dark')
 def reset(self):self.calls.append('reset')
 def hold(self,epoch):self.calls.append('hold')
 def sensor_state(self):return 'clear'
 def tick_feedback(self):self.calls.append('feedback')
 def healthy(self):return True
 def stopped(self):return self.still

class SequenceTests(unittest.TestCase):
 def test_contact_dark_and_model_reset_precede_hold_and_do_not_wait_for_stop(self):
  a=Adapter();c=immediate_reset_supervisor(Supervisor)(a);c.request('resistance',2);c.step()
  self.assertEqual(a.calls[:3],['dark','reset','hold']);self.assertTrue(c.reset_done);self.assertEqual(c.phase,'STOPPING')
  a.still=True;c.step();self.assertEqual(a.calls.count('reset'),1);self.assertEqual(c.phase,'WAIT_CLEARANCE')
 def test_fault_does_not_grant_automatic_recovery(self):
  a=Adapter();c=immediate_reset_supervisor(Supervisor)(a);c.request('hardware_fault',2);c.step()
  self.assertFalse(c.allow_return);self.assertNotIn('reset',a.calls)
 def test_resume_requires_verified_normal_release_and_no_pending_fault(self):
  a=NS(core=NS(phase='NORMAL_PARKED',error=None,pending=None,allow_return=True),m=NS(stopping=NS(is_set=lambda:False),urgent_stop=NS(is_set=lambda:False)),healthy=lambda:True,stopped=lambda:True,id1_contact_released=lambda:True)
  self.assertTrue(ready_for_automatic_resume(a))
  a.core.phase='RETURNING';self.assertFalse(ready_for_automatic_resume(a));a.core.phase='NORMAL_PARKED'
  a.core.pending={'kind':'operator_stop'};self.assertFalse(ready_for_automatic_resume(a))
 def test_blocked_release_cannot_resume_even_at_normal(self):
  a=NS(core=NS(phase='NORMAL_PARKED',error=None,pending=None,allow_return=True),m=NS(stopping=NS(is_set=lambda:False),urgent_stop=NS(is_set=lambda:False)),healthy=lambda:True,stopped=lambda:True,id1_contact_released=lambda:False)
  self.assertFalse(ready_for_automatic_resume(a))
 def test_automatic_handoff_does_not_consume_or_wait_for_button(self):
  events=[];a=NS(core=NS(phase='NORMAL_PARKED',serial=3,hold_epoch=2,error=None,pending=None,allow_return=True,record=lambda *args,**kw:events.append(args[0])),m=NS(stopping=NS(is_set=lambda:False),urgent_stop=NS(is_set=lambda:False),controller=NS(last_rows=[dict(id=i,goal_raw=2000+i)for i in range(1,6)])),healthy=lambda:True,stopped=lambda:True,id1_contact_released=lambda:True,restart_claimed=False,restart_request=None)
  self.assertTrue(arm_automatic_resume(a));self.assertEqual(a.restart_request,(3,2));self.assertEqual(a.restart_hold_goals[2],2002)
  self.assertEqual(events,['AUTO_PLAY_RESUME_READY']);self.assertFalse(arm_automatic_resume(a))
 def test_detection_dark_request_never_calls_physical_led_before_native_brake(self):
  from unittest.mock import Mock
  from .integration import adapter_class,consent
  a=object.__new__(adapter_class(consent()));ring=Mock();ring.close.side_effect=AssertionError('LED blocks brake')
  a.m=NS(led_ring=ring);a.blackout_detection()
  ring.close.assert_not_called();self.assertTrue(a.m.safety_recovery_led_off);self.assertFalse(a.m.presentation_led_output['off_command_completed'])
 def test_reset_failure_uses_native_fallback_before_physical_dark(self):
  from unittest.mock import patch
  from .test_integration import run
  from .integration import BaseAdapter
  from shared.experiments.central_safety_controller_20261110.scenarios import contact_in_state
  with patch.object(BaseAdapter,'reset',side_effect=RuntimeError('reset failed')):
   r,w=run(contact_in_state('happy',1),seconds=15)
  a=w.motor.bus.central_feedback.brake_capture
  self.assertEqual(r['phase'],'LATCHED');self.assertIn('reset failed',r['error'])
  self.assertTrue(a.fallback_report['attempted']);self.assertIsNone(w.motor.led_ring)
 def test_all_states_can_return_and_arm_play_without_r_or_button_after_synthetic_probe(self):
  import tempfile
  from pathlib import Path
  from unittest.mock import patch
  from .test_integration import harness,TrialPlant
  from .integration import hooks,consent
  from .restart import take_restart
  from shared.experiments.central_safety_controller_20261110.scenarios import contact_in_state
  for state in('normal','interested','happy','angry','afraid','sleepy'):
   def after(w):
    a=w.motor.bus.central_feedback.brake_capture
    if w.clearance and a.core.phase=='WAIT_CLEARANCE':
     # Synthetic external probe evidence tests sequence only, not hardware clearance.
     a.clear_token=(a.core.serial,a.core.hold_epoch);a.clearance_source='SYNTHETIC_TEST_PROBE'
    if take_restart(w.motor,255):w.auto_claimed=True;w.motor.stopping.set()
   with self.subTest(state=state),tempfile.TemporaryDirectory()as d,patch.object(harness,'Plant',TrialPlant),patch.object(harness,'hooks',lambda *a,**kw:hooks(*a,**{**kw,'trial_consent':consent((1,2,4)),'resume_after_normal':True})):
    r,w=harness.run(Path(d),contact_in_state(state,2,after),seconds=35,enabled_ids=())
    self.assertTrue(getattr(w,'auto_claimed',False),r.get('error'));self.assertIsNone(r['error'])
    events=[x['event']for x in r['events']]
    self.assertIn('AUTO_PLAY_RESUME_READY',events);self.assertNotIn('OPERATOR_CLEARANCE_R',events);self.assertNotIn('BUTTON_RESTART_ARMED',events)
 def test_native_capture_failure_reaches_fallback_before_physical_led_cleanup(self):
  from unittest.mock import patch
  from .test_integration import run
  from .native_stop import GroupStop
  from shared.experiments.central_safety_controller_20261110.scenarios import contact_in_state
  calls=[]
  with patch.object(GroupStop,'commit',side_effect=RuntimeError('capture failed')),patch.object(GroupStop,'recover_after_unstarted_failure',side_effect=lambda *a:calls.append('native_fallback')),patch('shared.experiments.presentation_safety_play_20261110.integration.blackout_output',side_effect=lambda *a:calls.append('physical_led_off')):
   r,w=run(contact_in_state('happy',1),seconds=15)
  self.assertEqual(r['phase'],'LATCHED');self.assertIn('native_fallback',calls);self.assertLess(calls.index('native_fallback'),calls.index('physical_led_off'))

if __name__=='__main__':unittest.main()
