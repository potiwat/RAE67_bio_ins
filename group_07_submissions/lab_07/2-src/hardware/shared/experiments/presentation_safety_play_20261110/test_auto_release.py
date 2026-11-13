import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from .test_integration import harness,TrialPlant
from .integration import hooks,consent
from .restart import take_restart
from shared.experiments.central_safety_controller_20261110.scenarios import contact_in_state

class ProbePlant(TrialPlant):
 def apply(self,i,address,data):
  if address==48:
   value=int.from_bytes(data,'little')
   if i not in(1,2,4)or value not in(1000,400 if i==2 else 160):raise AssertionError('Unreviewed probe cap')
   self.ram[i][48:50]=data;self.mutations.append(dict(time_s=self.clock(),id=i,address=48,data_hex=data.hex()));return
  return super().apply(i,address,data)
 def refresh(self,i):
  a=self.ram[i]
  if int.from_bytes(a[48:50],'little')!=1000 and i in self.contact:
   a[67:69]=a[42:44];a[58:60]=bytes(2);a[66]=0;a[60:62]=(350).to_bytes(2,'little');a[69:71]=(45).to_bytes(2,'little');return
  return super().refresh(i)

class AutoReleaseTests(unittest.TestCase):
 def test_angry_read_window_cannot_clip_probe_toward_approved_normal_endpoint(self):
  from types import SimpleNamespace as NS
  from .auto_release import AutoRelease
  from .native_stop import GroupStop
  bus=NS();windows={i:(1800,1951)for i in range(1,6)};w=GroupStop(windows);w.bus=bus;w.verified=w.restored=True;w.expected[4]=bytes((1,24))+(1932).to_bytes(2,'little')+bytes(4)
  c=NS(normal={4:1997},last_rows=[dict(id=4,position_raw=1932)],joint_windows={4:(1963,2031)})
  core=NS(event=dict(kind='resistance',axis=4),phase='WAIT_CLEARANCE',allow_return=True,reset_done=True,pending=None,error=None,serial=1,hold_epoch=1,record=lambda *args,**kw:None)
  a=NS(core=core,m=NS(bus=bus,controller=c,stopping=NS(is_set=lambda:False),urgent_stop=NS(is_set=lambda:False)),stop_writer=w,healthy=lambda:True,stopped=lambda:True,sensor_state=lambda:'clear',clear_token=None,enabled_ids={1,2,4},clock=lambda:1.,_safety=lambda fn:fn())
  def io(bus,sid,window,*args,**kw):return NS(window=window,anchor_goal=1932,anchor_q=1932,goal=1932,excursion=32,prepared=True,prepare=lambda:None,still=[])
  p=AutoRelease(a)
  with patch('shared.experiments.presentation_safety_play_20261110.auto_release.ReleaseIO',side_effect=io):p.begin()
  p.start_attempt({});self.assertEqual(p.plan.target,1964);self.assertEqual(p.io.window,(1800,1997));self.assertEqual(w.windows,windows)
 def test_exact_normal_head_probe_uses_only_existing_reviewed_command_window(self):
  from types import SimpleNamespace as NS
  from .auto_release import AutoRelease
  from .native_stop import GroupStop
  for reviewed,expected in (((1963,2031),(1965,2029)),((1972,2022),(1972,2022))):
   bus=NS();w=GroupStop({i:(1975,2019)for i in range(1,6)});w.bus=bus;w.verified=w.restored=True;w.expected[4]=bytes((1,12))+bytes.fromhex('cd07')+bytes(4)
   c=NS(normal={4:1997},last_rows=[dict(id=4,position_raw=1997)],joint_windows={4:reviewed})
   core=NS(event=dict(kind='resistance',axis=4),phase='WAIT_CLEARANCE',allow_return=True,reset_done=True,pending=None,error=None,serial=1,hold_epoch=1,record=lambda *args,**kw:None)
   a=NS(core=core,m=NS(bus=bus,controller=c,stopping=NS(is_set=lambda:False),urgent_stop=NS(is_set=lambda:False)),stop_writer=w,healthy=lambda:True,stopped=lambda:True,sensor_state=lambda:'clear',clear_token=None,enabled_ids={1,2,4},clock=lambda:1.,_safety=lambda fn:fn())
   def io(bus,sid,window,*args,**kw):return NS(window=window,anchor_goal=1997,anchor_q=1997,excursion=32,prepared=True,prepare=lambda:None)
   p=AutoRelease(a);p.pin_epoch=(0,0,4);p.epoch_attempts=7
   with patch('shared.experiments.presentation_safety_play_20261110.auto_release.ReleaseIO',side_effect=io):p.begin()
   self.assertEqual(p.io.window,expected);self.assertEqual(w.windows[4],(1975,2019));self.assertEqual(p.pin_window,expected);self.assertEqual(p.epoch_attempts,0)
 def test_exact_normal_hold_still_selects_a_bounded_nonzero_probe(self):
  from types import SimpleNamespace as NS
  from .auto_release import AutoRelease
  for sid in (1,2,4):
   raw=bytearray(38);raw[34:36]=(1997).to_bytes(2,'little');events=[]
   a=NS(m=NS(controller=NS(normal={sid:1997})),stop_writer=NS(original={sid:bytes(raw)}),clock=lambda:1.,core=NS(record=lambda name,**kw:events.append(name)))
   p=AutoRelease(a);p.sid=sid;p.io=NS(anchor_q=1997,anchor_goal=1997,goal=1997,window=(1975,2019),still=[])
   p.start_attempt({})
   self.assertNotEqual(p.plan.target,1997);self.assertGreaterEqual(p.plan.target,1975);self.assertLessEqual(p.plan.target,2019)
   self.assertFalse(p.plan.motion_verified);self.assertIn('AUTO_RELEASE_PROBE_BEGIN',events)
 def test_adopted_hold_preserves_accepted_happy_windows_after_controller_stops(self):
  # Actual failure: accepted Happy ID4 goal2021, encoder2015. STOPPED's
  # Normal feedback window ends2019; it must not replace the accepted window.
  from types import SimpleNamespace as NS
  from .auto_release import AutoRelease
  from .native_stop import GroupStop
  from normal_gaze_motor import decode_state
  windows={i:(0,4095)for i in range(1,6)};windows[4]=(1750,2200)
  blocks={}
  for i in range(1,6):
   b=bytearray(38);b[7]=1;b[8]=24;b[9:11]=(2021).to_bytes(2,'little');b[13:15]=(1000).to_bytes(2,'little');b[15:17]=(1000).to_bytes(2,'little');b[23:25]=(2015).to_bytes(2,'little');b[34:36]=(2021).to_bytes(2,'little');blocks[i]=bytes(b)
  bus=NS(read=lambda i,address,count:blocks[i])
  prior=GroupStop(windows);prior.bus=bus;prior.verified=True;prior.restored=True
  controller=NS(feedback_window=lambda i:(1975,2019)if i==4 else windows[i],normal_tolerances={i:22 for i in windows})
  now=[1.];a=NS(m=NS(bus=bus,controller=controller),clock=lambda:now[0],stop_writer=prior,writers=[])
  p=AutoRelease(a);p.sid=2;p.io=NS(audit=[],window=windows[2])
  for t in (1.,1.05,1.1):
   now[0]=t;self.assertFalse(p.adopt_hold())
  now[0]=1.15;self.assertTrue(p.adopt_hold())
  self.assertEqual(a.stop_writer.windows,windows)
  a.stop_writer.guard_feedback(decode_state(4,blocks[4]))
  self.assertEqual(a.stop_writer.expected[4][2:4],(2021).to_bytes(2,'little'))
  outside=decode_state(4,blocks[4]);outside['position_raw']=2201
  with self.assertRaisesRegex(RuntimeError,'envelope'):a.stop_writer.guard_feedback(outside)
 def test_single_speed_spike_clears_proof_but_does_not_relax_stationary_checks(self):
  from types import SimpleNamespace as NS
  from .auto_release import AutoRelease
  from .native_stop import GroupStop
  windows={i:(1800,2200)for i in range(1,6)};blocks={};now=[1.]
  for i in windows:
   raw=bytearray(38);raw[7]=1;raw[8]=8;raw[9:11]=(1930).to_bytes(2,'little')
   raw[23:25]=(1932).to_bytes(2,'little');raw[34:36]=raw[9:11];blocks[i]=raw
  bus=NS(read=lambda i,a,n:bytes(blocks[i]));prior=GroupStop(windows)
  prior.bus=bus;prior.verified=prior.restored=True
  c=NS(normal_tolerances={i:22 for i in windows},feedback_window=lambda i:windows[i])
  a=NS(m=NS(bus=bus,controller=c),clock=lambda:now[0],stop_writer=prior,writers=[])
  p=AutoRelease(a);p.sid=2;p.io=NS(window=windows[2],audit=[])
  self.assertFalse(p.adopt_hold());now[0]=1.05;blocks[1][25:27]=(50).to_bytes(2,'little')
  self.assertFalse(p.adopt_hold());self.assertEqual(p.post_probe_support,[])
  blocks[1][25:27]=bytes(2)
  for t in (1.1,1.15,1.2):
   now[0]=t;self.assertFalse(p.adopt_hold())
  now[0]=1.25;self.assertTrue(p.adopt_hold())
  # Fast read loops must accumulate time, not discard all but four samples
  # forever. Still no acceptance before 0.15s of fresh zero-speed evidence.
  for k in range(15):
   now[0]=1.3+k*.01;self.assertFalse(p.adopt_hold())
  now[0]=1.45;self.assertTrue(p.adopt_hold())
 def test_calibrated_near_reopen_rechecks_other_joints_before_any_cap_write(self):
  from types import SimpleNamespace as NS
  from .auto_release import AutoRelease
  normal={1:2019,2:2837,3:2746,4:1997,5:2696};rows=[]
  for i in range(1,6):rows.append(dict(id=i,mode=0,torque_raw=1,status_raw=0,speed_raw=0,moving_raw=0,position_raw=normal[i],goal_raw=normal[i],internal_target_raw=normal[i]))
  rows[1].update(goal_raw=2844,position_raw=2851,internal_target_raw=2844)
  rows[2].update(goal_raw=2781,position_raw=2781,internal_target_raw=2781)
  events=[];c=NS(normal=normal,last_rows=rows,normal_tolerances={i:34 if i in(2,3,5)else 22 for i in normal},feedback_window=lambda i:(2700,3200))
  a=NS(core=NS(event=dict(kind='resistance',axis=2),phase='WAIT_CLEARANCE',allow_return=True,reset_done=True,pending=None,serial=1,hold_epoch=1,record=lambda *args,**kw:events.append(args[0])),m=NS(controller=c),healthy=lambda:True,stopped=lambda:True,sensor_state=lambda:'clear',clear_token=None,enabled_ids={1,2,4})
  p=AutoRelease(a);p.pin_epoch=(1,1,2);p.pinned_source=(2844,2851);p.pin_calibration=(2819,2851)
  with patch('shared.experiments.presentation_safety_play_20261110.auto_release.ReleaseIO',side_effect=AssertionError('Unexpected cap/probe prepare')):p.begin()
  self.assertFalse(p.active);self.assertEqual(p.phase,'WAIT_SUPPORT');self.assertIn('AUTO_RELEASE_WAIT_SUPPORT',events)
 def run_case(self,state,axis,hold_contact_until=None,extra=None):
  def after(w):
   a=w.motor.bus.central_feedback.brake_capture
   if hold_contact_until is not None and w.triggered and w.clock()-w.trigger_time<hold_contact_until:
    w.plant.contact.add(axis);w.clearance=False
   if extra:extra(w)
   if take_restart(w.motor,255):w.resumed=True;w.motor.stopping.set()
  with tempfile.TemporaryDirectory()as d,patch.object(harness,'Plant',ProbePlant),patch.object(harness,'hooks',lambda *a,**kw:hooks(*a,**{**kw,'trial_consent':consent((1,2,4)),'id2_contact_recovery':True,'auto_contacts':True,'isolate_tof':True,'resume_after_normal':True})):
   return harness.run(Path(d),contact_in_state(state,axis,after),seconds=35,enabled_ids=())
 def test_normal_id2_contact_removed_returns_without_r_or_five_button_events(self):
  r,w=self.run_case('normal',2)
  self.assertTrue(getattr(w,'resumed',False),r['error']);self.assertIsNone(r['error'])
  events=[v['event']for v in r['events']]
  self.assertIn('AUTO_RELEASE_RETURN_AUTHORIZED',events);self.assertIn('AUTO_PLAY_RESUME_READY',events)
  self.assertNotIn('OPERATOR_CLEARANCE_R',events);self.assertNotIn('BUTTON_RESTART_ARMED',events)
  self.assertTrue(r['cleanup_confirmed'])
 def test_happy_id4_contact_can_use_same_central_flow(self):
  r,w=self.run_case('happy',4)
  self.assertTrue(getattr(w,'resumed',False),r['error']);self.assertIsNone(r['error']);self.assertTrue(r['cleanup_confirmed'])
 def test_all_three_axes_in_all_six_states_use_same_flow(self):
  for state in('normal','interested','happy','angry','afraid','sleepy'):
   for axis in(1,2,4):
    with self.subTest(state=state,axis=axis):
     r,w=self.run_case(state,axis);self.assertIsNone(r['error']);self.assertTrue(getattr(w,'resumed',False),(r['phase'],r['events'][-3:]));self.assertTrue(r['cleanup_confirmed'])
     self.assertTrue(all(x['address']not in(18,21,22,23,33)for x in r['mutations']))
 def test_obstruction_held_then_removed_does_not_restore_cap_and_push_through(self):
  r,w=self.run_case('happy',2,hold_contact_until=5.)
  self.assertIsNone(r['error']);self.assertTrue(getattr(w,'resumed',False));self.assertTrue(r['cleanup_confirmed'])
  a=w.motor.bus.central_feedback.brake_capture
  self.assertTrue(a.auto_id1.attempts>=1)
 def test_near_toggle_during_probe_retains_same_original_envelope(self):
  pins=[];pauses=[0];cleared_at=[None]
  def extra(w):
   a=w.motor.bus.central_feedback.brake_capture;p=a.auto_id1
   if p.active and p.io is not None and p.io.prepared:pins.append((p.io.anchor_goal,p.io.anchor_q))
   if p.phase=='PROBING'and p.io.goal!=p.io.anchor_goal and pauses[0]<2 and cleared_at[0]is None:
    w.distance.cm=15;pauses[0]+=1;cleared_at[0]=w.clock()+.3
   elif cleared_at[0]is not None:
    w.distance.cm=15
    if w.clock()>=cleared_at[0]:w.distance.cm=50;cleared_at[0]=None
  r,w=self.run_case('happy',2,extra=extra)
  self.assertEqual(pauses[0],2);self.assertTrue(getattr(w,'resumed',False),r['error']);self.assertEqual(len(set(pins)),1);self.assertTrue(r['cleanup_confirmed'])
 def test_q_during_probe_restores_profiles_without_resuming(self):
  def extra(w):
   p=w.motor.bus.central_feedback.brake_capture.auto_id1
   if p.active and p.phase=='PROBING'and p.io.goal!=p.io.anchor_goal:w.q_injected=True;w.motor.stopping.set()
  r,w=self.run_case('happy',4,extra=extra)
  self.assertTrue(w.q_injected);self.assertTrue(r['cleanup_confirmed']);self.assertFalse(getattr(w,'resumed',False))
  self.assertTrue(all(int.from_bytes(a[48:50],'little')==1000 for a in w.plant.ram.values()))
 def test_accepted_probe_write_with_lost_read_proof_uses_independent_stop(self):
  def extra(w):
   if getattr(w,'injection_ready',False):return
   w.injection_ready=True
   def readback(i,address,count):
    p=w.motor.bus.central_feedback.brake_capture.auto_id1
    if i==2 and address==33 and p.active and p.phase=='PROBING'and p.io.pending and p.io.pending['address']==42 and not getattr(w,'lost_proof',False):
     w.plant.ram[2][62]=59;w.lost_proof=True;w.reset_voltage=True
   def packet(op):
    if getattr(w,'reset_voltage',False):w.plant.ram[2][62]=72;w.reset_voltage=False
   w.plant.on_readback=readback;w.plant.on_packet=packet
  r,w=self.run_case('happy',2,extra=extra)
  self.assertTrue(w.lost_proof);self.assertTrue(r['cleanup_confirmed']);self.assertFalse(getattr(w,'resumed',False))
  self.assertTrue(all(int.from_bytes(a[48:50],'little')==1000 for a in w.plant.ram.values()))
 def test_h_during_configuration_or_restore_brakes_and_restores_without_play(self):
  for trigger in('CONFIGURING','RESTORING'):
   def extra(w):
    if getattr(w,'injection_ready',False):return
    w.injection_ready=True
    def packet(op):
     p=w.motor.bus.central_feedback.brake_capture.auto_id1
     if op==3 and p.active and p.phase==trigger and not getattr(w,'h_injected',False):
      w.h_injected=True;w.motor.key(ord('h'))
    w.plant.on_packet=packet
    # A real hand can remove foam while the owner performs bounded cleanup.
    # The virtual main pump is paused then, so drive removal from read time.
    def readback(i,address,count):
     if w.triggered and w.clock()-w.trigger_time>1.:w.plant.contact.clear()
    w.plant.on_readback=readback
   with self.subTest(trigger=trigger):
    r,w=self.run_case('happy',4,extra=extra)
    self.assertTrue(getattr(w,'h_injected',False));self.assertTrue(r['cleanup_confirmed']);self.assertFalse(getattr(w,'resumed',False))
    self.assertTrue(all(int.from_bytes(a[48:50],'little')==1000 for a in w.plant.ram.values()))

if __name__=='__main__':unittest.main()
