"""Explicit real-motor free-path sequence; no obstacle-detection claim."""
import json,time,sys,os,signal,threading,hashlib,argparse
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch

def main():
 from .state_matrix_inputs import STATES,StateDrive
 p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');p.add_argument('--axis',type=int,choices=(1,2,4),required=True);p.add_argument('--stop-state',choices=STATES,default='normal');p.add_argument('--from-state',choices=STATES);p.add_argument('--entry-stop',action='store_true');p.add_argument('--return-stop',action='store_true');p.add_argument('--play-soak',action='store_true');p.add_argument('--cycles',type=int,choices=(1,3),default=1);p.add_argument('--output',required=True);args=p.parse_args()
 if not args.execute:raise RuntimeError('Explicit authorized free-path execution required')
 root=Path(__file__).resolve().parents[3];os.chdir(root);here=Path(__file__).parent
 sys.path[:0]=[str(root),str(root/'shared/runtime'),str(root/'bio_inspire/runtime')]
 from physical_button import BufferedInput
 import physical_button,physical_touch,physical_distance
 from .auto_recovery import atomic,mode2_source
 from .integration import hooks,consent
 from .restart import take_restart,start_after_button
 from bio_inspire.runtime.camera_motor import CameraMotor
 sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();manifest=json.loads((here/'manifest.json').read_text())
 for group in('protected_sha256','own_sha256','dependency_sha256'):
  assert all(sha(root/n)==v for n,v in manifest[group].items()),'Staged source changed '+group
 out=Path(args.output);out.mkdir(parents=True,exist_ok=False);abort=threading.Event()
 signal.signal(signal.SIGTERM,lambda *a:abort.set());signal.signal(signal.SIGINT,lambda *a:abort.set())
 cancelled=lambda:abort.is_set()or(out/'ABORT').exists()
 axes=(args.axis,)if args.cycles==1 else(1,2,4);cycle=0
 report=dict(status='STARTING',evidence='REAL_MOTORS_OPEN_PATH_SCRIPTED_CENTERED_CAMERA_AND_INPUTS',contact_tested=False,axis=args.axis,cycle_axes=axes,completed_axes=[],stop_state=args.stop_state,operator_R_sent=False,post_safety_button_presses=0,pid_tuning=False,events=[])
 class Input(BufferedInput):
  def close(self):self.discard_pending()
 inputs={};sessions=[];m=None;error=None;phase='READY';started=time.monotonic();stable=None;last_save=0.;seq=0;completed=False;play_since=None;drive=StateDrive();return_stop_sent=False;return_seen=None
 from bio_inspire.runtime.angry_fsm import AngryFSM
 original_step=AngryFSM.step
 def diagnostic_step(fsm,now,candidates,**kw):return original_step(fsm,now,drive.filter(now,candidates),**kw)
 def factory(name,debounce):
  x=Input(debounce);now=time.clock_gettime(time.CLOCK_BOOTTIME);x.sample(False,now-1);x.sample(False,now-.5);inputs[name]=x;return x
 def create(*a,**kw):
  if cancelled():raise RuntimeError('Free-path test cancelled before startup')
  return CameraMotor(*a,**kw)
 try:
  with ExitStack()as stack:
   stack.enter_context(patch.object(physical_distance,'PhysicalDistance',mode2_source(physical_distance.PhysicalDistance)))
   sessions=stack.enter_context(hooks(root,out/'sessions',json.loads((here/'config.json').read_text()),time.monotonic,trial_consent=consent((1,2,4)),startup_cancelled=cancelled,isolate_tof=True,effort_stop=True,id2_contact_recovery=True,id2_effort_stop=True,resume_after_normal=True,auto_contacts=True,id4_effort_stop=True))
   stack.enter_context(patch.object(physical_button,'PhysicalButton',lambda d:factory('button',d)))
   stack.enter_context(patch.object(physical_touch,'PhysicalTouch',lambda d:factory('touch',d)))
   stack.enter_context(patch.object(AngryFSM,'step',diagnostic_step))
   try:
    m=create(here/'profile.json',operator_start=True)
    while time.monotonic()-started<75*args.cycles and not completed:
     if cancelled():raise RuntimeError('Free-path test cancelled')
     now=m.now();seq+=1;m.poll()
     m.apply(dict(observation=dict(status='TRACKING',box=(.35,.2,.3,.5),error_xy=(0.,0.),captured_s=now,processed_s=now,source_id=seq),intent=dict(mode='FOLLOW',error_xy=(0.,0.))))
     elapsed=0. if play_since is None else time.monotonic()-play_since
     scripted_button=args.play_soak and phase=='READY'and any(start<=elapsed<start+.18 for start in(3.,9.,15.))
     for name,x in inputs.items():x.sample((name=='touch'and phase in('STATE','PRESTATE')and drive.request is not None and drive.request[0]=='happy')or(name=='button'and scripted_button),now)
     view=m.snapshot_view();s=view.get('trial_safety',{});a=m.bus.central_feedback.brake_capture
     if m.fault_message()or s.get('phase')=='LATCHED':raise RuntimeError('Free-path fault: '+str(s.get('error')or m.fault_message()))
     if phase in('READY','STATE','PRESTATE','RESUMED')and s.get('phase')not in(None,'PLAY'):
      raise RuntimeError('Uncommanded free-path safety stop: '+str(a.core.event))
     if phase in('READY','RESUMED'):
      okay=(s.get('phase')=='PLAY'and view.get('state')in('READY','FOLLOWING')and view.get('behavior')=='normal'and s.get('led',{}).get('requested_brightness',0)>=.03)
      if not okay:stable=None
      elif stable is None:
       stable=time.monotonic()
       if phase=='READY'and play_since is None:play_since=stable
      elif time.monotonic()-stable>=.5:
       if args.play_soak and phase=='READY'and time.monotonic()-play_since<20.:
        time.sleep(.02);continue
       if phase=='READY':
        if args.stop_state!='normal' or args.from_state:
         phase='PRESTATE'if args.from_state else'STATE';drive.select(args.from_state or args.stop_state);stable=None
        else:
         a.core.record('OPEN_PATH_INJECTED_TEST_STOP',axis=axes[cycle],physical_contact=False)
         a.next_event=dict(kind='test_stop',axis=axes[cycle]);m.key(ord('v'));phase='RECOVERING';stable=None
       else:
        report['completed_axes'].append(axes[cycle]);cycle+=1
        if cycle==len(axes):completed=True
        else:phase='READY';stable=None
     elif phase in('STATE','PRESTATE'):
      target=drive.request[0];behavior=view.get('behavior','')
      entered=(behavior==target or behavior==target+'_transition' or target=='interested'and behavior=='button_look')
      entry_mode=args.entry_stop or phase=='PRESTATE'
      ready=entered if entry_mode else behavior==target and m.automatic_fsm.timer_ready(m)
      if target=='afraid'and not entry_mode:ready=ready and getattr(m.controller.pose_route,'progress',0.)>=1.
      if target=='sleepy':
       fold=getattr(m.controller,'sleepy_native_fold',None)
       if not entry_mode and fold is not None:ready=ready and fold.get('phase')=='breathing'
       if phase=='PRESTATE':ready=ready and fold is not None and fold.get('phase')=='folding'
      if not ready:stable=None
      elif stable is None:stable=time.monotonic()
      elif time.monotonic()-stable>=(.25 if entry_mode else 6. if target=='happy' else .4):
       if phase=='PRESTATE':
        report['events'].append(dict(event='ABRUPT_FSM_CHANGE',source=target,target=args.stop_state,behavior=behavior,time_s=time.monotonic()));drive.select(args.stop_state);phase='STATE';stable=None
       else:
        a.core.record('OPEN_PATH_INJECTED_TEST_STOP',axis=axes[cycle],physical_contact=False,state=target,entry_stop=args.entry_stop)
        drive.clear();a.next_event=dict(kind='test_stop',axis=axes[cycle]);m.key(ord('v'));phase='RECOVERING';stable=None
     elif phase=='RECOVERING':
      if args.return_stop and not return_stop_sent and s.get('phase')=='RETURNING':
       if return_seen is None:return_seen=time.monotonic()
       elif time.monotonic()-return_seen>=.25:
        a.core.record('OPEN_PATH_INJECTED_RETURN_STOP',axis=axes[cycle],physical_contact=False);a.next_event=dict(kind='resistance',axis=axes[cycle]);m.key(ord('v'));return_stop_sent=True
      if return_stop_sent and a.core.hold_epoch>=2:report['return_stop_verified']=True
      if s.get('phase')in('STOPPING','WAIT_CLEARANCE','RETURNING')and m.led_ring is not None:raise RuntimeError('LED remained active during recovery')
      if take_restart(m,255):
       report['events'].append(dict(event='AUTOMATIC_NORMAL_HANDOFF',time_s=time.monotonic()))
       m=start_after_button(m,here/'profile.json',create,True);phase='RESUMED';stable=None
     if time.monotonic()-last_save>=.2:
      report.update(status='RUNNING',stage=phase,motor=m.snapshot_view());atomic(out/'PROGRESS.json',report);last_save=time.monotonic()
     time.sleep(.02)
    if not completed:raise RuntimeError('Free-path automatic sequence deadline')
    if args.return_stop and not report.get('return_stop_verified'):raise RuntimeError('Return interruption was not accepted by supervisor')
    report.update(status='PASS',motor=m.snapshot_view())
   finally:
    if m is not None:
     m.key(ord('h'))
     try:m.close()
     except BaseException as e:error=repr(e)
 except BaseException as e:report.update(status='FAIL',error=repr(e),stage=phase)
 if error:report.update(status='FAIL',cleanup_error=error)
 report.update(cleanup_confirmed=m is not None and m.cleanup_confirmed,sessions=[str(s.recorder.out)for s in sessions],protected_unchanged=all(sha(root/n)==v for n,v in manifest['protected_sha256'].items()))
 report['pid_unchanged']=bool(sessions)and all(json.loads((s.recorder.out/'summary.json').read_text()).get('pid_unchanged')is True for s in sessions)
 summaries=[json.loads((s.recorder.out/'summary.json').read_text())for s in sessions]
 report['caps_restored']=bool(summaries)and all(int.from_bytes(bytes.fromhex(v)[15:17],'little')==1000 for s in summaries for v in s.get('native_after',{}).values())
 logs=[json.loads((s.recorder.out/'ASYNC_LOGGING.json').read_text())for s in sessions]
 report['logging_valid']=bool(logs)and all(v['evidence_valid']and v['queued']==v['completed']and v['pending']==0 and not v['writer_alive']for v in logs)
 if not all(report[k]for k in('cleanup_confirmed','protected_unchanged','pid_unchanged','caps_restored','logging_valid')):report['status']='FAIL'
 atomic(out/'RESULT.json',report);print(json.dumps({k:report.get(k)for k in('status','error','stage','cleanup_confirmed','pid_unchanged','protected_unchanged')}),flush=True)
 return 0 if report['status']=='PASS'else 1

if __name__=='__main__':raise SystemExit(main())
