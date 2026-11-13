import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from . import offline_harness as harness
from shared.experiments.central_safety_controller_20261110.scenarios import contact_in_state
from .integration import hooks,consent
from .test_native_stop import Bus
from .offline_plant import Plant,Port

class TrialPort(Port):
 def write(self,data):
  p=bytes(data)
  if p[4]!=131 or p[5:7]not in(bytes((40,1)),bytes((40,8))):return super().write(data)
  if p[:3]!=b'\xff\xff\xfe'or len(p)!=p[3]+4 or sum(p[2:])&255!=255:raise AssertionError('Bad stop frame')
  self.plant.clock.advance(.00064);self.plant.frames.append(dict(time_s=self.plant.clock(),packet=list(p),instruction=131))
  width=p[6]
  for j in range(7,len(p)-1,width+1):self.plant.apply(p[j],40,p[j+1:j+1+width])
  if self.plant.on_packet:self.plant.on_packet(131)
  return len(p)

class TrialPlant(Plant):
 def __init__(self,*args):
  super().__init__(*args);self.held_ids=set()
  for a in self.ram.values():a.extend(b'\0'*20);a[85]=50
 def serial(self,*a,**kw):return TrialPort(self)
 def apply(self,i,a,data):
  if a==40 and(data==b'\2'or len(data)==8):
   if len(data)==8:
    # A failed preflight/return uses the freshly proven source ACC rather
    # than a guessed brake preset. Both preserve the same accepted profiles.
    allowed_acc={self.ram[i][41],{1:0,3:50,4:48}.get(i,self.ram[i][41])}
    if data[0]!=1 or data[1]not in allowed_acc or data[4:]!=self.ram[i][44:48]:raise AssertionError('Invalid new active frame')
    self.held_ids.add(i);self.ram[i][40:48]=data;self.ram[i][67:69]=data[2:4]
   else:self.ram[i][40]=2;self.ram[i][67:69]=self.ram[i][56:58]
   self.mutations.append(dict(time_s=self.clock(),id=i,address=a,data_hex=data.hex()));return
  if a==42:self.held_ids.discard(i)
  return super().apply(i,a,data)
 def refresh(self,i):
  if self.ram[i][40]==2:self.ram[i][67:69]=self.ram[i][56:58];return
  contact=i in self.contact
  if i in self.held_ids:self.contact.discard(i)
  try:super().refresh(i)
  finally:
   if contact:self.contact.add(i)

def run(scenario,seconds=25,contact_ids=(1,2,3,4,5)):
 with tempfile.TemporaryDirectory()as d,patch.object(harness,'Plant',TrialPlant),patch.object(harness,'hooks',lambda *a,**kw:hooks(*a,**{**kw,'trial_consent':consent(contact_ids)})):
  return harness.run(Path(d),scenario,seconds=seconds,enabled_ids=range(1,6))

