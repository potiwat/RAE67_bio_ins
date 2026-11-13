"""Explicit, supervised clear-path lab. Never used by the Desktop launcher."""
import argparse,json,time,math,threading,signal,os,sys,hashlib
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch


def shadow_adapter(base):
 class Observer(base):
  def observe(self,row,decision):
   # Only resistance authority is suppressed. Data-gap/native/Stop handling
   # sees the original decision and follows the original runtime path.
   enabled=self.enabled_ids
   self.enabled_ids=set()
   try:return super().observe(row,decision)
   finally:self.enabled_ids=enabled
 return Observer


def main():
 p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');p.add_argument('--observer-effort',action='store_true');p.add_argument('--phase-sweep',action='store_true');p.add_argument('--output',required=True);args=p.parse_args()
 if not(args.execute and args.observer_effort):raise RuntimeError('Explicit separate observer-lab authorization required')
 root=Path(__file__).resolve().parents[3];os.chdir(root);sys.path[:0]=[str(root),str(root/'shared/runtime'),str(root/'bio_inspire/runtime')]
 here=Path(__file__).parent;out=Path(args.output);out.mkdir(parents=True,exist_ok=False)
 from . import integration
 from .auto_recovery import atomic,mode2_source
 from .state_matrix_inputs import StateDrive
 from .present_safety_start import existing_owners
 assert not existing_owners(),existing_owners()
 manifest=json.loads((here/'manifest.json').read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
 for group in('protected_sha256','own_sha256','dependency_sha256'):assert all(sha(root/n)==v for n,v in manifest[group].items()),group
 from bio_inspire.runtime.camera_motor import CameraMotor
 from bio_inspire.runtime.angry_fsm import AngryFSM
 from physical_button import BufferedInput
 import physical_button,physical_touch,physical_distance
 original_factory=integration.adapter_class;original_step=AngryFSM.step;drive=StateDrive();abort=threading.Event();sessions=[];m=None;inputs={}
 signal.signal(signal.SIGTERM,lambda *a:abort.set());signal.signal(signal.SIGINT,lambda *a:abort.set())
 cancelled=lambda:abort.is_set()or(out/'ABORT').exists()
 class Input(BufferedInput):
  def close(self):self.discard_pending()
 def factory(name,debounce):
  x=Input(debounce);now=time.clock_gettime(time.CLOCK_BOOTTIME);x.sample(False,now-1);x.sample(False,now-.5);inputs[name]=x;return x
 def adapter(*a,**kw):return shadow_adapter(original_factory(*a,**kw))
 def step(fsm,now,candidates,**kw):return original_step(fsm,now,drive.filter(now,candidates),**kw)
 stages=[('normal',5),('happy',12),('angry',6),('normal',6),('happy',12),('angry',6),('normal',6)]
 if args.phase_sweep:
  stages=[('normal',5)]+[stage for dwell in (1,2,3,4,5,6)for stage in [('happy',dwell),('angry',6),('normal',6)]]
 report=dict(status='RUNNING',scope='USER_AUTHORIZED_CLEAR_PATH_NO_OBSTRUCTION_OBSERVER_ONLY',contact_stop_enabled=False,native_faults_limits_feedback_and_emergency_retained=True,stages=[],events=[]);error=None
 try:
  with ExitStack()as stack:
   stack.enter_context(patch.object(integration,'adapter_class',adapter))
   stack.enter_context(patch.object(physical_distance,'PhysicalDistance',mode2_source(physical_distance.PhysicalDistance)))
   sessions=stack.enter_context(integration.hooks(root,out/'sessions',json.loads((here/'config.json').read_text()),time.monotonic,trial_consent=integration.consent((1,2,4)),startup_cancelled=cancelled,isolate_tof=True,effort_stop=True,id2_contact_recovery=True,id2_effort_stop=True,resume_after_normal=True,auto_contacts=True,id4_effort_stop=True))
   stack.enter_context(patch.object(physical_button,'PhysicalButton',lambda d:factory('button',d)))
   stack.enter_context(patch.object(physical_touch,'PhysicalTouch',lambda d:factory('touch',d)))
   stack.enter_context(patch.object(AngryFSM,'step',step))
   try:
    m=CameraMotor(here/'profile.json',operator_start=True);started=time.monotonic();index=-1;stage_start=None;last_save=0;seq=0
    while True:
     if cancelled():raise RuntimeError('Lab cancelled')
     now=m.now();seq+=1;m.poll();view=m.snapshot_view()
     if m.fault_message()or view.get('trial_safety',{}).get('phase')not in(None,'PLAY'):raise RuntimeError('Lab native/data fault: '+str(m.fault_message()or view.get('trial_safety')))
     if index<0:
      if view.get('state')not in('READY','FOLLOWING'):time.sleep(.02);continue
      index=0;stage_start=time.monotonic();drive.select(stages[0][0])
     elapsed=time.monotonic()-stage_start
     if elapsed>=stages[index][1]:
      report['stages'].append(dict(request=stages[index][0],duration_s=elapsed))
      index+=1
      if index==len(stages):break
      stage_start=time.monotonic();drive.select(stages[index][0]);elapsed=0
     role=stages[index][0]
     for name,x in inputs.items():x.sample(name=='touch'and role=='happy',now)
     # Existing bounded gaze controller owns the actual motor limits.
     ex=.18*math.sin((time.monotonic()-started)*.8);ey=.10*math.sin((time.monotonic()-started)*.55)
     m.apply(dict(observation=dict(status='TRACKING',box=(.35,.2,.3,.5),error_xy=(ex,ey),captured_s=now,processed_s=now,source_id=seq),intent=dict(mode='FOLLOW',error_xy=(ex,ey))))
     if time.monotonic()-last_save>=1:
      report.update(stage=role,motor=view);atomic(out/'PROGRESS.json',report);last_save=time.monotonic()
     if time.monotonic()-started>(120 if args.phase_sweep else 70):raise RuntimeError('Lab time limit')
     time.sleep(.02)
    report.update(status='PASS',motor=m.snapshot_view())
   finally:
    if m is not None:m.key(ord('h'));m.close()
 except BaseException as e:report.update(status='FAIL',error=repr(e))
 report.update(cleanup_confirmed=m is not None and m.cleanup_confirmed,sessions=[str(s.recorder.out)for s in sessions],protected_unchanged=all(sha(root/n)==v for n,v in manifest['protected_sha256'].items()))
 summaries=[json.loads((s.recorder.out/'summary.json').read_text())for s in sessions]
 report['pid_unchanged']=bool(summaries)and all(s['pid_unchanged']for s in summaries)
 if not all(report[k]for k in('cleanup_confirmed','protected_unchanged','pid_unchanged')):report['status']='FAIL'
 atomic(out/'RESULT.json',report);print(json.dumps({k:report.get(k)for k in('status','error','sessions','cleanup_confirmed','protected_unchanged','pid_unchanged')}),flush=True)

if __name__=='__main__':main()
