import unittest,threading
from types import SimpleNamespace as NS
from unittest.mock import Mock
try:
 from shared.experiments.resistance_id1_20261109.pilot import Pilot,handle_key
except ImportError:Pilot=handle_key=None

class Bus:
 def __init__(self):self.goals={1:2019};self.writes=[];self.holds=[];self.windows={1:(1678,2360)}
 def write(self,sid,addr,data):
  if sid!=1 or addr!=42:raise AssertionError('Only ID1 position may change')
  q=int.from_bytes(data,'little');self.goals[sid]=q;self.writes.append(q)
 def hold_actual(self,sid):
  self.holds.append(sid);self.goals[sid]=self.actual
 def read(self,sid,addr,n):
  if (sid,addr,n)!=(1,42,2):raise AssertionError('Unexpected extra read')
  return self.goals[1].to_bytes(2,'little')

class Tests(unittest.TestCase):
 def test_pilot_exists(self):self.assertIsNotNone(Pilot,'R2 pilot not implemented')
 def setUp(self):
  if Pilot is None and self._testMethodName!='test_pilot_exists':self.skipTest('Not implemented')
 def motor(self):
  b=Bus();b.actual=2019
  rows=[dict(id=i,sampled_monotonic_s=0.,mode=0,torque_raw=1,status_raw=0,position_raw=2019,goal_raw=2019,internal_target_raw=2019,current_raw=0,load_raw=0,target_speed_raw=600,acceleration_raw=3,speed_raw=0,moving_raw=0) for i in range(1,6)]
  c=NS(bus=b,last_rows=rows,state='READY',normal={2:2837,3:2746},yaw_window=(1678,2360),command_margin_ticks=13,last_goal=2019,pose_route=None)
  m=NS(lab07_pair_id='resistance_id1_R2_pilot',behavior_trial='normal',controller=c,operator_stopped=False,
   stopping=threading.Event(),urgent_stop=threading.Event(),distance_gate=NS(near=False),normal_measurement=NS(state='running'),finished=threading.Event())
  d=NS(rhythm=NS(advance=Mock(),modulation_status={}),mode=None,centers=None)
  return m,d,b
 def advance(self,p,m,d,b,t,blocked=False):
  r=m.controller.last_rows[0]
  q=r['position_raw'] if blocked else b.goals[1]
  for x in m.controller.last_rows:x['sampled_monotonic_s']=t
  r.update(position_raw=q,goal_raw=b.goals[1],internal_target_raw=b.goals[1],current_raw=4 if blocked else 1,load_raw=40 if blocked else 16)
  b.actual=q;p.step(d,m,t)
 def test_unobstructed_sweep_bounded_slow_no_parameter_writes(self):
  m,d,b=self.motor();p=Pilot()
  for k in range(921):self.advance(p,m,d,b,k*.05)
  self.assertTrue(p.complete);self.assertEqual(p.guard.state,'MONITORING')
  self.assertTrue(b.writes);self.assertGreater(max(b.writes),2019);self.assertLess(min(b.writes),2019)
  self.assertTrue(all(1985<=q<=2053 for q in b.writes))
  self.assertTrue(all(abs(a-b)<=2 for a,b in zip(b.writes,b.writes[1:])))
  self.assertEqual(b.holds,[1])
 def test_startup_acc1_restores_existing_yaw_config_once_and_waits_for_readback(self):
  m,d,b=self.motor();p=Pilot();r=m.controller.last_rows[0];r['acceleration_raw']=1
  m.controller.tracking_speed=600;m.controller.tracking_acceleration=3
  m.controller.configure_tracking=Mock()
  p.step(d,m,0.)
  m.controller.configure_tracking.assert_called_once_with(yaw=True,pitch=False)
  self.assertIsNone(p.started);self.assertEqual(b.writes,[])
  self.advance(p,m,d,b,.05);self.assertIsNone(p.started)
  m.controller.configure_tracking.assert_called_once()
  r['acceleration_raw']=3;self.advance(p,m,d,b,.1)
  self.assertEqual(p.started,.1)
 def test_startup_restore_rejects_unknown_acc_or_unsafe_feedback(self):
  for change in [dict(acceleration_raw=8),dict(acceleration_raw=1,status_raw=1),dict(acceleration_raw=1,sampled_monotonic_s=-1.),dict(acceleration_raw=1,moving_raw=1)]:
   m,d,b=self.motor();p=Pilot();m.controller.last_rows[0].update(change)
   m.controller.tracking_speed=600;m.controller.tracking_acceleration=3;m.controller.configure_tracking=Mock()
   with self.assertRaises(ValueError):p.step(d,m,0.)
   m.controller.configure_tracking.assert_not_called()
 def test_uart_configuration_delay_before_motion_is_not_active_control_gap(self):
  for delay in (.24,.4,.7):
   m,d,b=self.motor();p=Pilot();r=m.controller.last_rows[0];r['acceleration_raw']=1
   m.controller.tracking_speed=600;m.controller.tracking_acceleration=3;m.controller.configure_tracking=Mock()
   p.step(d,m,0.);self.assertEqual(b.writes,[])
   r['acceleration_raw']=3;self.advance(p,m,d,b,delay)
   self.assertEqual(p.started,delay)
   with self.assertRaises(ValueError):self.advance(p,m,d,b,delay+.25)
 def test_real_failed_startup_frames_wait_for_all_awake_readbacks_before_arming(self):
  # Exact timing/ACC transition from PID2566; these are measured timestamps.
  m,d,b=self.motor();p=Pilot();m.fast_awake_trial=True
  c=m.controller;c.tracking_speed=600;c.tracking_acceleration=3;c.configure_tracking=Mock()
  for r in c.last_rows:r.update(acceleration_raw=1,sampled_monotonic_s=3852.248058797)
  p.step(d,m,3852.360071289)
  for r in c.last_rows:r['sampled_monotonic_s']=3852.416056332
  c.last_rows[0]['acceleration_raw']=3
  p.step(d,m,3852.588082516)
  self.assertIsNone(p.started,'Do not arm against feedback taken before awake setup completed')
  self.assertEqual(b.writes,[])
  for r in c.last_rows:
   r.update(sampled_monotonic_s=3852.62806733,acceleration_raw={1:3,2:8,3:8,4:12,5:6}[r['id']])
  p.step(d,m,3852.70)
  self.assertIsNotNone(p.started);self.assertEqual(p.guard.state,'MONITORING')
  # A genuine active feedback gap still stops, with the unchanged 0.20s limit.
  for r in c.last_rows:r['sampled_monotonic_s']=3852.84
  with self.assertRaisesRegex(RuntimeError,'gapped'):p.step(d,m,3852.85)
 def test_real_awake_initializer_with_blocking_uart_then_full_45s_pilot(self):
  from bio_inspire.runtime.awake_motion import AwakeMotion
  m,d,b=self.motor();p=Pilot();m.fast_awake_trial=True
  c=m.controller;c.normal_tolerances={i:22 for i in range(1,6)}
  native={1:3,2:1,3:1,4:1,5:1};clock=[0.];setup=[]
  original_write=b.write;original_read=b.read
  def read(sid,address,count):
   clock[0]+=.008
   return bytes((native[sid],)) if address==41 else original_read(sid,address,count)
  def write(sid,address,data):
   clock[0]+=.030
   if address==41:native[sid]=data[0];setup.append((sid,data[0]))
   else:original_write(sid,address,data)
  b.read=read;b.write=write
  awake=AwakeMotion(m)
  for k in range(1000):
   for r in c.last_rows:
    clock[0]+=.008
    r.update(sampled_monotonic_s=clock[0],acceleration_raw=native[r['id']])
    if r['id']==1:r.update(position_raw=b.goals[1],goal_raw=b.goals[1],internal_target_raw=b.goals[1])
   b.actual=b.goals[1]
   awake.ensure(m,'normal')
   p.step(d,m,clock[0])
   if k==0:
    self.assertIsNone(p.started);self.assertEqual(b.writes,[])
   clock[0]+=.010
   if p.complete:break
  self.assertTrue(p.complete);self.assertEqual(p.guard.state,'MONITORING')
  self.assertEqual(setup,[(2,8),(3,8),(4,12),(5,6)])
  self.assertGreater(max(b.writes),2019);self.assertLess(min(b.writes),2019)
  self.assertEqual(b.holds,[1])
 def test_block_holds_once_and_does_not_retry_when_effort_falls(self):
  m,d,b=self.motor();p=Pilot()
  for k in range(81):self.advance(p,m,d,b,k*.05,blocked=True)
  self.assertEqual(p.guard.state,'RESISTANCE_PAUSE');self.assertEqual(b.holds,[1]);before=len(b.writes)
  for k in range(81,121):self.advance(p,m,d,b,k*.05,blocked=False)
  self.assertEqual(len(b.writes),before);self.assertEqual(b.holds,[1]);self.assertEqual(p.guard.state,'RESISTANCE_PAUSE')
 def test_explicit_resume_reseeds_from_actual_and_stop_cannot_resume(self):
  m,d,b=self.motor();p=Pilot()
  for k in range(81):self.advance(p,m,d,b,k*.05,blocked=True)
  p.resume_requested=True;self.advance(p,m,d,b,4.05)
  self.assertEqual(p.guard.state,'MONITORING');self.assertFalse(p.resume_requested)
  self.assertLessEqual(abs(b.goals[1]-b.actual),1)
  m.urgent_stop.set();p.resume_requested=True;before=len(b.writes)
  self.advance(p,m,d,b,4.1);self.assertEqual(len(b.writes),before)
 def test_stale_status_clock_and_bounds_refuse(self):
  for reason in ('stale','status','clock','bounds'):
   m,d,b=self.motor();p=Pilot()
   if reason=='bounds':m.controller.yaw_window=(2000,2030)
   elif reason=='stale':m.controller.last_rows[0]['sampled_monotonic_s']=-1.
   elif reason=='status':m.controller.last_rows[0]['status_raw']=1
   if reason=='clock':
    p.step(d,m,0.)
    with self.assertRaises(ValueError):p.step(d,m,1.)
   else:
    with self.assertRaises((ValueError,RuntimeError)):p.step(d,m,0.)
 def test_stop_near_and_aborted_no_position_writes(self):
  for kind in ('operator','near','fault','aborted'):
   m,d,b=self.motor();p=Pilot()
   if kind=='operator':m.operator_stopped=True
   elif kind=='near':m.distance_gate.near=True
   elif kind=='fault':m.controller.state='FAULT'
   else:m.normal_measurement.state='aborted'
   p.step(d,m,0.);self.assertEqual(b.writes,[])
 def test_completion_stops_growing_record_and_does_not_hold_repeatedly(self):
  m,d,b=self.motor();p=Pilot()
  for k in range(1001):self.advance(p,m,d,b,k*.05)
  count=len(p.samples)
  for k in range(1001,5001):self.advance(p,m,d,b,k*.05)
  self.assertEqual(len(p.samples),count);self.assertEqual(b.holds,[1])
 def test_hold_ack_failure_is_not_reported_as_successful_pause(self):
  m,d,b=self.motor();p=Pilot();b.read=lambda *args:(_ for _ in ()).throw(TimeoutError('readback unavailable'))
  with self.assertRaises(TimeoutError):
   for k in range(81):self.advance(p,m,d,b,k*.05,blocked=True)
  self.assertFalse(p.paused);self.assertFalse(any(e['event']=='hold_ack' for e in p.events))
 def test_key_override_only_r2_resistance_pause_and_other_keys_fallthrough(self):
  m,d,b=self.motor();p=Pilot();s=NS(attempts=[(m,p)]);original=Mock(return_value='original')
  handle_key(original,s,m,ord('r'));original.assert_not_called();self.assertFalse(p.resume_requested)
  p.guard.state='RESISTANCE_PAUSE';handle_key(original,s,m,ord('r'));self.assertTrue(p.resume_requested)
  handle_key(original,s,m,ord('h'));original.assert_called_once_with(m,ord('h'))
  m.lab07_pair_id='presentation';handle_key(original,s,m,ord('r'));self.assertEqual(original.call_count,2)

