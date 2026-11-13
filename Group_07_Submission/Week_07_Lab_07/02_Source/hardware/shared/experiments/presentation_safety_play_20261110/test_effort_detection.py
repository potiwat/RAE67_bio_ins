"""Advisory candidate only; no motor/network access."""
import unittest

class Tests(unittest.TestCase):
 def test_id1_post_stop_push_in_every_state_waits_for_release_then_returns(self):
  import tempfile
  from pathlib import Path
  from functools import partial
  from unittest.mock import patch
  from .test_integration import TrialPlant,harness
  from .integration import hooks
  from shared.experiments.central_safety_controller_20261110.scenarios import contact_in_state
  class DeflectedPlant(TrialPlant):
   def refresh(self,i):
    super().refresh(i)
    if i==1 and getattr(self,'deflect',False):
     a=self.ram[i];a[56:58]=(int.from_bytes(a[42:44],'little')-17).to_bytes(2,'little');a[60:62]=(90).to_bytes(2,'little');a[69:71]=(5).to_bytes(2,'little')
  for state in('normal','interested','happy','angry','afraid','sleepy'):
   def after(w):
    a=w.motor.bus.central_feedback.brake_capture
    if a.stop_writer is not None and a.stop_writer.verified and not hasattr(w,'push_started'):w.push_started=w.clock()
    if hasattr(w,'push_started'):
     w.plant.deflect=w.clock()-w.push_started<.7
    if a.core.phase=='WAIT_CLEARANCE':w.motor.key(ord('r'))
   with self.subTest(state=state),tempfile.TemporaryDirectory()as out,patch.object(harness,'Plant',DeflectedPlant),patch.object(harness,'hooks',partial(hooks,isolate_tof=True,effort_stop=True)):
    r,w=harness.run(Path(out),contact_in_state(state,1,after),seconds=30,enabled_ids=range(1,6),dark=True)
    self.assertEqual(r['phase'],'NORMAL_PARKED',r['error']);self.assertEqual(r['reset']['h'],0.)
    self.assertTrue(w.motor.bus.central_feedback.brake_capture.writers[0].audit['id1_contact_deflection']['stop_quality_bound_exceeded'])
    self.assertTrue(any(e['event']=='MANUAL_R_REJECTED'for e in r['events']))
 def test_integrated_moving_resistance_stops_resets_and_parks(self):
  import tempfile
  from pathlib import Path
  from functools import partial
  from unittest.mock import patch
  from .test_integration import TrialPlant,harness
  from .integration import hooks
  from shared.experiments.central_safety_controller_20261110.scenarios import contact_in_state
  class SlidingPlant(TrialPlant):
   def refresh(self,i):
    super().refresh(i)
    if i==1 and i in self.contact and i not in self.held_ids and self.ram[i][40]==1:
     q=int.from_bytes(self.ram[i][56:58],'little');self.ram[i][56:58]=(q+1).to_bytes(2,'little')
  def after(w):
   a=w.motor.bus.central_feedback.brake_capture
   if a.core.phase=='WAIT_CLEARANCE':w.motor.key(ord('r'))
  with tempfile.TemporaryDirectory()as out,patch.object(harness,'Plant',SlidingPlant),patch.object(harness,'hooks',partial(hooks,isolate_tof=True,effort_stop=True)):
   r,w=harness.run(Path(out),contact_in_state('happy',1,after),seconds=20,enabled_ids=range(1,6),dark=True)
  self.assertEqual(r['phase'],'NORMAL_PARKED',r['error']);self.assertEqual(r['reset']['h'],0.)
  evidence=[e for e in r['events']if e['event']=='ID1_EXCESS_EFFORT_STOP_REQUEST']
  self.assertTrue(evidence);self.assertGreater(evidence[0]['evidence']['encoder_span_ticks'],2)
  self.assertTrue(r['cleanup_confirmed'])
 def test_free_runtime_with_effort_stop_enabled_remains_playing(self):
  import tempfile
  from pathlib import Path
  from functools import partial
  from unittest.mock import patch
  from .test_integration import TrialPlant,harness
  from .integration import hooks
  with tempfile.TemporaryDirectory()as out,patch.object(harness,'Plant',TrialPlant),patch.object(harness,'hooks',partial(hooks,isolate_tof=True,effort_stop=True)):
   r,w=harness.run(Path(out),seconds=5,enabled_ids=range(1,6),dark=True)
  self.assertEqual(r['phase'],'PLAY');self.assertIsNone(r['error']);self.assertEqual(r['stops'],[])
 def config(self):
  return dict(stall_window_s=.3,minimum_samples=4,maximum_gap_s=.2,ids={'1':dict(current_limit_raw=2,pwm_limit_raw=72,internal_error_limit_ticks=22)})
 def row(self,t,q=2000,current=5,error=30,pwm=90):
  return dict(id=1,time_s=t,position_raw=q,current_raw=current,pwm_magnitude_raw=pwm,internal_error_ticks=error,decision='MONITOR')
 def test_sustained_excess_effort_is_detected_even_if_encoder_keeps_moving(self):
  from .effort_detection import ID1EffortEvidence
  m=ID1EffortEvidence(self.config())
  results=[m.update(self.row(1+k*.05,q=2000+k*6))for k in range(8)]
  self.assertTrue(results[-1]['candidate_stop']);self.assertGreater(results[-1]['encoder_span_ticks'],2)
 def test_transients_gaps_native_fault_and_other_axes_cannot_make_candidate(self):
  from .effort_detection import ID1EffortEvidence
  m=ID1EffortEvidence(self.config())
  for k in range(4):self.assertFalse(m.update(self.row(1+k*.05))['candidate_stop'])
  self.assertFalse(m.update(self.row(1.2,current=0))['candidate_stop'])
  for k in range(4):self.assertFalse(m.update(self.row(2+k*.05))['candidate_stop'])
  bad=self.row(2.2);bad['decision']='WOULD_HOLD_DATA';self.assertFalse(m.update(bad)['candidate_stop'])
  other=self.row(2.3);other['id']=2;self.assertFalse(m.update(other)['candidate_stop'])
 def test_direction_change_and_duplicate_timestamp_reset_evidence(self):
  from .effort_detection import ID1EffortEvidence
  m=ID1EffortEvidence(self.config())
  for k in range(6):self.assertFalse(m.update(self.row(1+k*.05))['candidate_stop'])
  self.assertFalse(m.update(self.row(1.3,error=-30))['candidate_stop'])
  self.assertFalse(m.update(self.row(1.3,error=-30))['candidate_stop'])

