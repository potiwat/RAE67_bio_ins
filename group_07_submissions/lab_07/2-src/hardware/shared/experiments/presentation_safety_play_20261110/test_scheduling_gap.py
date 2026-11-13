import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace as NS


class Tests(unittest.TestCase):
 def test_explicit_stop_native_fault_unsafe_mode_and_expired_evidence_cannot_rearm(self):
  from .integration import adapter_class,consent
  cls=adapter_class(consent((1,2,4)),isolate_tof=True,auto_contacts=True,id2_contact_recovery=True)
  for reason in ('close','stop','native','unsafe','expired','wrong_axis'):
   a=cls.__new__(cls);a.clock=lambda:1.;a.enabled_ids={1,2,4};a.scheduling_gap_candidate=dict(axis=1,observed_s=0. if reason=='expired'else 1.,evidence={})
   a.m=NS(stopping=NS(is_set=lambda:reason=='close'),urgent_stop=NS(is_set=lambda:reason=='stop'),bus=NS(unsafe_damping_axes={4}if reason=='unsafe'else set()))
   a.healthy=lambda:reason!='native';a.core=NS(record=lambda *args,**kw:None)
   self.assertFalse(a.allow_feedback_gap_recovery(dict(kind='feedback_gap',axis=2 if reason=='wrong_axis'else 1,serial=1)),reason)

 def test_recorded_publish_stall_qualifies_but_unknown_or_old_gaps_do_not(self):
  from .scheduling_gap import publish_stall_evidence
  gap=1.651048322;now=181.728059993
  timing={'recent_slow':[dict(operation='_publish',start_s=180.084978895,end_s=181.727088782,duration_s=1.642109887)]}
  self.assertIsNotNone(publish_stall_evidence(timing,gap,now))
  self.assertIsNone(publish_stall_evidence(timing,gap,now+1.))
  self.assertIsNone(publish_stall_evidence({'recent_slow':[]},gap,now))
  self.assertIsNone(publish_stall_evidence({'recent_slow':[dict(operation='uart_read',start_s=180.,end_s=181.727088782,duration_s=1.727)]},gap,now))

 def test_real_runtime_recovers_a_measured_publish_pause_with_existing_stop_and_probe(self):
  from . import offline_harness as harness
  from .integration import hooks,consent
  from .test_auto_release import ProbePlant
  from .pipeline_timing import PipelineTiming
  from .restart import take_restart
  def selected(*a,**kw):return hooks(*a,**{**kw,'trial_consent':consent((1,2,4)),'auto_contacts':True,'resume_after_normal':True,'isolate_tof':True,'accepted_coordination':True,'id2_contact_recovery':True})
  def scenario(w):
   m=w.motor;a=m.bus.central_feedback.brake_capture
   if w.clock()-w.start>2 and not getattr(w,'injected',False):
    w.injected=True;a.pipeline_timing=PipelineTiming(w.clock);original=m._publish
    def delayed(ms):
     original(ms)
     if not getattr(w,'delayed_once',False):w.delayed_once=True;w.clock.advance(.65)
    m._publish=lambda ms:a.pipeline_timing.call('_publish',delayed,ms)
   if take_restart(m,255):w.resumed=True;m.stopping.set()
  with tempfile.TemporaryDirectory()as folder,patch.object(harness,'Plant',ProbePlant),patch.object(harness,'hooks',selected):
   r,w=harness.run(Path(folder),scenario,seconds=25,enabled_ids=())
  self.assertTrue(w.delayed_once);self.assertTrue(getattr(w,'resumed',False),(r['phase'],r['error']))
  self.assertIsNone(r['error']);self.assertTrue(r['cleanup_confirmed'])
  events=[e['event']for e in r['events']]
  for name in ('RECOVERABLE_SCHEDULING_GAP_ACCEPTED','MODELS_RESET','HOLD_SENT','AUTO_RELEASE_LOCAL_PROGRESS','AUTO_PLAY_RESUME_READY'):self.assertIn(name,events)
  self.assertEqual(r['reset']['h'],0.)


if __name__=='__main__':unittest.main()