class Tests(unittest.TestCase):
 def test_contact_return_token_is_revoked_before_dispatch_not_during_motion(self):
  from .integration import adapter_class,consent
  from types import SimpleNamespace as NS
  cls=adapter_class(consent(),effort_stop=True);a=object.__new__(cls)
  a.core=NS(phase='WAIT_CLEARANCE',serial=1,hold_epoch=1);a.clear_token=(1,1);a.id1_contact_released=lambda:False
  self.assertFalse(a.manual_clearance(None));self.assertIsNone(a.clear_token)
  a.core.phase='RETURNING';a.clear_token=(1,1)
  self.assertTrue(a.manual_clearance(None))
 def test_static_normal_arrival_cannot_bypass_unreleased_id1_contact(self):
  def after(w):
   a=w.motor.bus.central_feedback.brake_capture
   if not hasattr(w,'late_marker'):
    w.late_marker=True;a.normal_complete=lambda:False
   if a.core.phase=='WAIT_CLEARANCE'and not hasattr(w,'first_r')and a.sensor_state()=='clear':
    w.first_r=True;w.motor.key(ord('r'))
   route=getattr(w.motor.controller,'pose_route',None)
   if a.core.phase=='RETURNING'and getattr(route,'phase',None)=='complete':
    w.distance.kind='unreliable';a.id1_contact_released=lambda:False
  r,w=run(contact_in_state('happy',1,after),seconds=15)
  self.assertEqual(r['phase'],'WAIT_CLEARANCE',r['error'])
  self.assertNotIn('BUTTON_RESTART_ARMED',[e['event']for e in r['events']])
 def test_worker_retirement_keeps_loaded_head_goal_after_five_releases(self):
  from .restart import take_restart
  class LoadedHead(TrialPlant):
   def refresh(self,i):
    super().refresh(i)
    if i==5 and self.ram[i][40]==1:
     self.ram[i][56:58]=(int.from_bytes(self.ram[i][42:44],'little')+15).to_bytes(2,'little')
  def after(w):
   a=w.motor.bus.central_feedback.brake_capture
   if a.core.phase=='WAIT_CLEARANCE'and a.sensor_state()=='clear':w.motor.key(ord('r'))
   if a.core.phase=='NORMAL_PARKED':
    if not hasattr(w,'gate_started'):w.gate_started=w.clock()
    t=w.clock()-w.gate_started
    w.inputs['button'].pressed=any(s<t<s+.17 for s in(.2,.6,1.,1.4,1.8))
    if take_restart(w.motor,255):
     a.retiring_parked_owner=True;w.claimed=True;w.motor.stopping.set()
  contact=contact_in_state('happy',1,after)
  def scenario(w):
   if hasattr(w,'park_time'):w.park_time=w.clock()
   contact(w)
  with patch(__name__+'.TrialPlant',LoadedHead):r,w=run(scenario,seconds=20)
  self.assertTrue(getattr(w,'claimed',False),r['error']);self.assertTrue(r['cleanup_confirmed'])
  proof=[e for e in r['events']if e['event']=='PARKED_OWNER_RETIRED_WITHOUT_REBASE']
  self.assertEqual(len(proof),1);self.assertEqual(r['final_goals'][5],r['normal'][5])
  self.assertEqual(proof[0]['proof']['5']['position_raw']-proof[0]['proof']['5']['goal_raw'],15)
 def test_retirement_preserves_verified_normal_goals_without_rebasing_sag(self):
  from .restart import verify_parked_retirement
  from types import SimpleNamespace as NS
  rows=[dict(id=i,mode=0,torque_raw=1,status_raw=0,speed_raw=0,moving_raw=0,
    goal_raw=2000,internal_target_raw=2000,position_raw=2015 if i==5 else 2000)for i in range(1,6)]
  a=NS(restart_claimed=True,core=NS(phase='NORMAL_PARKED',error=None,pending=None),
    restart_hold_goals={i:2000 for i in range(1,6)},m=NS(controller=NS(normal={i:2000 for i in range(1,6)},normal_tolerances={i:22 for i in range(1,6)})))
  proof=verify_parked_retirement(a,rows)
  self.assertEqual(proof['5']['goal_raw'],2000);self.assertEqual(proof['5']['position_raw'],2015)
  for key,value in (('moving_raw',1),('status_raw',1),('torque_raw',2),('goal_raw',2015),('internal_target_raw',1990)):
   changed=[dict(r)for r in rows];changed[-1][key]=value
   with self.subTest(key=key),self.assertRaises(RuntimeError):verify_parked_retirement(a,changed)
 def test_manual_view_can_use_mode2_dark_without_opening_devices(self):
  from .launch import runtime_surfaces
  from .auto_recovery import DarkLed
  import physical_distance,led_ring,json,time
  distance=physical_distance.PhysicalDistance;led=led_ring.LedRing
  with tempfile.TemporaryDirectory()as out,runtime_surfaces(harness.ROOT,Path(out),json.loads(harness.CONFIG.read_text()),time.monotonic,dark=True,mode2=True)as sessions:
   self.assertEqual(sessions,[]);self.assertIs(led_ring.LedRing,DarkLed)
   self.assertIsNot(physical_distance.PhysicalDistance,distance)
  self.assertIs(physical_distance.PhysicalDistance,distance);self.assertIs(led_ring.LedRing,led)
 def test_dark_output_and_sensor_mode_trial_do_not_change_ordinary_sources(self):
  from .auto_recovery import DarkLed,mode2_source
  from physical_distance import PhysicalDistance
  from types import SimpleNamespace as NS
  ring=DarkLed();ring.show_color((255,255,255),.03);ring.close()
  modes=[];deinit=[]
  class Sensor:
   @property
   def distance_mode(self):return modes[-1]
   @distance_mode.setter
   def distance_mode(self,value):modes.append(value)
   def start_ranging(self):pass
   def stop_ranging(self):pass
  original_run=PhysicalDistance._run;instances=[];trial=mode2_source(PhysicalDistance,instances)
  with patch('threading.Thread.start',lambda self:None):
   source=trial(factory=lambda:(Sensor(),NS(deinit=lambda:deinit.append(True))))
  source.stop.set();source._run()
  self.assertEqual(modes,[2,1]);self.assertTrue(source.mode_trial_restored);self.assertEqual(deinit,[True])
  self.assertIs(PhysicalDistance._run,original_run);self.assertEqual(instances,[source])
 def test_automatic_inputs_cancel_before_startup_and_require_continuous_happy(self):
  from .startup import build_source_factory
  from .offline_plant import Clock,Distance
  from .auto_recovery import RecoverySequence
  from types import SimpleNamespace as NS
  import threading
  cancelled=[True];created=[]
  def factory():created.append(True);return Distance(Clock())
  wrapped=build_source_factory(factory,simulation=True,external_cancelled=lambda:cancelled[0])
  with self.assertRaises(RuntimeError):wrapped()
  self.assertEqual(created,[])
  cancelled[0]=False;source=wrapped();cancelled[0]=True
  with self.assertRaisesRegex(RuntimeError,'cancelled'):source.require_fresh()
  keys=[];view=dict(behavior='happy',trial_safety=dict(phase='PLAY',led=dict(requested_brightness=.05)))
  m=NS(snapshot_view=lambda:view,stopping=threading.Event(),urgent_stop=threading.Event(),fault_message=lambda:None,led_ring=object(),key=keys.append)
  sequence=RecoverySequence(0);sequence.change('HAPPY',0);sequence.tick(m,.1)
  view['behavior']='afraid';sequence.tick(m,1.)
  view['behavior']='happy';sequence.tick(m,1.5);sequence.tick(m,2.)
  self.assertEqual(keys,[])
  sequence.tick(m,3.1);self.assertEqual(keys,[ord('v')])
 def test_automatic_sequence_drives_real_worker_to_checked_five_button_handoff(self):
  from .auto_recovery import RecoverySequence
  def scenario(w):
   if not hasattr(w,'sequence'):w.sequence=RecoverySequence(w.clock())
   action=w.sequence.tick(w.motor,w.clock())
   for name in('touch','button'):w.inputs[name].pressed=action[name]
   if action['restart']:w.restart_requested=True;w.motor.stopping.set()
  r,w=run(scenario,seconds=25,contact_ids=(1,2,4))
  self.assertEqual(w.motor.bus.central_feedback.brake_capture.enabled_ids,{1,2,4})
  self.assertTrue(w.restart_requested,r['error']);self.assertEqual(w.sequence.phase,'RESUMED')
  self.assertEqual(sum(e['event']=='V_REQUEST'for e in w.sequence.events),1)
  self.assertTrue(any(e['event']=='NORMAL_PARK_LED_OFF'for e in w.sequence.events))
  self.assertTrue(any(e['event']=='FIVE_RELEASES_CONFIRMED'for e in w.sequence.events))
  self.assertTrue(r['cleanup_confirmed']);self.assertIsNone(r['error'])
 def test_sensor_paused_return_can_park_only_when_normal_arrival_is_proven(self):
  for arrived in(True,False):
   def after(w):
    a=w.motor.bus.central_feedback.brake_capture
    if not hasattr(w,'late_marker'):
     w.late_marker=True;a.normal_complete=lambda:False # delayed route-complete acknowledgment
    if a.core.phase=='WAIT_CLEARANCE'and not hasattr(w,'first_r')and a.sensor_state()=='clear':
     w.first_r=True;w.motor.key(ord('r'))
    route=getattr(w.motor.controller,'pose_route',None)
    if a.core.phase=='RETURNING'and getattr(route,'phase',None)=='complete'and not hasattr(w,'optical_dip'):
     w.optical_dip=True;w.distance.kind='unreliable'
     if not arrived:
      raw=w.plant.ram[1];q=w.motor.controller.normal[1]+50
      raw[42:44]=q.to_bytes(2,'little');raw[56:58]=q.to_bytes(2,'little');raw[67:69]=q.to_bytes(2,'little')
   with self.subTest(arrived=arrived):
    r,w=run(contact_in_state('happy',3,after),seconds=15)
    self.assertTrue(w.optical_dip)
    self.assertEqual(sum(e['event']=='OPERATOR_CLEARANCE_R'for e in r['events']),1)
    if arrived:
     self.assertEqual(r['phase'],'NORMAL_PARKED',r['error'])
     self.assertTrue(any(e['event']=='NORMAL_ARRIVAL_VERIFIED_AFTER_SENSOR_PAUSE'for e in r['events']))
    else:
     self.assertEqual(r['phase'],'WAIT_CLEARANCE',r['error'])
     self.assertNotIn('BUTTON_RESTART_ARMED',[e['event']for e in r['events']])
 def test_tof_recovery_does_not_override_near_or_operator_stop(self):
  for mode in('near','stop'):
   def scenario(w):
    t=w.clock()-w.start;w.distance.kind='stale'if t<.18 else'range'
    w.distance.cm=15. if mode=='near'else 50.
    if mode=='stop'and t>.1 and not hasattr(w,'stopped_by_user'):
     w.stopped_by_user=True;w.motor.key(ord('h'))
    if t>2 and not hasattr(w,'recovery_checked'):
     w.recovery_checked=True;w.state_after=w.motor.controller.state;w.behavior_after=w.motor.behavior_trial;w.operator_after=w.motor.operator_stopped
   with self.subTest(mode=mode):
    r,w=run(scenario,seconds=3)
    if mode=='near':self.assertIn(w.behavior_after,('afraid','afraid_transition'),r['error'])
    else:self.assertTrue(w.operator_after);self.assertEqual(w.state_after,'STOPPED')
 def test_startup_tof_pause_resumes_normal_and_led_without_any_button(self):
  def scenario(w):
   t=w.clock()-w.start
   w.distance.kind='stale'if t<.18 else'range'
   if t>2 and not hasattr(w,'observed_after_recovery'):
    w.observed_after_recovery=True;w.recovered_behavior=w.motor.behavior_trial
    w.recovered_led=dict(getattr(w.motor,'presentation_led_output',{}))
  r,w=run(scenario,seconds=3)
  self.assertTrue(w.observed_after_recovery)
  self.assertIn(w.recovered_behavior,('normal','normal_transition'),r['error'])
  self.assertEqual(w.recovered_led.get('state'),'normal')
  self.assertEqual(r['phase'],'PLAY');self.assertIsNone(r['error'])
 def test_normal_park_turns_led_off_before_button_gate(self):
  def after(w):
   a=w.motor.bus.central_feedback.brake_capture
   if a.core.phase=='WAIT_CLEARANCE'and a.sensor_state()=='clear':w.motor.key(ord('r'))
   if a.core.phase=='NORMAL_PARKED'and not hasattr(w,'park_led_off'):
    w.park_led_off=w.motor.led_ring is None;w.park_led=dict(getattr(w.motor,'presentation_led_output',{}))
  r,w=run(contact_in_state('happy',3,after),seconds=15)
  self.assertEqual(r['phase'],'NORMAL_PARKED',r['error'])
  self.assertTrue(w.park_led_off);self.assertEqual(w.park_led['requested_brightness'],0.)
 def test_waiting_safety_screen_names_the_actual_r_gate(self):
  from .launch import view
  from types import SimpleNamespace as NS
  import play_view
  original=play_view.status_text
  with view():
   motor=NS(snapshot_view=lambda:dict(trial_safety=dict(phase='WAIT_CLEARANCE')))
   self.assertIn('WAIT_CLEARANCE',play_view.status_text(motor));self.assertIn('then R',play_view.status_text(motor))
   self.assertNotIn('press Start',play_view.status_text(motor))
  self.assertIs(play_view.status_text,original)
 def test_accepted_return_write_failure_uses_fresh_stop_proof_then_latches(self):
  def after(w):
   a=w.motor.bus.central_feedback.brake_capture
   if not hasattr(w,'return_fault_installed'):
    w.return_fault_installed=True
    def packet(op):
     p=w.plant.frames[-1]['packet']
     if a.return_dispatch and not hasattr(w,'return_fault')and p[4]in(3,131)and p[5]==42:
      w.return_fault=True;w.old_writer=a.stop_writer;w.plant.contact.add(3)
      raise OSError('accepted Normal command but return readback failed')
    w.plant.on_packet=packet
   if a.core.phase=='WAIT_CLEARANCE'and a.sensor_state()=='clear':w.motor.key(ord('r'))
  r,w=run(contact_in_state('happy',3,after),seconds=9)
  self.assertTrue(w.return_fault);a=w.motor.bus.central_feedback.brake_capture
  self.assertEqual(r['phase'],'LATCHED');self.assertIsNot(a.stop_writer,w.old_writer)
  self.assertTrue(w.old_writer.restored);self.assertEqual(len(a.writers),2)
  self.assertTrue(a.stop_writer.audit['failed_before_commit']);self.assertTrue(a.stop_writer.audit['recovery_verified'],a.stop_writer.audit)
  self.assertTrue(any(x['event']=='RETURN_FAILURE_FRESH_HOLD'for x in r['events']))
  self.assertTrue(all(raw[40]==1 for raw in w.plant.ram.values()))
 def test_later_moving_feedback_outside_pending_envelope_latches_immediately(self):
  for fault in('reference','travel'):
   def after(w):
    if hasattr(w,'guard_installed'):return
    w.guard_installed=True;apply=w.plant.apply
    def delayed(i,address,data):
     apply(i,address,data)
     if i==3 and address==40 and len(data)==8:w.break_at=w.clock()+.12;w.reset_q=int.from_bytes(w.plant.ram[3][56:58],'little')
    def later(i,address,n):
     if i!=3 or not hasattr(w,'break_at'):return
     raw=w.plant.ram[3];goal=int.from_bytes(raw[42:44],'little')
     raw[67:69]=(goal+3).to_bytes(2,'little')
     if w.clock()>=w.break_at:
      if not hasattr(w,'violation_at'):w.violation_at=w.clock()
      if fault=='reference':raw[67:69]=(goal+30).to_bytes(2,'little')
      else:raw[56:58]=(w.reset_q+17).to_bytes(2,'little')
      raw[58:60]=(50).to_bytes(2,'little');raw[66]=1
    w.plant.apply=delayed;w.plant.on_readback=later
   with self.subTest(fault=fault):
    r,w=run(contact_in_state('happy',3,after),seconds=6)
    events=[e for e in r['events']if e['event']=='STOP_ENVELOPE_FAULT']
    self.assertTrue(events,r['error']);self.assertLessEqual(events[0]['time_s']-w.violation_at,.01)
    self.assertEqual(r['phase'],'LATCHED');self.assertIn(3,w.motor.bus.unsafe_damping_axes)
    self.assertNotIn('NORMAL_RETURN_STARTED',[e['event']for e in r['events']])
 def test_pending_id3_reference_waits_without_rewriting_then_allows_r(self):
  for converges in (True,False):
   def after(w):
    a=w.motor.bus.central_feedback.brake_capture
    if not hasattr(w,'lag_installed'):
     w.lag_installed=True;apply=w.plant.apply
     def lagged(i,address,data):
      apply(i,address,data)
      if i==3 and address==40 and len(data)==8:w.lag_until=w.clock()+.4
     def readback(i,address,n):
      if i==3 and hasattr(w,'lag_until')and(not converges or w.clock()<w.lag_until):
       raw=w.plant.ram[3];raw[67:69]=(int.from_bytes(raw[42:44],'little')+3).to_bytes(2,'little')
     w.plant.apply=lagged;w.plant.on_readback=readback
    if a.core.phase=='WAIT_CLEARANCE'and a.sensor_state()=='clear':
     self.assertTrue(converges);self.assertGreaterEqual(w.clock(),w.lag_until);w.motor.key(ord('r'))
   with self.subTest(converges=converges):
    r,w=run(contact_in_state('happy',3,after),seconds=20 if converges else 12)
    a=w.motor.bus.central_feedback.brake_capture
    self.assertIn('3',a.writers[0].audit['native_reference_pending'])
    blocks=[x for x in r['mutations']if x['id']==3 and x['address']==40 and len(bytes.fromhex(x['data_hex']))==8]
    self.assertEqual(len(blocks),1)
    if converges:
     self.assertEqual(r['phase'],'NORMAL_PARKED',r['error']);self.assertEqual(r['reset']['h'],0.)
    else:
     self.assertEqual(r['phase'],'LATCHED');self.assertIn('Stop not confirmed',r['error'])
     self.assertNotIn('NORMAL_RETURN_STARTED',[e['event']for e in r['events']])
 def test_startup_waits_for_a_new_real_tof_frame_without_restarting_constructor(self):
  from .offline_plant import Distance
  class StaleDuringStart(Distance):
   def latest(self):
    if hasattr(self,'recover_at')and self.clock()>=self.recover_at:self.kind='range'
    return super().latest()
   def require_fresh(self):
    if not hasattr(self,'recover_at'):self.kind='stale';self.recover_at=self.clock()+.08
    self.latest();return super().require_fresh()
  with patch.object(harness,'Distance',StaleDuringStart):r,w=run(None,seconds=4)
  self.assertIsNone(r['error']);self.assertEqual(r['phase'],'PLAY');self.assertTrue(r['cleanup_confirmed'])
  self.assertGreater(w.distance.startup_freshness.wait_count,0)
 def test_startup_freshness_never_uses_stale_or_hardware_fault_as_ready(self):
  from .startup import StartupFreshness
  from .offline_plant import Clock,Distance
  clock=Clock();source=Distance(clock);source.kind='stale'
  guard=StartupFreshness(source,source.require_fresh,clock.advance,lambda:False)
  with self.assertRaisesRegex(RuntimeError,'fresh ToF'):guard.check()
  self.assertLessEqual(guard.spent_s,.501)
  source.kind='hardware_error';prior=clock()
  with self.assertRaisesRegex(RuntimeError,'I2C'):guard.check()
  self.assertEqual(prior,clock())
 def test_startup_wait_is_first_check_only_and_cancellation_interrupts_wait(self):
  from .startup import StartupFreshness
  from .offline_plant import Clock,Distance
  clock=Clock();source=Distance(clock);source.kind='stale';latest=source.latest;ready_at=[clock()+.3]
  def sample():
   source.kind='range'if clock()>=ready_at[0]else'stale';return latest()
  source.latest=sample
  def original():
   source.latest();return Distance.require_fresh(source)
  guard=StartupFreshness(source,original,clock.advance,lambda:False);guard.check()
  spent=guard.spent_s;ready_at[0]=clock()+.3
  with self.assertRaisesRegex(RuntimeError,'ToF unavailable'):guard.check()
  self.assertEqual(guard.spent_s,spent)
  cancelled=[False]
  def wait(dt):clock.advance(dt);cancelled[0]=True
  guard=StartupFreshness(source,original,wait,lambda:cancelled[0])
  with self.assertRaisesRegex(RuntimeError,'cancelled'):guard.check()
  self.assertEqual(guard.wait_count,1)
 def test_stale_frame_after_first_normal_dispatch_aborts_without_waiting(self):
  from .offline_plant import Distance
  sources=[];plants=[]
  class CapturedPlant(TrialPlant):
   def __init__(self,*args):super().__init__(*args);plants.append(self)
  class LaterStale(Distance):
   def __init__(self,*args):super().__init__(*args);self.checks=0;sources.append(self)
   def require_fresh(self):
    self.checks+=1
    n=sum(x['address']==42 for x in plants[-1].mutations)
    if self.checks==1:self.goals_before=n
    if self.checks==2:self.goals_after=n;self.kind='stale'
    return super().require_fresh()
  with patch(__name__+'.TrialPlant',CapturedPlant),patch.object(harness,'Distance',LaterStale):
   with self.assertRaisesRegex(RuntimeError,'ToF unavailable'):run(None,seconds=4)
  self.assertGreater(sources[0].goals_after,sources[0].goals_before)
  self.assertEqual(sources[0].startup_freshness.wait_count,0)
  self.assertTrue(plants[0].closed)
 def test_delayed_id4_reset_with_proven_recovery_still_needs_r_then_returns(self):
  def after(w):
   a=w.motor.bus.central_feedback.brake_capture
   if not hasattr(w,'delay_installed'):
    w.delay_installed=True;read=w.motor.bus.read
    def delayed(i,address,n):
     raw=read(i,address,n)
     if i==4 and(address,n)==(33,38)and raw[7]==2 and not hasattr(w,'delayed_axis4'):
      w.delayed_axis4=True;w.clock.advance(.012)
     return raw
    w.motor.bus.read=delayed
   if a.core.phase=='WAIT_CLEARANCE'and a.sensor_state()=='clear':w.motor.key(ord('r'))
  r,w=run(contact_in_state('happy',4,after),seconds=25)
  self.assertTrue(w.delayed_axis4);self.assertEqual(r['phase'],'NORMAL_PARKED',r['error'])
  a=w.motor.bus.central_feedback.brake_capture
  self.assertTrue(a.writers[0].audit['timing_recovery_support_verified'])
  self.assertFalse(a.writers[0].audit['timing_criterion_met'])
  self.assertEqual(sum(x['event']=='OPERATOR_CLEARANCE_R'for x in r['events']),1)
  self.assertEqual(r['reset']['h'],0.);self.assertTrue(r['cleanup_confirmed'])
 def test_return_tof_grace_requires_recent_clear_and_live_optical_frames(self):
  from .tof import ReturnDistancePolicy
  policy=ReturnDistancePolicy()
  def sample(t,kind='range',cm=50.):
   return dict(received_s=t,error=None,distance_cm=cm if kind=='range'else None,measurement_state=kind,range_status_raw=9 if kind=='range'else 7)
  self.assertEqual(policy.update(sample(10),10,False)['state'],'clear')
  self.assertEqual(policy.update(sample(10.1,'unreliable'),10.1,True)['quality'],'recent_clear_grace')
  self.assertEqual(policy.update(sample(10.51,'unreliable'),10.51,True)['state'],'unknown')
  self.assertEqual(policy.update(sample(11),11,False)['state'],'clear')
  self.assertEqual(policy.update(sample(11.1,'unreliable'),11.1,False)['state'],'unknown') # R cannot use grace
  self.assertEqual(policy.update(sample(11.2,'range',18),11.2,True)['state'],'near')
  self.assertEqual(policy.update(sample(11.3,'unreliable'),11.3,True)['state'],'unknown')
  policy.update(sample(12),12,False)
  self.assertEqual(policy.update(sample(12.01,'unreliable'),12.2,True)['state'],'unknown') # stale even within grace
  bad=sample(12.21,'unreliable');bad['error']='I2C failure'
  self.assertEqual(policy.update(bad,12.21,True)['state'],'hardware_fault')
 def test_single_unreliable_frame_during_return_does_not_stop_again(self):
  def after(w):
   a=w.motor.bus.central_feedback.brake_capture
   if a.core.phase=='WAIT_CLEARANCE'and a.sensor_state()=='clear':w.motor.key(ord('r'))
   if a.core.phase=='RETURNING'and not hasattr(w,'dip_s'):w.dip_s=w.clock()
   if hasattr(w,'dip_s'):w.distance.kind='unreliable'if w.clock()-w.dip_s<.1 else'range'
  r,w=run(contact_in_state('happy',2,after),seconds=25)
  self.assertEqual(r['phase'],'NORMAL_PARKED',r['error']);self.assertEqual(len(r['stops']),1)
  self.assertTrue(any(e['event']=='TOF_RETURN_DEGRADED'for e in r['events']))
 def test_automatic_button_handoff_rejects_failed_cleanup_or_intervening_fault(self):
  from .restart import start_after_button
  from types import SimpleNamespace as NS
  import threading
  for fault in ('cleanup','native','urgent','unsafe'):
   a=NS(restart_claimed=True,core=NS(phase='NORMAL_PARKED',error=None,pending=None))
   m=NS(bus=NS(central_feedback=NS(brake_capture=a),unsafe_damping_axes=set()),controller=NS(state='READY'),urgent_stop=threading.Event(),stopping=threading.Event(),finished=threading.Event(),cleanup_confirmed=False,watchdog=None,fault_message=lambda:None)
   def retire():
    m.stopping.set();m.finished.set();m.cleanup_confirmed=True
    if fault=='cleanup':m.cleanup_confirmed=False
    if fault=='native':m.controller.state='FAULT'
    if fault=='urgent':m.urgent_stop.set()
    if fault=='unsafe':m.bus.unsafe_damping_axes.add(3)
   m.disconnect_for_retry=retire;calls=[]
   with self.subTest(fault=fault),self.assertRaises(RuntimeError):start_after_button(m,'profile',lambda *x,**kw:calls.append(kw),True)
   self.assertEqual(calls,[])
 def test_button_restart_counts_five_new_complete_presses_only_after_park(self):
  from .restart import ButtonRestartGate
  from physical_button import BufferedInput
  source=BufferedInput(.06);t=0.
  def level(pressed):
   nonlocal t
   t+=.1;source.sample(pressed,t);t+=.1;source.sample(pressed,t)
  level(False);level(True)
  gate=ButtonRestartGate(source.diagnostics())
  level(False);gate.update(source.diagnostics());self.assertEqual(gate.count,0)
  for n in range(5):
   level(True);gate.update(source.diagnostics());self.assertEqual(gate.count,n)
   level(False);gate.update(source.diagnostics());self.assertEqual(gate.count,n+1)
  self.assertTrue(gate.ready)
  gate.update(source.diagnostics());self.assertEqual(gate.count,5)
 def test_button_restart_claim_is_once_only_and_retires_old_motor_owner(self):
  from .restart import take_restart,with_restart_gate
  def after(w):
   a=w.motor.bus.central_feedback.brake_capture
   if a.core.phase=='WAIT_CLEARANCE'and a.sensor_state()=='clear':w.motor.key(ord('r'))
   if a.core.phase=='NORMAL_PARKED':
    if not hasattr(w,'park_started'):w.park_started=w.clock()
    t=w.clock()-w.park_started
    w.inputs['button'].pressed=any(s<t<s+.17 for s in(.2,.6,1.,1.4,1.8))
    if take_restart(w.motor,255):
     w.claimed=True;self.assertFalse(take_restart(w.motor,255));w.motor.stopping.set()
  scenario=contact_in_state('happy',2,after)
  def extended(w):
   if hasattr(w,'park_time'):w.park_time=w.clock()
   scenario(w)
  r,w=run(extended,seconds=20)
  self.assertTrue(getattr(w,'claimed',False),r['error']);self.assertTrue(w.motor.cleanup_confirmed)
  from .restart import start_after_button
  w.motor.watchdog=None;w.motor.stopping.clear();marker=object()
  def factory(profile,operator_start):
   self.assertTrue(w.plant.closed);self.assertTrue(w.motor.cleanup_confirmed);self.assertTrue(operator_start);return marker
  self.assertIs(start_after_button(w.motor,'profile',factory,True),marker)
  source=(harness.ROOT/'shared/runtime/camera_preview.py').read_text(encoding='utf-8-sig')
  self.assertIn('trial_take_restart(motor,key)',with_restart_gate(source));compile(with_restart_gate(source),'trial-preview','exec')
 def test_parked_restart_uses_real_inputs_and_gui_claim_cannot_override_stop(self):
  from .restart import take_restart
  def after(w):
   a=w.motor.bus.central_feedback.brake_capture
   if a.core.phase=='WAIT_CLEARANCE'and a.sensor_state()=='clear':w.motor.key(ord('r'))
   if a.core.phase=='NORMAL_PARKED':
    if not hasattr(w,'park_started'):w.park_started=w.clock()
    t=w.clock()-w.park_started
    w.inputs['button'].pressed=any(s<t<s+.17 for s in(.2,.6,1.,1.4,1.8))
    if a.restart_gate and a.restart_gate.ready:w.parked_ready=True;w.motor.stopping.set()
  # contact scenario stops after 1s parked; this gate needs >2s, so use a
  # wrapper that keeps that existing scenario's park timer in the future.
  scenario=contact_in_state('happy',2,after)
  def extended(w):
   if hasattr(w,'park_time'):w.park_time=w.clock()
   scenario(w)
  r,w=run(extended,seconds=20)
  self.assertTrue(getattr(w,'parked_ready',False),r['error'])
  self.assertEqual(r['phase'],'NORMAL_PARKED');self.assertTrue(r['cleanup_confirmed'])
  self.assertFalse(take_restart(w.motor,ord('q')))
  self.assertFalse(take_restart(w.motor,255)) # Q already requested in owner
 def test_unknown_tof_during_return_holds_then_requires_new_r_without_fault(self):
  def after(w):
   a=w.motor.bus.central_feedback.brake_capture
   if a.core.phase=='WAIT_CLEARANCE'and a.sensor_state()=='clear'and a.stopped():
    w.motor.key(ord('r'))
   if a.core.phase=='RETURNING'and not hasattr(w,'unknown_injected'):
    w.unknown_injected=True;w.distance.kind='unreliable'
   if hasattr(w,'unknown_injected')and a.core.hold_epoch>=2:
    w.distance.kind='range'
  r,w=run(contact_in_state('happy',2,after),seconds=35)
  self.assertTrue(w.unknown_injected);self.assertEqual(r['phase'],'NORMAL_PARKED',r['error'])
  self.assertEqual(len(r['stops']),2)
  self.assertEqual(sum(e['event']=='MODELS_RESET'for e in r['events']),1)
  self.assertEqual(sum(e['event']=='OPERATOR_CLEARANCE_R'for e in r['events']),2)
  self.assertTrue(any(e['event']=='RETURN_PAUSED'and e['reason']=='unknown'for e in r['events']))
  self.assertTrue(r['source_profile_unchanged']);self.assertEqual(r['final_goals'],r['normal'])
 def test_led_backend_value_error_does_not_stop_motor_worker(self):
  def scenario(w):
   t=w.clock()-w.start;w.inputs['touch'].pressed=2<t<8
   if w.motor.behavior_trial=='happy'and w.motor.led_ring is not None and not hasattr(w,'led_failed'):
    def fail():raise ValueError('injected SPI LED value failure')
    w.motor.led_ring.pixels.show=fail;w.led_failed=True;w.frames_before_led_failure=len(w.plant.mutations)
   if t>6:w.motor.stopping.set()
  r,w=run(scenario,seconds=10)
  self.assertTrue(w.led_failed);self.assertTrue(w.motor.presentation_led_disabled)
  self.assertIsNone(r['error']);self.assertNotEqual(r['controller_state'],'FAULT');self.assertEqual(r['phase'],'PLAY')
  self.assertGreater(len(r['mutations']),w.frames_before_led_failure+5);self.assertEqual(r['stops'],[])
 def test_all_states_all_axes_require_manual_r_then_reset_and_normal(self):
  for state in ('normal','interested','happy','angry','afraid','sleepy'):
   for axis in range(1,6):
    def after(w):
     a=w.motor.bus.central_feedback.brake_capture
     if a.core.phase=='WAIT_CLEARANCE':
      if not hasattr(w,'waiting'):w.waiting=w.clock()
      if w.clock()-w.waiting>.3 and a.sensor_state()=='clear' and a.stopped() and not hasattr(w,'acknowledged'):
       w.acknowledged=True;w.motor.key(ord('r'))
    with self.subTest(state=state,axis=axis):
     r,w=run(contact_in_state(state,axis,after),seconds=35)
     self.assertTrue(getattr(w,'acknowledged',False),r['error']);self.assertEqual(r['phase'],'NORMAL_PARKED',r['error'])
     self.assertEqual(r['reset']['h'],0.);self.assertTrue(all(x['updates']==0 for x in r['reset']['bank'].values()))
     self.assertEqual(sum(e['event']=='MODELS_RESET'for e in r['events']),1);self.assertTrue(r['cleanup_confirmed'])
     self.assertEqual(r['final_goals'],r['normal']);self.assertTrue(r['source_profile_unchanged'])
 def test_clear_tof_alone_and_early_r_do_not_return(self):
  def after(w):
   if not hasattr(w,'early')and w.motor.bus.central_feedback.brake_capture.core.phase=='STOPPING':w.early=True;w.motor.key(ord('r'))
  r,w=run(contact_in_state('happy',2,after),seconds=8)
  self.assertEqual(r['phase'],'WAIT_CLEARANCE',r['error']);self.assertNotIn('NORMAL_RETURN_STARTED',[e['event']for e in r['events']])
 def test_live_contact_requires_explicit_trial_consent(self):
  from .integration import adapter_class
  with self.assertRaises(ValueError):adapter_class(None)
 def test_base_hold_read_failure_still_runs_group_recovery_before_fault_latch(self):
  def after(w):
   a=w.motor.bus.central_feedback.brake_capture
   if not hasattr(w,'installed_preflight_failure'):
    w.installed_preflight_failure=True;hold=a.hold
    def failed(epoch):
     if not hasattr(w,'failed_preflight'):w.failed_preflight=True;w.plant.drop_responses=1
     return hold(epoch)
    a.hold=failed
  r,w=run(contact_in_state('happy',2,after),seconds=8)
  a=w.motor.bus.central_feedback.brake_capture
  self.assertTrue(w.failed_preflight);self.assertEqual(r['phase'],'LATCHED')
  self.assertTrue(a.stop_writer.attempted);self.assertTrue(a.stop_writer.audit['recovery_verified'])
  self.assertTrue(a.fallback_report['confirmed']);self.assertFalse(getattr(w.motor.bus,'unsafe_damping_axes',()))
 def test_gui_r_queues_only_and_does_not_read_or_write_uart(self):
  def after(w):
   a=w.motor.bus.central_feedback.brake_capture
   if a.core.phase=='WAIT_CLEARANCE'and not hasattr(w,'queued_only'):
    with patch.object(a,'stopped',side_effect=AssertionError('GUI must not run stop validation')):w.motor.key(ord('r'))
    w.queued_only=True
  r,w=run(contact_in_state('happy',2,after),seconds=8)
  self.assertTrue(w.queued_only)
 def test_queued_r_cannot_authorize_a_newer_stop_epoch(self):
  def after(w):
   a=w.motor.bus.central_feedback.brake_capture
   if a.core.phase=='WAIT_CLEARANCE'and a.sensor_state()=='clear'and not hasattr(w,'raced'):
    original=a.stopped
    def interrupted_validation():
     result=original()
     if not hasattr(w,'injected'):
      w.injected=True;a.core.hold_epoch+=1
     return result
    a.stopped=interrupted_validation;w.raced=True;w.motor.key(ord('r'))
  r,w=run(contact_in_state('happy',2,after),seconds=8)
  self.assertTrue(w.raced);self.assertTrue(w.injected);self.assertEqual(r['phase'],'WAIT_CLEARANCE')
 def test_gui_start_retires_the_parked_owner_before_fresh_play(self):
  def after(w):
   a=w.motor.bus.central_feedback.brake_capture
   if a.core.phase=='WAIT_CLEARANCE'and a.sensor_state()=='clear':w.motor.key(ord('r'))
  r,w=run(contact_in_state('happy',2,after),seconds=15)
  self.assertEqual(r['phase'],'NORMAL_PARKED',r['error']);self.assertTrue(r['cleanup_confirmed'])
  from camera_preview import operator_motor_start
  marker=object()
  def factory(profile,operator_start):
   self.assertTrue(w.motor.cleanup_confirmed);self.assertTrue(w.plant.closed);self.assertTrue(operator_start);return marker
  # Harness never starts its watchdog thread; the virtual worker already finished.
  w.motor.watchdog=None
  self.assertIs(operator_motor_start(w.motor,'profile',factory),marker)
  r2,w2=run(contact_in_state('normal',3,after),seconds=15)
  self.assertEqual(r2['phase'],'NORMAL_PARKED',r2['error']);self.assertTrue(r2['cleanup_confirmed'])
 def test_stop_and_close_override_a_return_even_if_r_is_pressed_again(self):
  for command in('h','q'):
   def after(w):
    a=w.motor.bus.central_feedback.brake_capture
    if a.core.phase=='WAIT_CLEARANCE'and a.sensor_state()=='clear':w.motor.key(ord('r'))
    if a.core.phase=='RETURNING'and not hasattr(w,'aborted'):
     w.aborted=True
     if command=='q':w.motor.stopping.set()
     else:w.motor.key(ord('h'));w.motor.key(ord('r'))
   with self.subTest(command=command):
    r,w=run(contact_in_state('happy',2,after),seconds=10)
    self.assertTrue(w.aborted);self.assertNotEqual(r['phase'],'NORMAL_PARKED');self.assertTrue(r['cleanup_confirmed'])
 def test_native_fault_during_return_cannot_be_cleared_by_r(self):
  def after(w):
   a=w.motor.bus.central_feedback.brake_capture
   if a.core.phase=='WAIT_CLEARANCE'and a.sensor_state()=='clear':w.motor.key(ord('r'))
   if a.core.phase=='RETURNING':w.plant.bad_status[3]=1;w.motor.key(ord('r'))
  r,w=run(contact_in_state('happy',2,after),seconds=10)
  self.assertEqual(r['phase'],'LATCHED');self.assertNotIn('NORMAL_PARKED',[x['event']for x in r['events']])

