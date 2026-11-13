import unittest
from types import SimpleNamespace as NS
try:
 from shared.experiments.resistance_id1_20261109.pilot import poll_startup_distance
except ImportError:poll_startup_distance=None

class Tests(unittest.TestCase):
 def test_wrapper_exists(self):self.assertIsNotNone(poll_startup_distance)
 def setUp(self):
  if poll_startup_distance is None and self._testMethodName!='test_wrapper_exists':self.skipTest('Not implemented')
 def motor(self):
  from test_taught_crouch import Tests as Fixture
  from bio_inspire.runtime.distance_behavior import DistanceGate
  m,b=Fixture().motor();m.controller.state='NORMAL_STARTUP';m.lab07_pair_id='resistance_id1_R2_pilot'
  m.normal_measurement=NS(state='waiting');m.lab07_start_gate=NS(started=False)
  m.presentation_startup_tof_recovery=False;m.distance_gate=DistanceGate()
  s=dict(distance_cm=39.,received_s=19.,error=None);m.physical_distance=NS(latest=lambda:dict(s))
  return m,b,s
 def test_actual_stale_startup_uses_existing_wait_then_fresh_recovery(self):
  from bio_inspire.runtime.distance_behavior import poll_distance
  m,b,s=self.motor();poll_startup_distance(poll_distance,m,20.,False)
  self.assertEqual(m.controller.state,'WAIT_TOF');self.assertTrue(m.distance_resume_startup)
  self.assertFalse(m.presentation_startup_tof_recovery)
  s.update(received_s=20.1);m.now=lambda:20.1
  poll_startup_distance(poll_distance,m,20.1,False)
  self.assertEqual(m.controller.state,'READY');self.assertFalse(m.distance_gate.near)
  self.assertEqual(m.behavior_trial,'distance_wait')
 def test_fresh_near_does_not_clear_wait_or_start_pilot(self):
  from bio_inspire.runtime.distance_behavior import poll_distance
  m,b,s=self.motor();poll_startup_distance(poll_distance,m,20.,False)
  s.update(distance_cm=15.,received_s=20.1);m.now=lambda:20.1
  poll_startup_distance(poll_distance,m,20.1,False)
  self.assertTrue(m.distance_gate.near);self.assertFalse(m.lab07_start_gate.started)
 def test_production_profile_keeps_original_startup_fault(self):
  from bio_inspire.runtime.distance_behavior import poll_distance
  m,b,s=self.motor();m.lab07_pair_id='normal_motion_P1'
  poll_startup_distance(poll_distance,m,20.,False)
  self.assertEqual(m.controller.state,'FAULT')
 def test_running_measurement_does_not_enable_startup_recovery(self):
  m,b,s=self.motor();m.normal_measurement.state='running';seen=[]
  poll_startup_distance(lambda m,now,dispatch:seen.append(m.presentation_startup_tof_recovery),m,20.,False)
  self.assertEqual(seen,[False])
 def test_stop_and_failed_hold_never_recover(self):
  from bio_inspire.runtime.distance_behavior import poll_distance
  for mode in ('stop','failed_hold'):
   m,b,s=self.motor()
   if mode=='stop':m.operator_stopped=True
   else:m._hold=lambda *a,**kw:setattr(m.controller,'state','FAULT')
   poll_startup_distance(poll_distance,m,20.,False)
   b.calls.clear();s.update(received_s=20.1);m.now=lambda:20.1
   poll_startup_distance(poll_distance,m,20.1,False)
   self.assertEqual(b.calls,[])
   self.assertNotEqual(m.controller.state,'READY')
 def test_flag_restored_even_if_original_raises(self):
  m,b,s=self.motor()
  def fail(*a,**kw):raise RuntimeError('transport')
  with self.assertRaises(RuntimeError):poll_startup_distance(fail,m,20.,False)
  self.assertFalse(m.presentation_startup_tof_recovery)

if __name__=='__main__':unittest.main()

