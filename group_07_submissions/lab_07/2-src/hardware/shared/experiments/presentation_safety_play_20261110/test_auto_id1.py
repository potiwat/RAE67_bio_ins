import unittest
from .test_native_stop import Bus
from .test_integration import TrialPlant,harness

class ProbePlant(TrialPlant):
 def refresh(self,i):
  super().refresh(i)
  if i==1 and i in self.contact and int.from_bytes(self.ram[i][48:50],'little')==160:
   a=self.ram[i];q=int.from_bytes(a[56:58],'little');goal=int.from_bytes(a[42:44],'little');error=abs(goal-q)
   a[67:69]=a[42:44];a[60:62]=(150 if error else 16).to_bytes(2,'little');a[69:71]=(5 if error else 1).to_bytes(2,'little')
 def apply(self,i,a,data):
  if i==1 and a==48 and data in((160).to_bytes(2,'little'),(1000).to_bytes(2,'little')):
   self.ram[i][48:50]=data;self.mutations.append(dict(time_s=self.clock(),id=i,address=a,data_hex=data.hex()));return
  return super().apply(i,a,data)

def run_auto(scenario,seconds=20):
 import tempfile
 from pathlib import Path
 from functools import partial
 from unittest.mock import patch
 from .integration import hooks
 with tempfile.TemporaryDirectory()as out,patch.object(harness,'Plant',ProbePlant),patch.object(harness,'hooks',partial(hooks,isolate_tof=True,effort_stop=True,auto_id1_return=True)):
  return harness.run(Path(out),scenario,seconds=seconds,enabled_ids=range(1,6),dark=True)