class SelectedAxesTests(unittest.TestCase):
 def test_selected_axes_dispatch_only_selected_resistance_keep_all_feedback(self):
  from .integration import adapter_class,consent
  from types import SimpleNamespace as NS
  selected=consent((1,2,4))
  self.assertEqual(selected.ids,(1,2,4))
  cls=adapter_class(selected)
  for sid in range(1,6):
   with self.subTest(sid=sid):
    a=object.__new__(cls);a.auto_id1=NS(observe=lambda row:None,active=False);a.effort_monitor=None
    a.enabled_ids=set(selected.ids);a.history={i:[]for i in range(1,6)}
    a.m=NS();a.core=NS(phase='PLAY',pending=None);a.stop_writer=None;a.return_dispatch=False
    a.next_event=None
    row=dict(id=sid,time_s=1.)
    with patch('shared.experiments.central_safety_controller_20261110.runtime.queue_stop_test')as queue:
     a.observe(row,dict(decision='WOULD_STOP_RESISTANCE',reason='test'))
     self.assertEqual(queue.call_count,1 if sid in selected.ids else 0)
    self.assertEqual(len(a.history[sid]),1)
    with patch('shared.experiments.central_safety_controller_20261110.runtime.queue_stop_test')as queue:
     a.observe(row,dict(decision='WOULD_HOLD_DATA',reason='stale native feedback'))
     self.assertEqual(queue.call_count,1)
 def test_invalid_axes_cannot_grant_trial_authority(self):
  from .integration import adapter_class,consent,TrialConsent
  for ids in ((),(1,1),(0,),(6,),(True,),(1,'2')):
   with self.subTest(ids=ids),self.assertRaises(ValueError):
    adapter_class(TrialConsent(True,ids,True,True))
  with self.assertRaises(ValueError):adapter_class(consent((2,4)),isolate_tof=True,effort_stop=True,auto_id1_return=True)

 def test_selected_three_axes_reset_and_return_in_each_state(self):
  for state in ('normal','interested','happy','angry','afraid','sleepy'):
   for axis in (1,2,4):
    def after(w):
     a=w.motor.bus.central_feedback.brake_capture
     if a.core.phase=='WAIT_CLEARANCE'and a.sensor_state()=='clear'and a.stopped():w.motor.key(ord('r'))
    with self.subTest(state=state,axis=axis):
     r,w=run(contact_in_state(state,axis,after),seconds=35,contact_ids=(1,2,4))
     self.assertEqual(r['phase'],'NORMAL_PARKED',r['error'])
     self.assertEqual(r['reset']['h'],0.)
     self.assertTrue(all(x['updates']==0 for x in r['reset']['bank'].values()))
     self.assertTrue(r['cleanup_confirmed']);self.assertEqual(r['final_goals'],r['normal'])
     self.assertEqual(w.motor.bus.central_feedback.brake_capture.enabled_ids,{1,2,4})

 def test_launcher_cannot_expand_staged_contact_scope_on_reopen(self):
  from .launch import selected_contact_ids
  manifest={'enabled_ids':[1,2,4]}
  self.assertEqual(selected_contact_ids([],manifest),(1,2,4))
  self.assertEqual(selected_contact_ids(['--contact-ids','4,2,1'],manifest),(1,2,4))
  with self.assertRaises(ValueError):selected_contact_ids(['--contact-ids','1,2,3,4,5'],manifest)
  with self.assertRaises(ValueError):selected_contact_ids(['--contact-ids'],manifest)