class RunningRecoveryTests(Tests):
 def call_service(self,m,p,now):
  from shared.experiments.resistance_id1_20261109.pilot import service_measurement
  from unittest.mock import Mock
  original=Mock();sessions=NS(get=lambda owner:p)
  service_measurement(original,sessions,m.normal_measurement,m,now)
  return original
 def setup_running(self):
  from shared.experiments.resistance_id1_20261109.pilot import Pilot
  m,b,s=self.motor();m.controller.state='READY';m.behavior_trial='normal'
  m.normal_measurement=NS(state='running',last_callback=None)
  m.lab07_start_gate.started=True
  snapshot=b.snapshot
  def stamped_snapshot():return [dict(r,sampled_monotonic_s=m.now()) for r in snapshot()]
  b.snapshot=stamped_snapshot;m.controller.tick(20.)
  return m,b,s,Pilot()
 def test_stale_running_tof_pauses_without_aborting_and_recovers_only_with_fresh_clear(self):
  m,b,s,p=self.setup_running();original=self.call_service(m,p,20.)
  self.assertEqual(m.controller.state,'WAIT_TOF');self.assertEqual(m.normal_measurement.state,'running')
  self.assertTrue(p.safety_wait);original.assert_not_called()
  # A completed but ambiguous frame never authorizes R2 motion restart.
  s.update(distance_cm=None,measurement_state='unreliable',range_status_raw=5,received_s=20.1)
  m.now=lambda:20.1;self.call_service(m,p,20.1);self.assertTrue(p.safety_wait)
  s.update(distance_cm=39.,measurement_state='range',range_status_raw=9,received_s=20.2)
  m.now=lambda:20.2;self.call_service(m,p,20.2)
  self.assertEqual(m.controller.state,'READY');self.assertEqual(m.behavior_trial,'normal')
  self.assertFalse(p.safety_wait);self.assertEqual(m.normal_measurement.state,'running')
 def test_near_holds_and_does_not_recover_from_near_frame(self):
  m,b,s,p=self.setup_running();s.update(distance_cm=15.,received_s=20.)
  self.call_service(m,p,20.);self.assertTrue(p.safety_wait);self.assertEqual(m.controller.state,'WAIT_TOF')
  s['received_s']=20.1;m.now=lambda:20.1;self.call_service(m,p,20.1)
  self.assertTrue(p.safety_wait);self.assertEqual(m.controller.state,'WAIT_TOF')
 def test_operator_stop_and_hardware_fault_never_auto_resume(self):
  for flag in ('stop','fault'):
   m,b,s,p=self.setup_running();self.call_service(m,p,20.)
   if flag=='stop':m.operator_stopped=True
   else:m.controller.state='FAULT'
   s.update(distance_cm=39.,received_s=20.2);m.now=lambda:20.2
   original=self.call_service(m,p,20.2)
   original.assert_called_once();self.assertTrue(p.safety_wait)
 def test_production_service_is_unmodified(self):
  m,b,s,p=self.setup_running();m.lab07_pair_id='normal_motion_P1'
  self.call_service(m,p,20.).assert_called_once()

 def test_record_hook_does_not_turn_safe_wait_into_research_abort(self):
  from shared.experiments.resistance_id1_20261109.pilot import record_measurement
  from bio_inspire.runtime.normal_measurement import NormalMeasurement
  from unittest.mock import Mock
  m,b,s,p=self.setup_running();self.call_service(m,p,20.)
  measurement=NormalMeasurement.__new__(NormalMeasurement)
  measurement.saved=False;measurement.state='running';measurement.abort=Mock()
  record_measurement(NormalMeasurement.record,NS(get=lambda owner:p),measurement,m,20.)
  measurement.abort.assert_not_called()
 def test_record_hook_keeps_real_fault_and_operator_stop(self):
  from shared.experiments.resistance_id1_20261109.pilot import record_measurement
  from unittest.mock import Mock
  for flag in ('stop','fault','other_profile'):
   m,b,s,p=self.setup_running();p.safety_wait=True
   if flag=='stop':m.operator_stopped=True
   elif flag=='fault':m.controller.state='FAULT'
   else:m.lab07_pair_id='normal_motion_P1'
   original=Mock();record_measurement(original,NS(get=lambda owner:p),m.normal_measurement,m,20.)
   original.assert_called_once()

 def test_real_disk_recorder_quality_hold_is_not_io_failure_even_after_recovery(self):
  import tempfile
  from bio_inspire.runtime.session_recording import SessionRecorder
  from bio_inspire.runtime.normal_measurement import NormalMeasurement
  from shared.experiments.resistance_id1_20261109.pilot import record_measurement
  from unittest.mock import Mock
  m,b,s,p=self.setup_running()
  with tempfile.TemporaryDirectory() as temp:
   recorder=SessionRecorder(temp,'C0',180);m.lab07_recorder=recorder
   try:
    self.call_service(m,p,20.)
    recorder.record(dict(time_s=20.,state=m.controller.state))
    self.assertTrue(recorder.invalid);self.assertIsNone(recorder.error);self.assertEqual(recorder.dropped,0)
    measurement=NormalMeasurement.__new__(NormalMeasurement)
    measurement.saved=False;measurement.state='running';measurement.streamed=True;measurement.abort=Mock()
    record_measurement(NormalMeasurement.record,NS(get=lambda owner:p),measurement,m,20.)
    s.update(distance_cm=39.,received_s=20.2);m.now=lambda:20.2;self.call_service(m,p,20.2)
    self.assertFalse(p.safety_wait)
    recorder.record(dict(time_s=20.2,state=m.controller.state))
    record_measurement(NormalMeasurement.record,NS(get=lambda owner:p),measurement,m,20.2)
    measurement.abort.assert_not_called()
   finally:recorder.close()
   self.assertEqual(recorder.written,recorder.accepted);self.assertIsNone(recorder.error)

 def test_full_45s_pipeline_real_controller_tof_and_disk_with_repeated_waits(self):
  import tempfile,json
  from pathlib import Path
  from unittest.mock import Mock
  from bio_inspire.runtime.normal_measurement import NormalMeasurement
  from bio_inspire.runtime.session_recording import SessionRecorder,record_owner
  from shared.experiments.resistance_id1_20261109.pilot import service_measurement,service_rhythm,record_measurement
  m,b,s,p=self.setup_running();c=m.controller;clock=[20.];m.now=lambda:clock[0]
  m.id1_tof_observe_only=getattr(self,'force_observe_only',False)
  m.fast_awake_trial=False;m.rhythm_driver=NS(rhythm=NS(advance=Mock(),status=Mock(return_value={})))
  measurement=NormalMeasurement.__new__(NormalMeasurement)
  measurement.state='running';measurement.saved=False;measurement.streamed=True;measurement.abort=Mock()
  measurement.replay=NS(started=20.);measurement.fixture_sha256='SIMULATION_ONLY';m.lab07_start_marker={}
  m.normal_measurement=measurement;sessions=NS(get=lambda owner:p);original_service=Mock();original_rhythm=Mock()
  snapshot=b.snapshot
  def feedback():
   rows=snapshot()
   for r in rows:
    sid=r['id'];r.update(sampled_monotonic_s=clock[0],target_speed_raw=600,acceleration_raw=3,
     goal_raw=b.reg[sid][42],internal_target_raw=b.reg[sid][42],current_raw=1,load_raw=16)
   return rows
  b.snapshot=feedback
  with tempfile.TemporaryDirectory() as temp:
   recorder=SessionRecorder(temp,'C0',180);m.lab07_recorder=recorder
   try:
    for n in range(1000):
     t=20.+n*.05;clock[0]=t;b.pos={i:b.reg[i][42] for i in range(1,6)};c.tick(t)
     s.update(distance_cm=39.,received_s=t,measurement_state='range',range_status_raw=9)
     if 24.<=t<25.2:s.update(received_s=23.8)
     elif 25.2<=t<25.8:s.update(distance_cm=None,measurement_state='unreliable',range_status_raw=5)
     elif 30.<=t<31.:s['distance_cm']=15.
     elif 31.<=t<32.:s['distance_cm']=24.
     service_measurement(original_service,sessions,measurement,m,t)
     before=len(b.calls);service_rhythm(original_rhythm,sessions,m)
     if p.safety_wait:self.assertEqual(len(b.calls),before,'No pilot writes while safety-held')
     from unittest.mock import patch
     with patch('time.clock_gettime',lambda unused:t,create=True),patch('time.CLOCK_BOOTTIME',7,create=True):
      record_owner(m,dict(time_s=t,state=c.state,behavior=m.behavior_trial,rows=c.last_rows))
     record_measurement(NormalMeasurement.record,sessions,measurement,m,t)
     self.assertNotEqual(c.state,'FAULT');measurement.abort.assert_not_called()
     # Let the real file writer drain; this tests file I/O, not queue overflow.
     if n%20==0:
      import time;time.sleep(.002)
     if p.complete:break
    self.assertTrue(p.complete,'Must complete the logical 45s run after both waits')
    self.assertEqual(sum(e['event']=='tof_safety_wait' for e in p.events),0 if m.id1_tof_observe_only else 2)
    self.assertEqual(sum(e['event']=='tof_fresh_clear' for e in p.events),0 if m.id1_tof_observe_only else 2)
    self.assertEqual(p.guard.state,'MONITORING');self.assertFalse(p.safety_wait)
   finally:recorder.close()
   summary=json.loads((Path(temp)/'summary.json').read_text())
   self.assertEqual(summary['accepted'],summary['written']);self.assertEqual(summary['dropped'],0)
   self.assertIsNone(summary['error']);self.assertEqual(summary['quality_hold_or_invalid_seen'],not m.id1_tof_observe_only)
 def test_real_io_and_input_health_failures_remain_fatal(self):
  from shared.experiments.resistance_id1_20261109.pilot import record_measurement
  from unittest.mock import Mock
  for name,value in [('error','disk full'),('dropped',1),('input_health_error','sampler failed')]:
   m,b,s,p=self.setup_running()
   m.lab07_recorder=NS(error=None,dropped=0,input_health_error=None,invalid=True,end_seen=False)
   setattr(m.lab07_recorder,name,value)
   with self.assertRaisesRegex(RuntimeError,'recording failure'):
    record_measurement(Mock(),NS(get=lambda owner:p),m.normal_measurement,m,20.)

