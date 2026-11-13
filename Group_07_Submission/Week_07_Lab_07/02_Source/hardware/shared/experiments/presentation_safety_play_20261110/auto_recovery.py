"""Authorized open-path sequence check: real motors/ToF/LED, scripted inputs.

No camera/obstacle/contact claim. Same isolated owner, profiles and protections.
Requires --execute. No motion or device access on import or --check.
"""
import json,time,sys,os,signal,threading,hashlib,argparse,inspect,textwrap,math
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
from led_ring import LedRing as StateLedInterface

class DarkLed(StateLedInterface):
 """Keep logical LED calls observable without touching SPI/GPIO."""
 def show_color(self,color,brightness=None):
  if brightness is not None and not .03<=brightness<=.08:raise ValueError('Invalid logical LED level')
  self.last_frame=(color,brightness)
 def close(self):self.last_frame=None

def mode2_source(original,instances=None):
 """Process-local sensor mode comparison; restore short mode on close."""
 source=textwrap.dedent(inspect.getsource(original._run))
 if source.count('sensor.distance_mode=1')!=1 or source.count('if sensor is not None:sensor.stop_ranging()')!=1:raise RuntimeError('Inspect changed ToF worker')
 source=source.replace('sensor.distance_mode=1','sensor.distance_mode=2')
 source=source.replace('if sensor is not None:sensor.stop_ranging()','if sensor is not None:\n                sensor.stop_ranging();sensor.distance_mode=1\n                self.mode_trial_restored=True\n                print("TOF_MODE_TRIAL_RESTORED_SHORT_MODE",flush=True)')
 scope=dict(original._run.__globals__);exec(compile(source,__file__,'exec'),scope)
 def init(self,*args,**kwargs):
  self.mode_trial_restored=False
  if instances is not None:instances.append(self)
  original.__init__(self,*args,**kwargs)
 return type('Mode2TrialDistance',(original,),dict(__init__=init,_run=scope['_run']))