class ColdStartTests(unittest.TestCase):
 def fixture(self,torque=0,matched=False):
  from types import SimpleNamespace as NS
  values={1:(8,16,0),2:(32,20,0),3:(24,26,0),4:(5,0,0),5:(7,3,0)}
  profile={'startup_pid_by_id':{str(i):dict(p=v[0],d=v[1],i=v[2])for i,v in values.items()}}
  desired={i:bytes(v)for i,v in values.items()}
  b=NS(manual_tuning=False,tuning_id=1,writes=[])
  b.values=dict(desired)if matched else {i:bytes((32,32,0))for i in range(1,6)}
  b.read=lambda i,a,n:b.values[i]if (a,n)==(21,3)else b'\1'if(a,n)==(55,1)else None
  def write(i,a,v):
   self.assertTrue(b.manual_tuning);self.assertEqual(b.tuning_id,i);self.assertEqual(a,21)
   b.writes.append((i,a,v));b.values[i]=v
  b.write=write
  b.snapshot=lambda:[dict(id=i,mode=0,status_raw=0,speed_raw=0,moving_raw=0,torque_raw=torque,position_raw=2000)for i in range(1,6)]
  return b,profile,desired
 def test_factory_pid_restore_precedes_recorder_without_any_motion_or_torque_write(self):
  from .startup import prepare_cold_pid_restore
  b,p,desired=self.fixture()
  report=prepare_cold_pid_restore(b,p)
  self.assertEqual(b.values,desired);self.assertEqual(len(b.writes),5)
  self.assertTrue(report['restored']);self.assertFalse(b.manual_tuning)
  self.assertEqual(report['pid_before']['1'],[32,32,0]);self.assertEqual(report['pid_after']['1'],list(desired[1]))
 def test_active_pid_mismatch_is_not_automatically_rewritten(self):
  from .startup import prepare_cold_pid_restore
  b,p,_=self.fixture(torque=1)
  with self.assertRaises(RuntimeError):prepare_cold_pid_restore(b,p)
  self.assertEqual(b.writes,[])
 def test_matching_active_pid_is_read_only(self):
  from .startup import prepare_cold_pid_restore
  b,p,_=self.fixture(torque=1,matched=True)
  self.assertFalse(prepare_cold_pid_restore(b,p)['restored']);self.assertEqual(b.writes,[])