if __name__=='__main__':unittest.main()

class RhythmOwnerTests(unittest.TestCase):
 def test_r2_routes_directly_to_pilot_without_normal_gaze_setup(self):
  from shared.experiments.resistance_id1_20261109.pilot import service_rhythm
  m,d,b=Tests().motor();m.lock=threading.Lock();m.now=lambda:20.;m.rhythm_driver=d
  d.rhythm.status=Mock(return_value={})
  p=NS(safety_wait=False,step=Mock());original=Mock()
  service_rhythm(original,NS(get=lambda owner:p),m)
  original.assert_not_called();p.step.assert_called_once_with(d,m,20.)
  p.safety_wait=True;p.step.reset_mock();m.behavior_trial='distance_wait'
  service_rhythm(original,NS(get=lambda owner:p),m);p.step.assert_not_called()
 def test_other_profiles_keep_original_rhythm(self):
  from shared.experiments.resistance_id1_20261109.pilot import service_rhythm
  original=Mock();m=NS(lab07_pair_id='normal_motion_P1')
  service_rhythm(original,None,m);original.assert_called_once_with(m)

class ResistanceWithoutToFTests(Tests):
 def test_resistance_still_latches_in_observe_only_mode_and_effort_drop_does_not_resume(self):
  m,d,b=self.motor();m.id1_tof_observe_only=True;p=Pilot()
  for k in range(81):self.advance(p,m,d,b,k*.05,blocked=True)
  self.assertEqual(p.guard.state,'RESISTANCE_PAUSE');self.assertEqual(b.holds,[1])
  count=len(b.writes)
  for k in range(81,121):self.advance(p,m,d,b,k*.05,blocked=False)
  self.assertEqual(len(b.writes),count);self.assertEqual(p.guard.state,'RESISTANCE_PAUSE')