class RecoverySequence:
 def __init__(self,now,exercise_yaw=False,auto_id1_return=False,stop_state='happy',happy_dwell_s=1.5,contact_brake_axis=None):
  if stop_state not in('normal','happy'):raise ValueError('Reviewed sequence stop state must be Normal or Happy')
  if happy_dwell_s not in(1.5,6.):raise ValueError('Reviewed Happy dwell1.5or6s required')
  if contact_brake_axis is not None and(type(contact_brake_axis)is not int or contact_brake_axis not in(1,2,4)):raise ValueError('Reviewed contact brake axis1,2or4 only')
  self.contact_brake_axis=contact_brake_axis
  self.happy_dwell_s=happy_dwell_s;self.stop_state=stop_state;self.started=now;self.phase='NORMAL';self.entered=now;self.events=[];self.r_attempts=0;self.last_r=-1e9;self.stable=None;self.exercise_yaw=exercise_yaw;self.auto_id1_return=auto_id1_return
 def event(self,name,now,**data):self.events.append(dict(event=name,time_s=now,phase=self.phase,**data))
 def change(self,phase,now):self.phase=phase;self.entered=now;self.stable=None;self.event('PHASE',now)
 def tick(self,m,now):
  from physical_distance import distance_input_kind
  from .restart import take_restart
  view=m.snapshot_view();s=view.get('trial_safety',{});phase=s.get('phase');led=s.get('led',{})
  if m.stopping.is_set()or m.urgent_stop.is_set():raise RuntimeError('Sequence interrupted by Stop/close')
  if m.fault_message()or phase=='LATCHED':raise RuntimeError('Sequence motor/safety fault: '+str(s.get('error')or m.fault_message()))
  if led.get('disabled')or led.get('error'):raise RuntimeError('Sequence decorative output error: '+str(led))
  if now-self.started>75:raise RuntimeError('Sequence overall deadline')
  limits={'NORMAL':15,'HAPPY':10,'STOP':12,'RETURN':25,'BUTTONS':8,'RESUMED':15}
  if now-self.entered>limits.get(self.phase,75):raise RuntimeError('Sequence stage deadline: '+self.phase)
  out=dict(touch=False,button=False,restart=False,done=False)
  lit=led.get('requested_brightness',0)>=.03 and m.led_ring is not None
  dark=led.get('requested_brightness')==0 and led.get('enabled')is False and m.led_ring is None
  if self.phase in('NORMAL','RESUMED'):
   good=(phase=='PLAY'and view.get('state')in('READY','FOLLOWING')and view.get('behavior')=='normal'and lit)
   if not good:self.stable=None
   elif self.stable is None:self.stable=now
   elif now-self.stable>=(8. if self.exercise_yaw and self.phase=='NORMAL'else .5):
    self.event('NORMAL_LED_READY',now,restarted=self.phase=='RESUMED')
    if self.phase=='RESUMED':self.change('DONE',now);out['done']=True
    elif self.stop_state=='normal':
     if self.auto_id1_return:m.bus.central_feedback.brake_capture.next_event=dict(kind='test_stop',axis=1)
     if self.contact_brake_axis is not None:m.bus.central_feedback.brake_capture.next_event=dict(kind='resistance',axis=self.contact_brake_axis)
     m.key(ord('v'));self.event('V_REQUEST',now,stop_state='normal');self.change('STOP',now)
    else:self.change('HAPPY',now)
  elif self.phase=='HAPPY':
   out['touch']=True
   if view.get('behavior')=='happy'and lit:
    if self.stable is None:self.stable=now
    elif now-self.stable>=(6. if self.exercise_yaw else self.happy_dwell_s):
     if self.auto_id1_return:m.bus.central_feedback.brake_capture.next_event=dict(kind='test_stop',axis=1)
     if self.contact_brake_axis is not None:m.bus.central_feedback.brake_capture.next_event=dict(kind='resistance',axis=self.contact_brake_axis)
     m.key(ord('v'));out['touch']=False;self.event('V_REQUEST',now);self.change('STOP',now)
   else:self.stable=None
  elif self.phase=='STOP':
   if phase=='WAIT_CLEARANCE':
    if not dark:raise RuntimeError('Stop reached clearance gate without LED blackout')
    reset=getattr(m.bus.central_feedback.brake_capture,'reset_snapshot',{})
    if reset.get('h')!=0 or any(v.get('updates')!=0 for v in reset.get('bank',{}).values()):raise RuntimeError('H/CPG reset not confirmed')
    self.change('RETURN',now)
  elif self.phase=='RETURN':
   if phase=='NORMAL_PARKED':
    if not dark:raise RuntimeError('Normal parked without LED blackout')
    self.event('NORMAL_PARK_LED_OFF',now);self.change('BUTTONS',now)
   elif not self.auto_id1_return and phase=='WAIT_CLEARANCE'and now-self.last_r>=1.:
    sample=m.physical_distance.latest();kind=distance_input_kind(sample,m.now())
    if kind=='no_target'or kind=='range'and sample['distance_cm']>=28.:
     m.key(ord('r'));self.r_attempts+=1;self.last_r=now;self.event('R_REQUEST',now,attempt=self.r_attempts)
  elif self.phase=='BUTTONS':
   elapsed=now-self.entered;cycle=int(elapsed/.36)
   out['button']=cycle<5 and elapsed-cycle*.36<.18
   if take_restart(m,255):
    if s.get('restart_count')!=5:raise RuntimeError('Restart token without five releases')
    self.event('FIVE_RELEASES_CONFIRMED',now);out['restart']=True;self.change('RESUMED',now)
  return out