class NormalSequenceTests(unittest.TestCase):
 def test_normal_planned_stop_uses_id1_auto_path_without_touch_or_happy(self):
  from .auto_recovery import RecoverySequence
  from types import SimpleNamespace as NS
  import threading
  keys=[]
  adapter=NS(next_event=None)
  view=dict(state='READY',behavior='normal',trial_safety=dict(phase='PLAY',led=dict(requested_brightness=.05)))
  m=NS(snapshot_view=lambda:view,stopping=threading.Event(),urgent_stop=threading.Event(),fault_message=lambda:None,led_ring=object(),key=keys.append,bus=NS(central_feedback=NS(brake_capture=adapter)))
  s=RecoverySequence(0.,auto_id1_return=True,stop_state='normal')
  self.assertFalse(s.tick(m,.1)['touch'])
  action=s.tick(m,.7)
  self.assertEqual(keys,[ord('v')]);self.assertEqual(s.phase,'STOP');self.assertFalse(action['touch'])
  self.assertEqual(adapter.next_event,dict(kind='test_stop',axis=1))

class RetirementRaceTests(unittest.TestCase):
 def test_last_owner_service_tick_during_claimed_retirement_preserves_proof(self):
  from .restart import take_restart
  def after(w):
   a=w.motor.bus.central_feedback.brake_capture
   if a.core.phase=='WAIT_CLEARANCE'and a.sensor_state()=='clear':w.motor.key(ord('r'))
   if a.core.phase=='NORMAL_PARKED':
    if not hasattr(w,'gate_started'):w.gate_started=w.clock()
    t=w.clock()-w.gate_started
    w.inputs['button'].pressed=any(s<t<s+.17 for s in(.2,.6,1.,1.4,1.8))
    if take_restart(w.motor,255):
     a.retiring_parked_owner=True;w.claimed=True;w.motor.stopping.set()
     # Real GUI can stop the owner while its current service tick is in flight.
     a.service(w.motor)
  contact=contact_in_state('happy',1,after)
  def scenario(w):
   if hasattr(w,'park_time'):w.park_time=w.clock()
   contact(w)
  r,w=run(scenario,seconds=20,contact_ids=(1,2,4))
  self.assertTrue(getattr(w,'claimed',False))
  self.assertIsNone(r['error'])
  self.assertTrue(r['cleanup_confirmed'])
  self.assertTrue(any(e['event']=='PARKED_OWNER_RETIRED_WITHOUT_REBASE'for e in r['events']))
  self.assertEqual(r['final_goals'],r['normal'])