class PublicResumeTests(Tests):
 def test_ui_public_key_path_delivers_r_and_resumes_from_hold(self):
  from shared.experiments.resistance_id1_20261109.pilot import enqueue_pilot_key
  from bio_inspire.runtime.camera_motor import CameraMotor
  m,d,b=self.motor();m.lock=threading.Lock();m.keys=[];m.id1_tof_observe_only=True
  p=Pilot();sessions=NS(attempts=[(m,p)])
  for k in range(81):self.advance(p,m,d,b,k*.05,blocked=True)
  self.assertEqual(p.guard.state,'RESISTANCE_PAUSE')
  enqueue_pilot_key(CameraMotor.key,m,ord('r'));self.assertEqual(m.keys,[ord('r')])
  for key in m.keys:handle_key(Mock(),sessions,m,key)
  self.assertTrue(p.resume_requested)
  held=b.goals[1];self.advance(p,m,d,b,4.05,blocked=False)
  self.assertEqual(p.guard.state,'MONITORING');self.assertLessEqual(abs(b.goals[1]-held),1)
  for k in range(82,121):self.advance(p,m,d,b,k*.05,blocked=False)
  self.assertTrue(any(e['event']=='operator_resume' for e in p.events));self.assertNotEqual(b.goals[1],held)
 def test_waiting_for_r_does_not_consume_45s_motion_budget(self):
  m,d,b=self.motor();p=Pilot()
  for k in range(81):self.advance(p,m,d,b,k*.05,blocked=True)
  for k in range(81,1101):self.advance(p,m,d,b,k*.05,blocked=False)
  self.assertFalse(p.complete,'Waiting for clearance is not 45s of movement')
  p.resume_requested=True;self.advance(p,m,d,b,55.05)
  self.assertEqual(p.guard.state,'MONITORING')
 def test_wider_trial_uses_10deg_span_and_still_rejects_outside_original_window(self):
  m,d,b=self.motor();m.id1_resistance_half_span_ticks=114;p=Pilot();self.advance(p,m,d,b,0.)
  self.assertEqual((p.limits.low,p.limits.high),(1905,2133))
  m,d,b=self.motor();m.id1_resistance_half_span_ticks=114;m.controller.yaw_window=(1980,2060)
  with self.assertRaisesRegex(ValueError,'outside'):self.advance(Pilot(),m,d,b,0.)

 def test_public_r_never_overrides_urgent_stop_or_other_profile_filter(self):
  from shared.experiments.resistance_id1_20261109.pilot import enqueue_pilot_key
  from bio_inspire.runtime.camera_motor import CameraMotor
  m,d,b=self.motor();m.lock=threading.Lock();m.keys=[]
  enqueue_pilot_key(CameraMotor.key,m,ord('R'));self.assertEqual(m.keys,[ord('R')])
  enqueue_pilot_key(CameraMotor.key,m,ord('h'));self.assertEqual(m.keys,[ord('h')])
  enqueue_pilot_key(CameraMotor.key,m,ord('r'));self.assertEqual(m.keys,[ord('h')])
  m.urgent_stop.clear();m.keys=[];m.lab07_pair_id='presentation'
  enqueue_pilot_key(CameraMotor.key,m,ord('r'));self.assertEqual(m.keys,[])