if __name__=='__main__':unittest.main()

class JointEvidenceTests(unittest.TestCase):
 def config(self):return dict(stall_window_s=.3,minimum_samples=4,maximum_gap_s=.2,ids={'2':dict(current_limit_raw=40,pwm_limit_raw=358,internal_error_limit_ticks=44)})
 def test_id2_persistent_effort_detects_sliding_without_changing_thresholds(self):
  from .effort_detection import JointEffortEvidence
  m=JointEffortEvidence(self.config(),2)
  for k in range(8):r=m.update(dict(id=2,time_s=1+k*.05,position_raw=2600+k*3,current_raw=73,pwm_magnitude_raw=379,internal_error_ticks=-47,decision='MONITOR'))
  self.assertTrue(r['candidate_stop']);self.assertGreater(r['encoder_span_ticks'],2)
 def test_id2_calm_transients_and_other_axis_do_not_trip(self):
  from .effort_detection import JointEffortEvidence
  m=JointEffortEvidence(self.config(),2)
  for k in range(8):
   r=m.update(dict(id=2,time_s=1+k*.05,position_raw=2600+k*3,current_raw=40,pwm_magnitude_raw=358,internal_error_ticks=-44,decision='MONITOR'))
   self.assertFalse(r['candidate_stop'])
  self.assertFalse(m.update(dict(id=1,time_s=2.,decision='MONITOR'))['candidate_stop'])