class ID2ReleaseTests(unittest.TestCase):
 def test_displaced_loaded_axis_requires_fresh_low_effort_release_before_r(self):
  from .integration import adapter_class,consent
  from types import SimpleNamespace as NS
  a=object.__new__(adapter_class(consent((1,2,4))))
  a.stop_writer=NS(audit={'id2_contact_deflection':{}});a.core=NS(phase='WAIT_CLEARANCE')
  row=dict(id=2,position_raw=2662,goal_raw=2656,internal_target_raw=2656,speed_raw=0,moving_raw=0,load_raw=56,current_raw=2)
  a.m=NS(controller=NS(last_rows=[row],normal_tolerances={2:34}))
  a.session=NS(detector=NS(config={'ids':{'2':dict(current_limit_raw=40,pwm_limit_raw=358,internal_error_limit_ticks=44)}}))
  self.assertTrue(a.id1_contact_released())
  for key,value in(('position_raw',2674),('speed_raw',50),('moving_raw',1),('current_raw',41),('load_raw',359)):
   old=row[key];row[key]=value
   with self.subTest(key=key):self.assertFalse(a.id1_contact_released())
   row[key]=old
  row['position_raw']=row['goal_raw']+23
  self.assertFalse(a.id1_contact_released())
  a.core.phase='NORMAL_PARKED'
  self.assertTrue(a.id1_contact_released()) # Existing loaded Normal tolerance34, after deliberate return.
 def test_id2_recovery_cannot_run_with_id1_auto_return(self):
  from .integration import adapter_class,consent
  with self.assertRaises(ValueError):adapter_class(consent((1,2,4)),isolate_tof=True,effort_stop=True,auto_id1_return=True,id2_contact_recovery=True)
  with self.assertRaises(ValueError):adapter_class(consent((1,4)),id2_contact_recovery=True)