class Tests(unittest.TestCase):
 def test_recorded_normal_low_effort_residual_reholds_before_retry(self):
  from .auto_id1 import AutoID1
  from .offline_plant import Clock
  from types import SimpleNamespace as NS
  import threading
  clock=Clock();events=[];holds=[]
  row=dict(position_raw=2207,goal_raw=2214,internal_target_raw=2214,speed_raw=0,moving_raw=0,current_raw=1,load_raw=1052,torque_raw=1,mode=0,status_raw=0,acceleration_raw=3,target_speed_raw=600,torque_limit_raw=160,id=1)
  a=NS(clock=clock,core=NS(record=lambda name,**data:events.append(dict(event=name,**data))),m=NS(stopping=threading.Event(),urgent_stop=threading.Event(),controller=NS(normal={1:2019})),_safety=lambda fn:fn())
  p=AutoID1(a);p.active=True;p.phase='SETTLE';p.passed=False
  def read():return dict(row,time_s=clock()),None
  def hold():
   holds.append(clock());row['goal_raw']=row['internal_target_raw']=row['position_raw'];p.io.goal=row['goal_raw']
  p.io=NS(read=read,hold=hold,anchor=2215,goal=2214,window=(1691,2347))
  for _ in range(40):
   clock.advance(.05);p.tick()
   if p.attempts:break
  self.assertEqual(len(holds),1);self.assertEqual(p.phase,'PROBING');self.assertEqual(p.plan.target,2199)
  self.assertTrue(any(e['event']=='AUTO_ID1_STATIONARY_REHOLD'for e in events))
  # An OLD successful probe cannot use this correction to erase a later
  # residual and raise cap1000 without new motion/clearance evidence.
  row.update(goal_raw=2214,internal_target_raw=2214,position_raw=2207)
  p.io.goal=2214;p.phase='SETTLE';p.passed=True;p.stable=[];holds.clear()
  for _ in range(20):clock.advance(.05);p.tick()
  self.assertEqual(holds,[]);self.assertEqual(p.phase,'SETTLE')
  self.assertFalse(any(e['event']=='AUTO_ID1_RETURN_AUTHORIZED'for e in events))
 def test_real_motion_followed_by_still_tail_can_pass_but_zero_motion_cannot(self):
  from .auto_id1 import ProbePlan
  for q,expected in((2014,'passed'),(2000,'pause')):
   p=ProbePlan(2000,2100,0.);action=None
   for k in range(14):
    t=1+k*.05;r=dict(time_s=t,position_raw=q,internal_target_raw=2016,goal_raw=2016,speed_raw=0,moving_raw=0,current_raw=0,load_raw=0)
    action=p.step(r,t)
   self.assertEqual(action['action'],expected)
 def test_motion_and_still_proof_cannot_span_missing_feedback(self):
  from .auto_id1 import ProbePlan,AutoID1
  from types import SimpleNamespace as NS
  p=ProbePlan(2000,2100,0.)
  def row(t,q=2010):return dict(time_s=t,position_raw=q,internal_target_raw=q,goal_raw=q,speed_raw=0,moving_raw=0,current_raw=0,load_raw=0)
  for k in range(3):self.assertNotEqual(p.step(row(1+k*.05,2010+k),1+k*.05)['action'],'passed')
  self.assertEqual(p.step(row(1.5,2013),1.5)['action'],'pause')
  self.assertEqual(len(p.flow),0)
  a=AutoID1(NS());a.rest_at=1.
  for t in(1.,1.05,1.1):self.assertFalse(a.settled(row(t),t))
  self.assertFalse(a.settled(row(1.5),1.5));self.assertIsNone(a.rest_at)
 def test_unknown_internal_reference_prevents_probe_mutations(self):
  from .auto_id1 import ProbeIO
  b=self.bus();b.ram[1][67:69]=(2500).to_bytes(2,'little')
  p=ProbeIO(b,(1691,2347),lambda:False,b.clock)
  with self.assertRaisesRegex(RuntimeError,'reference'):p.prepare()
  self.assertTrue(p.uncertain_reference);self.assertEqual(b.frames,[])
 def test_bad_reference_midprobe_latches_unsafe_without_auto_return(self):
  from shared.experiments.central_safety_controller_20261110.scenarios import contact_in_state
  world=[]
  def after(w):
   if not world:world.append(w)
   p=w.motor.bus.central_feedback.brake_capture.auto_id1
   if p.phase=='PROBING'and not hasattr(w,'reference_injected'):
    w.reference_injected=True
    def bad(i,address,n):
     if i==1 and(address,n)==(33,38):w.plant.ram[1][67:69]=(2500).to_bytes(2,'little')
    w.plant.on_readback=bad
  with self.assertRaises(RuntimeError):run_auto(contact_in_state('happy',1,after),seconds=12)
  a=world[0].motor.bus.central_feedback.brake_capture
  self.assertTrue(a.auto_id1.failed);self.assertIn(1,world[0].motor.bus.unsafe_damping_axes)
  self.assertFalse(any(e['event']=='AUTO_ID1_RETURN_AUTHORIZED'for e in a.core.events))
  self.assertFalse(world[0].motor.cleanup_confirmed)
 def test_accepted_probe_goal_then_read_failure_uses_fresh_recovery(self):
  from unittest.mock import patch
  from .auto_id1 import ProbeIO
  from shared.experiments.central_safety_controller_20261110.scenarios import contact_in_state
  original=ProbeIO.write;failed=[False]
  def write(self,address,data,recovery=False):
   result=original(self,address,data,recovery=recovery)
   if address==42 and not recovery and int.from_bytes(data,'little')!=self.anchor and not failed[0]:
    failed[0]=True;raise OSError('injected lost read after accepted probe goal')
   return result
  with patch.object(ProbeIO,'write',write):r,w=run_auto(contact_in_state('happy',1),seconds=12)
  self.assertTrue(failed[0]);self.assertEqual(r['phase'],'LATCHED')
  self.assertEqual(sum(e['event']=='AUTO_ID1_FAILURE_RECOVERED'for e in r['events']),1)
  self.assertFalse(any(e['event']=='AUTO_ID1_RETURN_AUTHORIZED'for e in r['events']))
  self.assertEqual(int.from_bytes(w.plant.ram[1][48:50],'little'),1000)
 def test_restore_failure_on_q_stays_sticky_and_blocks_restart(self):
  from unittest.mock import patch
  from .auto_id1 import ProbeIO
  from shared.experiments.central_safety_controller_20261110.scenarios import contact_in_state
  world=[]
  def after(w):
   if not world:world.append(w)
   if w.motor.bus.central_feedback.brake_capture.auto_id1.phase=='PROBING':w.motor.stopping.set()
  with patch.object(ProbeIO,'restore',side_effect=OSError('injected restore failure')):
   with self.assertRaises(RuntimeError):run_auto(contact_in_state('happy',1,after),seconds=12)
  m=world[0].motor
  self.assertTrue(m.finished.is_set());self.assertFalse(m.cleanup_confirmed)
  self.assertIn(1,m.bus.unsafe_damping_axes)
  self.assertEqual(int.from_bytes(world[0].plant.ram[1][48:50],'little'),160)
 def test_near_during_active_probe_pauses_without_normal_return(self):
  from shared.experiments.central_safety_controller_20261110.scenarios import contact_in_state
  def after(w):
   p=w.motor.bus.central_feedback.brake_capture.auto_id1
   if p.phase=='PROBING'and not hasattr(w,'near_injected'):w.near_injected=True
   if hasattr(w,'near_injected'):w.distance.kind='range';w.distance.cm=15.
  r,w=run_auto(contact_in_state('happy',1,after),seconds=12)
  self.assertTrue(w.near_injected);self.assertNotEqual(r['phase'],'NORMAL_PARKED')
  self.assertTrue(any(e['event']=='AUTO_ID1_NEAR_PAUSED'for e in r['events']))
  self.assertFalse(any(e['event']=='AUTO_ID1_RETURN_AUTHORIZED'for e in r['events']))
  self.assertEqual(int.from_bytes(w.plant.ram[1][48:50],'little'),1000)
 def test_progress_then_resistance_release_retries_same_target(self):
  from shared.experiments.central_safety_controller_20261110.scenarios import contact_in_state
  def after(w):
   p=w.motor.bus.central_feedback.brake_capture.auto_id1
   if p.phase=='PROBING'and not hasattr(w,'second_contact')and abs(int.from_bytes(w.plant.ram[1][56:58],'little')-p.io.anchor)>=6:w.second_contact=w.clock()
   if hasattr(w,'second_contact')and w.clock()-w.second_contact<.8:w.plant.contact.add(1)
  r,w=run_auto(contact_in_state('happy',1,after),seconds=30)
  self.assertEqual(r['phase'],'NORMAL_PARKED',r['error'])
  begins=[e for e in r['events']if e['event']=='AUTO_ID1_PROBE_BEGIN']
  self.assertGreaterEqual(len(begins),2);self.assertEqual(len({e['target']for e in begins}),1)
 def test_partial_probe_setup_recovers_fresh_and_never_continues_after_fault(self):
  from unittest.mock import patch
  from .auto_id1 import ProbeIO
  from shared.experiments.central_safety_controller_20261110.scenarios import contact_in_state
  original=ProbeIO.write;failed=[False];world=[]
  def write(self,address,data,recovery=False):
   if address==41 and not recovery and not failed[0]:
    failed[0]=True;world[0].plant.contact.clear();raise OSError('injected setup failure after cap reduction')
   return original(self,address,data,recovery=recovery)
  def capture(w):
   if not world:world.append(w)
  with patch.object(ProbeIO,'write',write):r,w=run_auto(contact_in_state('happy',1,capture),seconds=10)
  self.assertEqual(r['phase'],'LATCHED');self.assertFalse(any(e['event']=='AUTO_ID1_RETURN_AUTHORIZED'for e in r['events']))
  self.assertTrue(any(e['event']=='AUTO_ID1_FAILURE_RECOVERED'for e in r['events']))
  self.assertEqual(int.from_bytes(w.plant.ram[1][48:50],'little'),1000)
 def test_h_and_q_during_probe_restore_original_cap_and_never_return(self):
  import tempfile
  from pathlib import Path
  from functools import partial
  from unittest.mock import patch
  from .test_integration import TrialPlant,harness
  from .integration import hooks
  from shared.experiments.central_safety_controller_20261110.scenarios import contact_in_state
  class AutoPlant(ProbePlant):
   def apply(self,i,a,data):
    if i==1 and a==48 and data in((160).to_bytes(2,'little'),(1000).to_bytes(2,'little')):
     self.ram[i][48:50]=data;return
    return super().apply(i,a,data)
  for command in('h','q'):
   def after(w):
    p=w.motor.bus.central_feedback.brake_capture.auto_id1
    if p.active and p.phase=='PROBING'and not hasattr(w,'interrupted'):
     w.interrupted=True
     if command=='q':w.motor.stopping.set()
     else:w.motor.key(ord('h'))
   with self.subTest(command=command),tempfile.TemporaryDirectory()as out,patch.object(harness,'Plant',AutoPlant),patch.object(harness,'hooks',partial(hooks,isolate_tof=True,effort_stop=True,auto_id1_return=True)):
    r,w=harness.run(Path(out),contact_in_state('happy',1,after),seconds=15,enabled_ids=range(1,6),dark=True)
    self.assertTrue(w.interrupted);self.assertNotEqual(r['phase'],'NORMAL_PARKED')
    self.assertEqual(int.from_bytes(w.plant.ram[1][48:50],'little'),1000)
    self.assertTrue(r['cleanup_confirmed'])
 def test_all_states_return_after_id1_probe_without_any_r(self):
  import tempfile
  from pathlib import Path
  from functools import partial
  from unittest.mock import patch
  from .test_integration import TrialPlant,harness
  from .integration import hooks
  from shared.experiments.central_safety_controller_20261110.scenarios import contact_in_state
  class AutoPlant(ProbePlant):
   def apply(self,i,a,data):
    if i==1 and a==48 and data in((160).to_bytes(2,'little'),(1000).to_bytes(2,'little')):
     self.ram[i][48:50]=data;self.mutations.append(dict(time_s=self.clock(),id=i,address=a,data_hex=data.hex()));return
    return super().apply(i,a,data)
  for state in('normal','interested','happy','angry','afraid','sleepy'):
   with self.subTest(state=state),tempfile.TemporaryDirectory()as out,patch.object(harness,'Plant',AutoPlant),patch.object(harness,'hooks',partial(hooks,isolate_tof=True,effort_stop=True,auto_id1_return=True)):
    r,w=harness.run(Path(out),contact_in_state(state,1),seconds=30,enabled_ids=range(1,6),dark=True)
    self.assertEqual(r['phase'],'NORMAL_PARKED',r['error'])
    self.assertTrue(any(e['event']=='AUTO_ID1_RETURN_AUTHORIZED'for e in r['events']))
    self.assertFalse(any(e['event']=='OPERATOR_CLEARANCE_R'for e in r['events']))
    self.assertEqual(int.from_bytes(w.plant.ram[1][48:50],'little'),1000)
    self.assertEqual(r['reset']['h'],0.);self.assertTrue(r['cleanup_confirmed'])
 def bus(self):
  b=Bus()
  for i,a in b.ram.items():
   a[42:44]=a[56:58];a[67:69]=a[56:58];a[58:60]=b'\0\0';a[66]=0;a[60:62]=b'\0\0';a[69:71]=b'\0\0'
  return b
 def test_probe_uses_accepted_profile_and_restores_without_pid_or_body_writes(self):
  from .auto_id1 import ProbeIO
  b=self.bus();before={i:bytes(a)for i,a in b.ram.items()}
  p=ProbeIO(b,(1691,2347),cancelled=lambda:False,clock=b.clock)
  p.prepare()
  self.assertEqual(int.from_bytes(b.ram[1][48:50],'little'),160)
  self.assertEqual(int.from_bytes(b.ram[1][46:48],'little'),600);self.assertEqual(b.ram[1][41],3)
  p.hold();p.restore()
  self.assertTrue(p.restored);self.assertEqual(b.ram[1][41],before[1][41]);self.assertEqual(b.ram[1][46:50],before[1][46:50])
  self.assertTrue(all(bytes(b.ram[i])==before[i]for i in(2,3,4,5)))
  for packet in b.frames:
   self.assertEqual(packet[2],1);self.assertIn(packet[5],(41,42,46,48))
 def test_probe_requires_genuine_motion_and_cannot_ratchet(self):
  from .auto_id1 import ProbePlan
  p=ProbePlan(2000,2100,0.)
  for k in range(12):
   action=p.step(dict(time_s=k*.1,position_raw=2000,internal_target_raw=2000,goal_raw=2000,speed_raw=0,moving_raw=0,current_raw=0,load_raw=0),k*.1)
   self.assertNotEqual(action['action'],'passed')
   if 'goal'in action:self.assertLessEqual(abs(action['goal']-2000),16)
  r=dict(time_s=2.,position_raw=2011,internal_target_raw=2011,goal_raw=2011,speed_raw=40,moving_raw=1,current_raw=0,load_raw=0)
  result=None
  for k in range(5):r['time_s']=2+k*.05;r['position_raw']=2010+k;result=p.step(r,r['time_s'])
  self.assertEqual(result['action'],'passed')
 def test_probe_effort_pauses_and_new_attempt_has_same_anchor(self):
  from .auto_id1 import ProbePlan
  p=ProbePlan(2000,2100,0.)
  r=dict(time_s=.5,position_raw=2000,internal_target_raw=2014,goal_raw=2014,speed_raw=0,moving_raw=0,current_raw=8,load_raw=180)
  self.assertEqual(p.step(r,.5)['action'],'pause')
  self.assertEqual(p.target,2016)

if __name__=='__main__':unittest.main()