class ObserveOnlyTests(RunningRecoveryTests):
 def test_near_and_stale_tof_are_logged_without_hold_in_explicit_r2_only_mode(self):
  from bio_inspire.runtime.distance_behavior import poll_distance
  from shared.experiments.resistance_id1_20261109.pilot import poll_startup_distance
  from unittest.mock import Mock
  for sample in (dict(distance_cm=10.,received_s=20.),dict(distance_cm=39.,received_s=19.)):
   m,b,s,p=self.setup_running();m.id1_tof_observe_only=True;s.update(sample)
   original_hold=m._hold;m._hold=Mock(wraps=original_hold)
   poll_startup_distance(poll_distance,m,20.,False)
   self.assertEqual(m.controller.state,'READY');self.assertFalse(m.distance_gate.near)
   m._hold.assert_not_called();self.assertEqual(m.distance_view['policy'],'telemetry_only_id1_trial')
 def test_running_service_does_not_pause_for_logged_tof_near_or_stale(self):
  from bio_inspire.runtime import distance_behavior
  from shared.experiments.resistance_id1_20261109.pilot import poll_startup_distance
  from unittest.mock import patch
  m,b,s,p=self.setup_running();m.id1_tof_observe_only=True;s.update(distance_cm=10.,received_s=19.)
  original=distance_behavior.poll_distance
  with patch.object(distance_behavior,'poll_distance',lambda m,now,dispatch=True:poll_startup_distance(original,m,now,dispatch)):
   self.call_service(m,p,20.)
  self.assertFalse(p.safety_wait);self.assertEqual(m.controller.state,'READY')
 def test_other_profile_does_not_inherit_observe_only_even_if_flag_is_set(self):
  from bio_inspire.runtime.distance_behavior import poll_distance
  from shared.experiments.resistance_id1_20261109.pilot import poll_startup_distance
  m,b,s,p=self.setup_running();m.id1_tof_observe_only=True;m.lab07_pair_id='presentation'
  poll_startup_distance(poll_distance,m,20.,False)
  self.assertEqual(m.controller.state,'WAIT_TOF')

 def test_telemetry_sensor_keeps_input_implementation_but_removes_startup_freshness_gate(self):
  from shared.experiments.resistance_id1_20261109.pilot import telemetry_distance_class
  from unittest.mock import Mock
  class Input:
   wait_first_sample=Mock(side_effect=RuntimeError('stale'))
   require_fresh=Mock(side_effect=RuntimeError('stale'))
   def latest(self):return {'error':'sensor unavailable'}
  view=telemetry_distance_class(Input)()
  view.wait_first_sample();view.require_fresh()
  self.assertEqual(view.latest(),{'error':'sensor unavailable'})
  Input.wait_first_sample.assert_not_called();Input.require_fresh.assert_not_called()

 def test_full_pipeline_observe_only_finishes_despite_near_stale_and_ambiguous_tof(self):
  self.force_observe_only=True
  RunningRecoveryTests.test_full_45s_pipeline_real_controller_tof_and_disk_with_repeated_waits(self)