class SupportReleaseTests(unittest.TestCase):
 def test_id3_quiet_supported_residual_uses_existing34_and_rejects_effort(self):
  from .integration import adapter_class,consent
  from types import SimpleNamespace as NS
  a=object.__new__(adapter_class(consent((2,)),id2_contact_recovery=True))
  row=dict(id=3,position_raw=3005,goal_raw=2987,internal_target_raw=2987,speed_raw=0,moving_raw=0,load_raw=118,current_raw=10)
  a.stop_writer=NS(audit={'id3_contact_deflection':{}});a.core=NS(phase='WAIT_CLEARANCE')
  a.m=NS(controller=NS(last_rows=[row],normal_tolerances={3:34}))
  a.session=NS(detector=NS(config={'ids':{'3':dict(current_limit_raw=50,pwm_limit_raw=429)}}))
  self.assertTrue(a.id1_contact_released())
  for key,value in(('position_raw',3022),('current_raw',51),('load_raw',430),('speed_raw',50)):
   old=row[key];row[key]=value
   with self.subTest(key=key):self.assertFalse(a.id1_contact_released())
   row[key]=old

class FreshSupportRetirementTests(unittest.TestCase):
 def test_fresh_loaded_support_effort_cannot_reuse_cached_clearance(self):
  from .integration import adapter_class,consent
  from .restart import verify_parked_retirement
  from types import SimpleNamespace as NS
  a=object.__new__(adapter_class(consent((2,)),id2_contact_recovery=True))
  rows=[dict(id=i,mode=0,torque_raw=1,status_raw=0,speed_raw=0,moving_raw=0,goal_raw=2000,position_raw=2000,internal_target_raw=2000,load_raw=0,current_raw=0)for i in range(1,6)]
  rows[2].update(position_raw=2018,load_raw=118,current_raw=10)
  a.restart_claimed=True;a.restart_hold_goals={i:2000 for i in range(1,6)}
  a.core=NS(phase='NORMAL_PARKED',error=None,pending=None)
  a.stop_writer=NS(audit={'id3_contact_deflection':{}})
  a.m=NS(controller=NS(last_rows=rows,normal={i:2000 for i in range(1,6)},normal_tolerances={1:22,2:34,3:34,4:22,5:34}))
  a.session=NS(detector=NS(config={'ids':{'3':dict(current_limit_raw=50,pwm_limit_raw=429)}}))
  self.assertTrue(a.id1_contact_released());verify_parked_retirement(a,rows)
  renewed=[dict(r)for r in rows];renewed[2]['current_raw']=51
  with self.assertRaises(RuntimeError):verify_parked_retirement(a,renewed)