class MovingJointWorkerTests(unittest.TestCase):
 def test_id1_id2_moving_effort_stops_resets_and_returns_in_all_six_states(self):
  import tempfile
  from pathlib import Path
  from functools import partial
  from unittest.mock import patch
  from .test_integration import TrialPlant,harness
  from .integration import hooks,consent
  from shared.experiments.central_safety_controller_20261110.scenarios import contact_in_state
  for axis in(1,2):
   class SlidingJoint(TrialPlant):
    def refresh(self,i):
     super().refresh(i)
     if i==axis and i in self.contact and i not in self.held_ids and self.ram[i][40]==1:
      q=int.from_bytes(self.ram[i][56:58],'little');self.ram[i][56:58]=(q+1).to_bytes(2,'little')
   for state in('normal','interested','happy','angry','afraid','sleepy'):
    def after(w):
     a=w.motor.bus.central_feedback.brake_capture
     if a.core.phase=='WAIT_CLEARANCE'and a.id1_contact_released():w.motor.key(ord('r'))
    with self.subTest(axis=axis,state=state),tempfile.TemporaryDirectory()as out,patch.object(harness,'Plant',SlidingJoint),patch.object(harness,'hooks',partial(hooks,trial_consent=consent((axis,)),isolate_tof=True,effort_stop=axis==1,id2_contact_recovery=axis==2,id2_effort_stop=axis==2)):
     r,w=harness.run(Path(out),contact_in_state(state,axis,after),seconds=40,enabled_ids=(axis,),dark=True)
    self.assertEqual(r['phase'],'NORMAL_PARKED',r['error']);self.assertEqual(r['reset']['h'],0.)
    evidence=[e for e in r['events']if e['event']=='ID'+str(axis)+'_EXCESS_EFFORT_STOP_REQUEST']
    self.assertTrue(evidence);self.assertGreater(evidence[0]['evidence']['encoder_span_ticks'],2)
    self.assertTrue(r['cleanup_confirmed'])
    self.assertEqual(w.motor.bus.central_feedback.brake_capture.writers[0].contact_axis,axis)

class ReturningEffortTests(unittest.TestCase):
 def test_id1_id2_contact_during_normal_return_preempts_return_again(self):
  import tempfile
  from pathlib import Path
  from functools import partial
  from unittest.mock import patch
  from .test_integration import TrialPlant,harness
  from .integration import hooks,consent
  from shared.experiments.central_safety_controller_20261110.scenarios import contact_in_state
  for axis in(1,2):
   class SlidingJoint(TrialPlant):
    def refresh(self,i):
     super().refresh(i)
     if i==axis and i in self.contact and i not in self.held_ids and self.ram[i][40]==1:
      q=int.from_bytes(self.ram[i][56:58],'little');self.ram[i][56:58]=(q+1).to_bytes(2,'little')
   def after(w):
    a=w.motor.bus.central_feedback.brake_capture
    if a.core.phase=='RETURNING'and not hasattr(w,'return_contact_s'):w.return_contact_s=w.clock()
    if hasattr(w,'return_contact_s')and w.clock()-w.return_contact_s<1.:
     w.plant.contact.add(axis)
    else:w.plant.contact.discard(axis)if hasattr(w,'return_contact_s')else None
    if a.core.phase=='WAIT_CLEARANCE'and a.sensor_state()=='clear'and a.id1_contact_released():w.motor.key(ord('r'))
   with self.subTest(axis=axis),tempfile.TemporaryDirectory()as out,patch.object(harness,'Plant',SlidingJoint),patch.object(harness,'hooks',partial(hooks,trial_consent=consent((axis,)),isolate_tof=True,effort_stop=axis==1,id2_contact_recovery=axis==2,id2_effort_stop=axis==2)):
    r,w=harness.run(Path(out),contact_in_state('happy',axis,after),seconds=40,enabled_ids=(axis,),dark=True)
   hits=[e for e in r['events']if e['event']=='ID'+str(axis)+'_EXCESS_EFFORT_STOP_REQUEST']
   self.assertGreaterEqual(len(hits),2);self.assertTrue(any(e['phase']=='RETURNING'for e in hits))
   self.assertEqual(r['phase'],'NORMAL_PARKED',r['error']);self.assertTrue(r['cleanup_confirmed'])


