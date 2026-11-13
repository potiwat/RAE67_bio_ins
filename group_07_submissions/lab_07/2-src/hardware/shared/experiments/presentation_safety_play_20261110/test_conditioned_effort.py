import unittest
from .conditioned_effort import ContextEffortEvidence

def model():
 points=[]
 for source in range(2):
  for q in (2600,2604,2608,2612,2616,2620):
   points.append(dict(x=[q,80.,3100],y=[3,100,10],speed_cap=1000,acc=16,source=source))
 return dict(schema_version=1,sources=[dict(name='a'),dict(name='b')],points=points)

def row(i,t,**kw):
 r=dict(id=i,time_s=t,position_raw=2572,internal_target_raw=2600,goal_raw=2600,current_raw=18,load_raw=230,internal_error_ticks=28,target_speed_raw=1000,acceleration_raw=16,complete_feedback=True,controller_state='READY',operator_stopped=False,mode=0,torque_raw=1,status_raw=0)
 r.update(kw);return r

class Tests(unittest.TestCase):
 def test_static_reference_does_not_claim_moving_load_coverage(self):
  data=model()
  for point in data['points']:point['x'][1]=0.
  out=self.run_rows(ContextEffortEvidence(data))
  self.assertFalse(any(x['candidate_stop']for x in out))
  self.assertFalse(out[-1]['covered'])

 def test_moving_with_constant_loaded_tracking_lag_does_not_trigger(self):
  m=ContextEffortEvidence(model());out=[]
  for k in range(7):
   t=1+k*.05;ref=2600+k*4
   m.update(row(3,t-.001,internal_target_raw=3100),dict(decision='MONITOR'))
   out.append(m.update(row(2,t,internal_target_raw=ref,position_raw=ref-28),dict(decision='MONITOR')))
  self.assertFalse(any(x['candidate_stop']for x in out))

 def test_reference_catching_up_to_sagged_encoder_is_not_obstruction(self):
  m=ContextEffortEvidence(model());out=[]
  for k in range(6):
   t=1+k*.05;m.update(row(3,t-.001,internal_target_raw=3100),dict(decision='MONITOR'))
   out.append(m.update(row(2,t,internal_target_raw=2600+k*4,position_raw=2640,current_raw=18,load_raw=230),dict(decision='MONITOR')))
  self.assertFalse(any(x['candidate_stop']for x in out))

 def run_rows(self,m,**kw):
  result=[]
  for k in range(6):
   t=1+k*.05;m.update(row(3,t-.001,internal_target_raw=3100),dict(decision='MONITOR'))
   result.append(m.update(row(2,t,internal_target_raw=2600+k*4,**kw),dict(decision='MONITOR')))
  return result
 def test_relative_effort_with_moving_reference_detects_below_old_fixed_threshold(self):
  m=ContextEffortEvidence(model());a=self.run_rows(m)
  self.assertFalse(a[2]['candidate_stop']);self.assertTrue(a[-1]['candidate_stop']);self.assertEqual(a[-1]['path'],'context_reference')
 def test_normal_effort_and_static_reference_do_not_trigger(self):
  m=ContextEffortEvidence(model());self.assertFalse(any(x['candidate_stop']for x in self.run_rows(m,current_raw=3,load_raw=100,internal_error_ticks=10)))
  m=ContextEffortEvidence(model())
  for k in range(8):
   t=1+k*.05;m.update(row(3,t-.001,internal_target_raw=3100),dict(decision='MONITOR'));r=m.update(row(2,t),dict(decision='MONITOR'))
  self.assertFalse(r['candidate_stop'])
 def test_missing_reference_or_stale_support_is_unknown_never_clearance(self):
  m=ContextEffortEvidence(model())
  for k in range(8):r=m.update(row(2,1+k*.05),dict(decision='MONITOR'))
  self.assertFalse(r['candidate_stop']);self.assertFalse(r['covered'])
  m=ContextEffortEvidence(model());a=self.run_rows(m,target_speed_raw=600);self.assertFalse(any(x['candidate_stop']for x in a));self.assertFalse(a[-1]['covered'])
 def test_fault_gap_and_duplicate_timestamp_reset_persistence(self):
  m=ContextEffortEvidence(model());self.run_rows(m)
  self.assertFalse(m.update(row(2,2.),dict(decision='WOULD_HOLD_DATA'))['candidate_stop'])
  self.assertFalse(m.update(row(2,2.),dict(decision='MONITOR'))['candidate_stop'])
 def test_reference_is_validated_and_not_modified(self):
  import copy
  data=model();before=copy.deepcopy(data);self.run_rows(ContextEffortEvidence(data));self.assertEqual(data,before)
  data['points'][0]['x'][0]=float('nan')
  with self.assertRaises(ValueError):ContextEffortEvidence(data)


class RoutingTests(unittest.TestCase):
 def test_context_request_uses_existing_reset_hold_return_in_all_six_states(self):
  import tempfile
  from pathlib import Path
  from functools import partial
  from unittest.mock import patch
  from .test_integration import TrialPlant,harness
  from .integration import hooks,consent
  from shared.experiments.central_safety_controller_20261110.scenarios import contact_in_state
  class Evidence:
   stats={};last={}
   def update(self,row,decision):return dict(candidate_stop=row['id']==2 and row.get('current_raw',0)>=120 and decision['decision']=='MONITOR',covered=True,path='context_reference',reason='injected context evidence for routing test')
  for state in ('normal','interested','happy','angry','afraid','sleepy'):
   def after(w):
    a=w.motor.bus.central_feedback.brake_capture
    if a.core.phase=='WAIT_CLEARANCE'and a.id1_contact_released():w.motor.key(ord('r'))
   with self.subTest(state=state),tempfile.TemporaryDirectory()as out,patch.object(ContextEffortEvidence,'from_path',return_value=Evidence()),patch.object(harness,'Plant',TrialPlant),patch.object(harness,'hooks',partial(hooks,trial_consent=consent((2,)),isolate_tof=True,id2_contact_recovery=True,id2_effort_stop=True)):
    r,w=harness.run(Path(out),contact_in_state(state,2,after),seconds=40,enabled_ids=(2,),dark=True)
   self.assertEqual(r['phase'],'NORMAL_PARKED',r['error'])
   self.assertTrue(any(e['event']=='ID2_CONTEXT_EFFORT_STOP_REQUEST'for e in r['events']))
   self.assertEqual(w.motor.bus.central_feedback.brake_capture.writers[0].contact_axis,2)


class NativeSchemaTests(unittest.TestCase):
 def test_actual_decoded_rows_without_derived_error_can_detect(self):
  from normal_gaze_motor import decode_state
  m=ContextEffortEvidence(model());out=[]
  for k in range(6):
   for sid,ref,q in ((3,3100,3100),(2,2600+k*4,2572+k*2)):
    block=bytearray(38);block[7]=1;block[8]=16;block[13:15]=(1000).to_bytes(2,'little');block[23:25]=q.to_bytes(2,'little');block[27:29]=(230).to_bytes(2,'little');block[34:36]=ref.to_bytes(2,'little');block[36:38]=(18).to_bytes(2,'little')
    r=decode_state(sid,block);r.update(time_s=1+k*.05-(.001 if sid==3 else 0),complete_feedback=True,controller_state='READY',operator_stopped=False)
    self.assertNotIn('internal_error_ticks',r)
    result=m.update(r,dict(decision='MONITOR'))
    if sid==2:out.append(result)
  self.assertTrue(out[-1]['candidate_stop'])