class HappyDwellTests(unittest.TestCase):
 def test_long_happy_baseline_does_not_request_v_early(self):
  from .auto_recovery import RecoverySequence
  from types import SimpleNamespace as NS
  import threading
  keys=[];v=dict(behavior='happy',trial_safety=dict(phase='PLAY',led=dict(requested_brightness=.05)))
  m=NS(snapshot_view=lambda:v,stopping=threading.Event(),urgent_stop=threading.Event(),fault_message=lambda:None,led_ring=object(),key=keys.append)
  s=RecoverySequence(0.,happy_dwell_s=6.);s.change('HAPPY',0.)
  s.tick(m,.1);s.tick(m,2.);self.assertEqual(keys,[])
  s.tick(m,6.2);self.assertEqual(keys,[ord('v')])


class ContactBrakeSequenceTests(unittest.TestCase):
 def test_id4_brake_request_uses_same_recovery_pipeline(self):
  from .auto_recovery import RecoverySequence
  def scenario(w):
   if not hasattr(w,'sequence'):w.sequence=RecoverySequence(w.clock(),contact_brake_axis=4)
   action=w.sequence.tick(w.motor,w.clock())
   for name in('touch','button'):w.inputs[name].pressed=action[name]
   if action['restart']:w.restart_requested=True;w.motor.stopping.set()
  r,w=run(scenario,seconds=25,contact_ids=(1,2,4))
  self.assertTrue(getattr(w,'restart_requested',False),r['error'])
  self.assertEqual(w.sequence.phase,'RESUMED')
  self.assertTrue(r['cleanup_confirmed']);self.assertIsNone(r['error'])
 def test_software_event_routes_contact_brake_without_claiming_physical_contact(self):
  from .auto_recovery import RecoverySequence
  from types import SimpleNamespace as NS
  import threading
  capture=NS(next_event=None);keys=[]
  view=dict(behavior='happy',trial_safety=dict(phase='PLAY',led=dict(requested_brightness=.05)))
  m=NS(snapshot_view=lambda:view,stopping=threading.Event(),urgent_stop=threading.Event(),fault_message=lambda:None,led_ring=object(),key=keys.append,bus=NS(central_feedback=NS(brake_capture=capture)))
  s=RecoverySequence(0.,contact_brake_axis=2);s.change('HAPPY',0.);s.tick(m,.1);s.tick(m,2.)
  self.assertEqual(capture.next_event,dict(kind='resistance',axis=2));self.assertEqual(keys,[ord('v')])


class DeferredRTests(unittest.TestCase):
 def test_one_r_waits_for_original_standstill_then_returns_without_second_press(self):
  def after(w):
   a=w.motor.bus.central_feedback.brake_capture
   if a.core.phase=='WAIT_CLEARANCE'and not hasattr(w,'one_r_time'):
    w.one_r_time=w.clock();original=a.stopped
    a.stopped=lambda:w.clock()-w.one_r_time>=.5 and original()
    w.motor.key(ord('r'))
  r,w=run(contact_in_state('happy',2,after),seconds=22,contact_ids=(2,))
  self.assertEqual(r['phase'],'NORMAL_PARKED',r['error'])
  self.assertTrue(any(e['event']=='MANUAL_R_WAIT_STILL'for e in r['events']))
  self.assertEqual(sum(e['event']=='OPERATOR_CLEARANCE_R'for e in r['events']),1)


class DeferredRAbortTests(unittest.TestCase):
 def test_wait_expires_without_late_auto_return(self):
  def after(w):
   a=w.motor.bus.central_feedback.brake_capture
   if a.core.phase=='WAIT_CLEARANCE'and not hasattr(w,'one_r_time'):
    w.one_r_time=w.clock();original=a.stopped;a.stopped=lambda:w.clock()-w.one_r_time>=3. and original();w.motor.key(ord('r'))
  r,w=run(contact_in_state('happy',2,after),seconds=22,contact_ids=(2,))
  self.assertEqual(r['phase'],'WAIT_CLEARANCE');self.assertTrue(any(e['event']=='MANUAL_R_WAIT_EXPIRED'for e in r['events']));self.assertFalse(any(e['event']=='NORMAL_RETURN_STARTED'for e in r['events']))
 def test_operator_stop_cancels_wait_without_authorization(self):
  def after(w):
   a=w.motor.bus.central_feedback.brake_capture
   if a.core.phase=='WAIT_CLEARANCE'and not hasattr(w,'one_r_time'):
    w.one_r_time=w.clock();a.stopped=lambda:False;w.motor.key(ord('r'))
   elif hasattr(w,'one_r_time')and w.clock()-w.one_r_time>.2 and not hasattr(w,'stopped_once'):
    w.stopped_once=True;w.motor.key(ord('h'))
  r,w=run(contact_in_state('happy',2,after),seconds=15,contact_ids=(2,))
  self.assertFalse(any(e['event']=='OPERATOR_CLEARANCE_R'for e in r['events']));self.assertFalse(any(e['event']=='NORMAL_RETURN_STARTED'for e in r['events']))


class DeferredRDeadlineTests(unittest.TestCase):
 def test_validation_crossing_deadline_cannot_grant_clearance(self):
  from .integration import adapter_class,consent
  from types import SimpleNamespace as NS
  import threading
  cls=adapter_class(consent((2,)),isolate_tof=True);a=cls.__new__(cls);clock=NS(t=0.);events=[]
  a.in_r_owner=True;a.auto_id1=NS(active=False);a.m=NS(stopping=threading.Event(),urgent_stop=threading.Event());a.core=NS(serial=1,hold_epoch=1,phase='WAIT_CLEARANCE',allow_return=True,pending=None,record=lambda name,**kw:events.append(name));a.clock=lambda:clock.t;a.healthy=lambda:True
  def stopped():clock.t+=2.1;return True
  a.stopped=stopped;a.id1_contact_released=lambda:True;a.sensor_state=lambda:'clear';a.r_wait=dict(token=(1,1),expires_s=2.);a.clear_token=None
  self.assertFalse(a.confirm_clearance((1,1),deferred=True));self.assertIsNone(a.clear_token);self.assertNotIn('OPERATOR_CLEARANCE_R',events)
