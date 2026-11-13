import tempfile,unittest
from functools import partial
from unittest.mock import patch
from pathlib import Path
from .test_integration import TrialPlant,harness
from .integration import hooks
from shared.experiments.central_safety_controller_20261110.scenarios import contact_in_state

def run(scenario,seconds=25,dark=False):
 with tempfile.TemporaryDirectory()as d,patch.object(harness,'Plant',TrialPlant),patch.object(harness,'hooks',partial(hooks,isolate_tof=True)):
  return harness.run(Path(d),scenario,seconds=seconds,enabled_ids=range(1,6),dark=dark)

class Tests(unittest.TestCase):
 def test_dark_hardware_adapter_runs_all_six_states_and_returns(self):
  for state in ('normal','interested','happy','angry','afraid','sleepy'):
   def after(w):
    a=w.motor.bus.central_feedback.brake_capture
    if a.core.phase=='WAIT_CLEARANCE':w.motor.key(ord('r'))
   with self.subTest(state=state):
    r,w=run(contact_in_state(state,2,after),seconds=30,dark=True)
    self.assertTrue(w.triggered);self.assertEqual(r['phase'],'NORMAL_PARKED',r['error'])
    self.assertIsNone(r['error']);self.assertTrue(r['cleanup_confirmed'])
 def test_five_fresh_button_releases_restart_even_when_tof_unavailable(self):
  from .restart import take_restart
  def after(w):
   a=w.motor.bus.central_feedback.brake_capture
   if a.core.phase in('STOPPING','WAIT_CLEARANCE','RETURNING','NORMAL_PARKED'):w.distance.kind='hardware_error'
   if a.core.phase=='WAIT_CLEARANCE':w.motor.key(ord('r'))
   if a.core.phase=='NORMAL_PARKED':
    if not hasattr(w,'gate_start'):w.gate_start=w.clock()
    t=w.clock()-w.gate_start
    w.inputs['button'].pressed=any(s<t<s+.17 for s in(.2,.6,1.,1.4,1.8))
    if take_restart(w.motor,255):w.claimed=True;w.motor.stopping.set()
  contact=contact_in_state('happy',2,after)
  def scenario(w):
   if hasattr(w,'park_time'):w.park_time=w.clock()
   contact(w)
  r,w=run(scenario,seconds=20)
  self.assertTrue(getattr(w,'claimed',False),r['error']);self.assertTrue(r['cleanup_confirmed'])
  self.assertEqual(sum(e['event']=='BUTTON_RESTART_READY'for e in r['events']),1)
  self.assertEqual(r['reset']['h'],0.)
  self.assertTrue(all(v['updates']==0 for v in r['reset']['bank'].values()))
 def test_all_six_states_stop_reset_and_return_with_missing_tof(self):
  for state in ('normal','interested','happy','angry','afraid','sleepy'):
   def after(w):
    a=w.motor.bus.central_feedback.brake_capture
    # Afraid first needs a genuinely clear frame after the real Near;
    # after R, sensor loss must not interrupt an authorized return.
    if a.core.phase=='RETURNING':w.distance.kind='hardware_error'
    if a.core.phase=='WAIT_CLEARANCE':w.motor.key(ord('r'))
   with self.subTest(state=state):
    r,w=run(contact_in_state(state,2,after),seconds=30)
    self.assertTrue(w.triggered);self.assertEqual(r['phase'],'NORMAL_PARKED',r['error'])
    self.assertEqual(r['reset']['h'],0.);self.assertTrue(r['source_profile_unchanged'])
    self.assertFalse(any(e['event']=='RETURN_PAUSED'for e in r['events']))
 def test_stop_and_q_cannot_be_overridden_when_tof_is_missing(self):
  for command in('h','q'):
   def after(w):
    a=w.motor.bus.central_feedback.brake_capture
    if a.core.phase=='WAIT_CLEARANCE':w.motor.key(ord('r'))
    if a.core.phase=='RETURNING'and not hasattr(w,'aborted'):
     w.aborted=True;w.distance.kind='hardware_error'
     if command=='q':w.motor.stopping.set()
     else:w.motor.key(ord('h'));w.motor.key(ord('r'))
   with self.subTest(command=command):
    r,w=run(contact_in_state('happy',2,after),seconds=10)
    self.assertTrue(w.aborted);self.assertNotEqual(r['phase'],'NORMAL_PARKED');self.assertTrue(r['cleanup_confirmed'])
 def test_bad_tof_cannot_interrupt_operator_authorized_return(self):
  for kind in ('unreliable','stale','hardware_error'):
   def after(w):
    a=w.motor.bus.central_feedback.brake_capture
    if a.core.phase in ('STOPPING','WAIT_CLEARANCE','RETURNING'):w.distance.kind=kind
    if a.core.phase=='WAIT_CLEARANCE':w.motor.key(ord('r'))
   with self.subTest(kind=kind):
    r,w=run(contact_in_state('happy',2,after))
    self.assertEqual(r['phase'],'NORMAL_PARKED',r['error'])
    self.assertEqual(sum(e['event']=='OPERATOR_CLEARANCE_R'for e in r['events']),1)
    self.assertFalse(any(e['event']=='RETURN_PAUSED'for e in r['events']))
    self.assertEqual(r['reset']['h'],0.);self.assertTrue(r['cleanup_confirmed'])
    self.assertEqual(w.motor.bus.central_feedback.brake_capture.sensor_snapshot['state'],'unavailable')
 def test_bad_tof_during_play_does_not_hold_motors(self):
  for kind in ('unreliable','stale','hardware_error'):
   def scenario(w):w.distance.kind=kind
   with self.subTest(kind=kind):
    r,w=run(scenario,seconds=4)
    self.assertIsNone(r['error']);self.assertEqual(r['controller_state'],'READY')
    self.assertNotEqual(w.motor.behavior_trial,'distance_wait');self.assertEqual(r['stops'],[])
 def test_real_near_still_pauses_return_and_native_fault_still_latches(self):
  for fault in ('near','native'):
   def after(w):
    a=w.motor.bus.central_feedback.brake_capture
    if a.core.phase=='WAIT_CLEARANCE'and not hasattr(w,'injected'):w.motor.key(ord('r'))
    if a.core.phase=='RETURNING':
     w.injected=True
     if fault=='near':w.distance.kind='range';w.distance.cm=15.
     else:w.plant.bad_status[3]=1
   with self.subTest(fault=fault):
    r,w=run(contact_in_state('happy',2,after),seconds=12)
    self.assertNotEqual(r['phase'],'NORMAL_PARKED')
    if fault=='near':self.assertTrue(any(e['event']=='RETURN_PAUSED'and e['reason']=='near'for e in r['events']))
    else:self.assertEqual(r['phase'],'LATCHED')
 def test_startup_missing_tof_is_nonblocking_without_fabricating_samples(self):
  from .offline_plant import Distance
  class Missing(Distance):
   def __init__(self,*a):super().__init__(*a);self.kind='hardware_error'
  with patch.object(harness,'Distance',Missing):r,w=run(None,seconds=4)
  self.assertIsNone(r['error']);self.assertTrue(r['cleanup_confirmed'])
  self.assertEqual(w.distance.latest()['error'],'I2C failure')
 def test_held_near_evidence_is_not_cleared_by_missing_input(self):
  from .tof_isolation import isolated_gate
  from bio_inspire.runtime.distance_behavior import DistanceGate
  g=isolated_gate(DistanceGate)()
  self.assertEqual(g.step(dict(distance_cm=15.,received_s=1.,error=None),1.),'near')
  for t in (1.5,2.,5.):
   self.assertIsNone(g.step(dict(distance_cm=None,received_s=t,error='I2C failure'),t));self.assertTrue(g.near)
  self.assertEqual(g.step(dict(distance_cm=50.,received_s=6.,error=None),6.),'clear')
 def test_sampled_button_has_no_gpiozero_hold_thread_during_retirement(self):
  from .inputs import SampledButton
  from physical_button import BufferedInput
  import sys
  from types import SimpleNamespace as NS
  calls=[];closed=[];active=[False]
  class Device:
   def __init__(self,pin,**kwargs):self.pin=NS(when_changed=object());calls.append((pin,kwargs))
   @property
   def is_active(self):return active[0]
   def close(self):closed.append('device')
  class Factory:
   def close(self):closed.append('factory')
  with patch.dict(sys.modules,{'gpiozero':NS(DigitalInputDevice=Device),'gpiozero.pins.lgpio':NS(LGPIOFactory=Factory)}),patch.object(BufferedInput,'start_sampling',lambda self,read:setattr(self,'reader',read)):
   button=SampledButton(.06);self.assertIsNone(button.device.pin.when_changed)
   self.assertFalse(button.reader());active[0]=True;self.assertTrue(button.reader());button.close()
  self.assertEqual(calls[0][0],27);self.assertTrue(calls[0][1]['pull_up'])
  self.assertEqual(closed,['device','factory'])

if __name__=='__main__':unittest.main()