class FastBlockedTests(unittest.TestCase):
 def config(self):return JointEvidenceTests().config()
 def row(self,k,**kw):
  r=dict(id=2,time_s=1+k*.05,position_raw=2700,current_raw=60,pwm_magnitude_raw=300,internal_error_ticks=-25-k*5,decision='MONITOR');r.update(kw);return r
 def test_blocked_rising_reference_detected_in_point_one_seconds(self):
  from .effort_detection import ID2EffortEvidence
  m=ID2EffortEvidence(self.config());a=[m.update(self.row(k))for k in range(3)]
  self.assertFalse(a[0]['candidate_stop']);self.assertFalse(a[1]['candidate_stop']);self.assertTrue(a[2]['candidate_stop']);self.assertEqual(a[2]['path'],'fast_blocked')
 def test_motion_flat_error_low_effort_gap_and_invalid_do_not_trip(self):
  from .effort_detection import ID2EffortEvidence
  variants=[lambda k:self.row(k,position_raw=2700+k*3),lambda k:self.row(k,internal_error_ticks=-30),lambda k:self.row(k,current_raw=40),lambda k:self.row(k,pwm_magnitude_raw=250),lambda k:self.row(k,decision='WOULD_HOLD_DATA'),lambda k:self.row(k,time_s=1+k*.3)]
  for make in variants:
   m=ID2EffortEvidence(self.config())
   for k in range(3):self.assertFalse(m.update(make(k))['candidate_stop'])
 def test_direction_change_and_missing_position_reset_fast_history(self):
  from .effort_detection import ID2EffortEvidence
  for override in ({'internal_error_ticks':35},{'position_raw':None}):
   m=ID2EffortEvidence(self.config());m.update(self.row(0));m.update(self.row(1));self.assertFalse(m.update(self.row(2,**override))['candidate_stop'])
 def test_sliding_slow_path_retained(self):
  from .effort_detection import ID2EffortEvidence
  m=ID2EffortEvidence(self.config())
  for k in range(8):r=m.update(self.row(k,position_raw=2700+k*4,current_raw=73,pwm_magnitude_raw=379,internal_error_ticks=-47))
  self.assertTrue(r['candidate_stop']);self.assertNotEqual(r.get('path'),'fast_blocked')


class SensitiveMovingTests(unittest.TestCase):
 def test_recorded_interested_tracking_lag_without_growing_error_is_not_contact(self):
  from .effort_detection import ID2EffortEvidence
  m=ID2EffortEvidence(JointEvidenceTests().config())
  results=[m.update(self.row(k,position_raw=2800-k*7,current_raw=c,pwm_magnitude_raw=p,internal_error_ticks=-e))for k,(c,p,e)in enumerate(((28,255,30),(31,261,31),(35,266,32),(32,263,32)))]
  self.assertFalse(any(r['candidate_stop']for r in results))
 def row(self,k,**kw):
  r=dict(id=2,time_s=1+k*.05,position_raw=2700-k*5,current_raw=30,pwm_magnitude_raw=260,internal_error_ticks=-30,decision='MONITOR');r.update(kw);return r
 def test_continued_motion_with_moderate_sustained_effort_is_detected(self):
  from .effort_detection import ID2EffortEvidence
  m=ID2EffortEvidence(JointEvidenceTests().config());results=[m.update(self.row(k,internal_error_ticks=-26-k*2))for k in range(4)]
  self.assertFalse(any(r['candidate_stop']for r in results[:3]));self.assertTrue(results[-1]['candidate_stop']);self.assertEqual(results[-1]['path'],'moving_sensitive');self.assertGreater(results[-1]['encoder_span_ticks'],2)
 def test_boundary_low_effort_transient_native_fault_and_gaps_do_not_trip(self):
  from .effort_detection import ID2EffortEvidence
  for change in ({'current_raw':25},{'pwm_magnitude_raw':240},{'internal_error_ticks':-25},{'decision':'WOULD_HOLD_DATA'}):
   m=ID2EffortEvidence(JointEvidenceTests().config())
   for k in range(8):self.assertFalse(m.update(self.row(k,**change))['candidate_stop'])
  m=ID2EffortEvidence(JointEvidenceTests().config())
  for k in range(3):self.assertFalse(m.update(self.row(k))['candidate_stop'])
  self.assertFalse(m.update(self.row(3,current_raw=0))['candidate_stop'])
  for k in range(3):self.assertFalse(m.update(self.row(k,time_s=2+k*.3))['candidate_stop'])