def atomic(path,data):
 p=path.with_suffix('.tmp');p.write_text(json.dumps(data,indent=2));p.replace(path)

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');parser.add_argument('--check',action='store_true');parser.add_argument('--output');parser.add_argument('--dark',action='store_true');parser.add_argument('--tof-mode2-trial',action='store_true');parser.add_argument('--isolate-tof',action='store_true');parser.add_argument('--id1-effort-trial',action='store_true');parser.add_argument('--exercise-yaw',action='store_true');parser.add_argument('--auto-id1-return',action='store_true');parser.add_argument('--id2-effort-trial',action='store_true');parser.add_argument('--happy-dwell-s',type=float,choices=(1.5,6.),default=1.5);parser.add_argument('--id2-contact-recovery',action='store_true');parser.add_argument('--contact-ids');parser.add_argument('--contact-brake-axis',type=int,choices=(1,2,4));parser.add_argument('--stop-state',choices=('normal','happy'),default='happy');args=parser.parse_args()
 if args.check:print('AUTO_RECOVERY_CHECK_OK_NO_DEVICE_ACCESS');return 0
 if not args.execute:raise RuntimeError('Explicit --execute required for authorized open-path motion')
 root=Path(__file__).resolve().parents[3];os.chdir(root);here=Path(__file__).parent
 sys.path[:0]=[str(root),str(root/'bio_inspire/runtime'),str(root/'shared/runtime')]
 from .launch import selected_contact_ids
 manifest=json.loads((here/'manifest.json').read_text());selected_ids=selected_contact_ids(sys.argv,manifest);sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
 for group in('protected_sha256','own_sha256','dependency_sha256'):
  if not all(sha(root/n)==v for n,v in manifest[group].items()):raise RuntimeError('Manifest differs before automatic run')
 out=Path(args.output)if args.output else root/'shared/hardware/presentation_safety_play_20261110'/('auto_sequence_'+str(time.time_ns()))
 out.mkdir(parents=True,exist_ok=False)
 report=dict(evidence='PHYSICAL_OPEN_PATH_REAL_UART_ENCODER_TOF_LED_SCRIPTED_TOUCH_BUTTON_AND_CENTERED_CAMERA_INPUT',camera_tracking_tested=False,contact_tested=False,pid_tuning=False,status='STARTING',events=[])
 atomic(out/'PROGRESS.json',report)
 abort=threading.Event();signal.signal(signal.SIGTERM,lambda *a:abort.set());signal.signal(signal.SIGINT,lambda *a:abort.set())
 cancelled=lambda:abort.is_set()or(out/'ABORT').exists()
 from physical_button import BufferedInput
 import physical_button,physical_touch,physical_distance,led_ring
 from .integration import hooks,consent
 from .restart import start_after_button
 from bio_inspire.runtime.camera_motor import CameraMotor
 inputs={};m=None;sequence=None;sessions=[];close_error=None;tof_instances=[]
 report.update(injected_resistance_event_axis=args.contact_brake_axis,id2_effort_stop=args.id2_effort_trial,happy_dwell_s=args.happy_dwell_s,id2_contact_recovery=args.id2_contact_recovery,stop_state=args.stop_state,contact_detection_ids=list(selected_ids),feedback_ids=[1,2,3,4,5],supported_stop_ids=[1,2,3,4,5],led_hardware_enabled=not args.dark,led_checks='logical commands only'if args.dark else'real SPI command completion; not photometric measurement',tof_mode_trial=2 if args.tof_mode2_trial else 1)
 if args.dark:report['evidence']='PHYSICAL_OPEN_PATH_REAL_UART_ENCODER_TOF_SCRIPTED_INPUTS_LED_OUTPUT_DISABLED'
 class ScriptedInput(BufferedInput):
  def close(self):self.discard_pending()
 def factory(name,debounce):
  source=ScriptedInput(debounce);now=time.clock_gettime(time.CLOCK_BOOTTIME)
  source.sample(False,now-1);source.sample(False,now-.5);inputs[name]=source;return source
 def create_motor(*args,**kwargs):
  if cancelled():raise RuntimeError('Automatic run cancelled before motor start')
  return CameraMotor(*args,**kwargs)
 try:
  with ExitStack()as stack:
   if args.tof_mode2_trial:stack.enter_context(patch.object(physical_distance,'PhysicalDistance',mode2_source(physical_distance.PhysicalDistance,tof_instances)))
   sessions=stack.enter_context(hooks(root,out/'sessions',json.loads((here/'config.json').read_text()),time.monotonic,trial_consent=consent(selected_ids),startup_cancelled=cancelled,isolate_tof=args.isolate_tof,effort_stop=args.id1_effort_trial,auto_id1_return=args.auto_id1_return,id2_contact_recovery=args.id2_contact_recovery,id2_effort_stop=args.id2_effort_trial))
   stack.enter_context(patch.object(physical_button,'PhysicalButton',lambda d:factory('button',d)))
   stack.enter_context(patch.object(physical_touch,'PhysicalTouch',lambda d:factory('touch',d)))
   if args.dark:stack.enter_context(patch.object(led_ring,'LedRing',DarkLed))
   try:
    m=create_motor(here/'profile.json',operator_start=True);sequence=RecoverySequence(m.now(),exercise_yaw=args.exercise_yaw,auto_id1_return=args.auto_id1_return,stop_state=args.stop_state,happy_dwell_s=args.happy_dwell_s,contact_brake_axis=args.contact_brake_axis);frame=0;last_progress=0.
    while sequence.phase!='DONE':
     now=m.now()
     if cancelled():raise RuntimeError('Automatic run aborted')
     frame+=1;m.poll()
     error_x=.20*math.sin(2*math.pi*(now-sequence.entered)/4.)if args.exercise_yaw and sequence.phase=='NORMAL'else 0.
     m.apply(dict(observation=dict(status='TRACKING',box=(.35+error_x,.2,.3,.5),error_xy=(error_x,0.),captured_s=now,processed_s=now,source_id=frame),intent=dict(mode='FOLLOW',error_xy=(error_x,0.))))
     action=sequence.tick(m,now)
     if cancelled():raise RuntimeError('Automatic run aborted before input/handoff')
     for name in('touch','button'):inputs[name].sample(action[name],now)
     if action['restart']:
      if cancelled():raise RuntimeError('Automatic run aborted before handoff')
      m=start_after_button(m,here/'profile.json',create_motor,True)
     if now-last_progress>=.5:
      report.update(status='RUNNING',stage=sequence.phase,events=sequence.events,motor=m.snapshot_view());atomic(out/'PROGRESS.json',report);last_progress=now
     time.sleep(.02)
    if cancelled():raise RuntimeError('Automatic run aborted before completion')
    report.update(status='PASS',stage=sequence.phase,events=sequence.events,motor=m.snapshot_view())
   finally:
    if m is not None:
     m.key(ord('h'))
     try:m.close()
     except Exception as error:close_error=repr(error)
 except Exception as error:report.update(status='FAIL',error=repr(error),events=[]if sequence is None else sequence.events,motor=None if m is None else m.snapshot_view())
 if close_error:report.update(status='FAIL',cleanup_error=close_error)
 report['sessions']=[str(s.recorder.out)for s in sessions]
 report['cleanup_confirmed']=m is not None and m.cleanup_confirmed
 report['protected_unchanged']=all(sha(root/n)==h for n,h in manifest['protected_sha256'].items())
 if not report['cleanup_confirmed']or not report['protected_unchanged']:report['status']='FAIL'
 report['pid_unchanged']=all(json.loads((s.recorder.out/'summary.json').read_text()).get('pid_unchanged')is True for s in sessions)
 if not report['pid_unchanged']:report['status']='FAIL'
 if args.tof_mode2_trial:
  report['tof_short_mode_restore_completed']=bool(tof_instances)and all(s.mode_trial_restored for s in tof_instances)
  if not report['tof_short_mode_restore_completed']:report['status']='FAIL'
 atomic(out/'RESULT.json',report);print('AUTO_RECOVERY_RESULT',json.dumps(dict(status=report['status'],output=str(out),error=report.get('error'),cleanup_confirmed=report['cleanup_confirmed'],pid_unchanged=report['pid_unchanged'])),flush=True)
 return 0 if report['status']=='PASS'else 1

if __name__=='__main__':raise SystemExit(main())
