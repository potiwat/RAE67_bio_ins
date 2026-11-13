"""Supervised six-state experiment. Initial five base releases start Normal."""
import os,sys,json,hashlib,time
from pathlib import Path
from contextlib import contextmanager,ExitStack
from unittest.mock import patch
from .restart import with_restart_gate,take_restart,start_after_button
from .initial_start import InitialButtonStart,with_initial_gate

def selected_contact_ids(argv,manifest):
 from .integration import contact_ids
 staged=contact_ids(manifest['enabled_ids'])
 if '--contact-ids'not in argv:return staged
 index=argv.index('--contact-ids')
 if index+1>=len(argv):raise ValueError('Missing contact ID list')
 requested=contact_ids(tuple(int(i)for i in argv[index+1].split(',')))
 if requested!=staged:raise ValueError('Contact IDs differ from staged consent; restage explicitly')
 return requested

def viewer_arguments(preview,profile):
 return [str(preview),'--live','--simple-ui','--max-age-s','.5','--fps','30','--roll-compensation','--normal-profile',str(profile),'--diagnostic-snapshot']

@contextmanager
def runtime_surfaces(root,output,config,clock,dark=False,mode2=False,isolate_tof=False,effort_stop=False,auto_id1_return=False,contact_ids=(1,2,3,4,5),id2_contact_recovery=False,id2_effort_stop=False,auto_contacts=False,id4_effort_stop=False,accepted_coordination=False):
 from .integration import hooks,consent
 from .auto_recovery import DarkLed,mode2_source
 import physical_distance,led_ring
 with ExitStack()as stack:
  if mode2:stack.enter_context(patch.object(physical_distance,'PhysicalDistance',mode2_source(physical_distance.PhysicalDistance)))
  if isolate_tof:
   from .range_conditioning import conditioned_source,read_stimulus
   from bio_inspire.runtime import normal_ahm
   stack.enter_context(patch.object(physical_distance,'PhysicalDistance',conditioned_source(physical_distance.PhysicalDistance)))
   stack.enter_context(patch.object(normal_ahm,'read_stimulus',read_stimulus))
  sessions=stack.enter_context(hooks(root,output,config,clock,trial_consent=consent(contact_ids),isolate_tof=isolate_tof,effort_stop=effort_stop,auto_id1_return=auto_id1_return,id2_contact_recovery=id2_contact_recovery,id2_effort_stop=id2_effort_stop,resume_after_normal=True,auto_contacts=auto_contacts,id4_effort_stop=id4_effort_stop,accepted_coordination=accepted_coordination))
  if dark:stack.enter_context(patch.object(led_ring,'LedRing',DarkLed))
  yield sessions

@contextmanager
def view(dark=False,mode2=False,isolate_tof=False,auto_id1_return=False,initial_gate=None,auto_contacts=False):
 import play_view
 original=play_view.draw
 original_status=play_view.status_text
 def status(motor,start_error=''):
  if motor is None and initial_gate is not None:
   if initial_gate.error:return initial_gate.error
   return 'Starting Normal'if initial_gate.claimed else 'Base button '+str(initial_gate.count)+'/5 to start Normal'
  state={}if motor is None else motor.snapshot_view().get('trial_safety',{})
  phase=state.get('phase')
  if state.get('auto_probe',{}).get('active'):return 'Checking joint '+str(state['auto_probe'].get('id',1))+' movement - keep hands clear'
  if phase=='WAIT_CLEARANCE'and auto_contacts:return 'Waiting for supported bounded release check'
  labels={'STOPPING':'STOPPING - verifying hold and native target','WAIT_CLEARANCE':'WAIT_CLEARANCE - clear path, then R','RETURNING':'Returning to initial Normal','NORMAL_PARKED':'Normal reset complete - resuming play','LATCHED':'Safety fault - see reason below'}
  return labels.get(phase)or original_status(motor,start_error)
 def draw(cv,image,result,motor=None,start_error=''):
  out=original(cv,image,result,motor,start_error)
  state={}if motor is None else motor.snapshot_view().get('trial_safety',{})
  phase=state.get('phase','WAIT_START')
  message={'WAIT_START':'Start/M: Normal | V: planned stop | Q: close','PLAY':'All 6 states | LED CPG 3-8% | V: test stop','STOPPING':'STOPPING: verifying support and target - wait','WAIT_CLEARANCE':'WAIT_CLEARANCE: clear path, then press R','RETURNING':'Returning to initial Normal - H/Stop available','NORMAL_PARKED':'NORMAL RESET COMPLETE | Button releases '+str(state.get('restart_count',0))+'/5 to play','LATCHED':'STOPPED: inspect lamp; R cannot clear this fault'}.get(phase,phase)
  if phase=='WAIT_START'and initial_gate is not None:
   message=initial_gate.error or ('Base button '+str(initial_gate.count)+'/5 to start Normal | Q: close')
  if phase=='NORMAL_PARKED':message='NORMAL RESET COMPLETE | resuming play automatically'
  if phase=='WAIT_CLEARANCE'and auto_contacts:message='Automatic bounded release check | remove obstruction | H/Stop available'
  if phase=='PLAY'and dark:message='All 6 states | LED OUTPUT OFF | V: test stop'
  if state.get('auto_probe',{}).get('active'):message='AUTO ID'+str(state['auto_probe'].get('id',1))+': '+state['auto_probe']['phase']+' | H/Stop: pause | Q: close'
  if phase=='WAIT_CLEARANCE'and state.get('clearance_wait'):message='R recorded - waiting for stable hold; H/Stop available'
  lines=['Contact detection IDs: '+','.join(map(str,state.get('enabled_ids',()))),'EXPERIMENT - '+('ID1 AUTO RETURN / OTHERS MANUAL'if auto_id1_return else'ID1-5 / MANUAL R')+' / NOT QUALIFIED',('ToF mode 2 | 'if mode2 else'ToF mode 1 | ')+('LED OUTPUT OFF'if dark else'LED CPG 3-8%'),message]
  if auto_contacts:lines[1]='EXPERIMENT - ID1/2/4 AUTO RECOVERY / NOT QUALIFIED'
  if state.get('tof_quality')=='recent_clear_grace':lines.append('ToF: optical quality low - bounded 0.5s recent-clear grace')
  if isolate_tof:lines.append('ToF isolated: unavailable range cannot certify clearance')
  if str(state.get('tof_quality','')).startswith('unavailable_'):lines.append('ToF UNAVAILABLE | range protection unavailable | R confirms path')
  if state.get('contact_held'):lines.append('CONTACT HELD: ID1 deflected | remove obstruction before R')
  if state.get('error'):lines.append(str(state['error']))
  out=cv.copyMakeBorder(out,0,20*len(lines)+8,0,0,cv.BORDER_CONSTANT,value=(35,35,35))
  for n,line in enumerate(lines):
   while len(line)>12 and cv.getTextSize(line,cv.FONT_HERSHEY_SIMPLEX,.34,1)[0][0]>out.shape[1]-16:line=line[:-4]+'...'
   cv.putText(out,line,(8,out.shape[0]-20*len(lines)+n*20),cv.FONT_HERSHEY_SIMPLEX,.34,(225,240,235),1)
  return out
 with patch.object(play_view,'draw',draw),patch.object(play_view,'status_text',status):yield

def main():
 root=Path(__file__).resolve().parents[3];os.chdir(root);here=Path(__file__).parent
 sys.path[:0]=[str(root),str(root/'bio_inspire/runtime'),str(root/'shared/runtime')]
 check='--check'in sys.argv
 dark='--dark'in sys.argv;mode2='--tof-mode2-trial'in sys.argv
 isolate_tof='--isolate-tof'in sys.argv
 effort_stop='--id1-effort-trial'in sys.argv
 auto_id1_return='--auto-id1-return'in sys.argv
 id2_contact_recovery='--id2-contact-recovery'in sys.argv
 id2_effort_stop='--id2-effort-trial'in sys.argv
 id4_effort_stop='--id4-effort-trial'in sys.argv
 auto_contacts='--auto-contact-recovery'in sys.argv
 if not check and('--experimental-contact'not in sys.argv or not(auto_contacts or'--manual-r-clearance'in sys.argv)):raise RuntimeError('Explicit unqualified trial and clearance-mode flags required')
 m=json.loads((here/'manifest.json').read_text())
 selected_ids=selected_contact_ids(sys.argv,m)
 for group in('protected_sha256','own_sha256','dependency_sha256'):
  for n,h in m[group].items():
   if hashlib.sha256((root/n).read_bytes()).hexdigest()!=h:raise RuntimeError('Source changed; inspect before launching: '+n)
 config=json.loads((here/'config.json').read_text());preview=root/'shared/runtime/camera_preview.py'
 source=preview.read_text(encoding='utf-8-sig');anchor="'Lamp Bio - Normal / face centering'"
 if source.count(anchor)!=1:raise RuntimeError('Camera title anchor changed')
 title='EXPERIMENT - Safety / ToF'+('2'if mode2 else'1')+(' / LED OFF'if dark else' / LED ON')
 source=source.replace(anchor,repr(title))
 source=with_initial_gate(with_restart_gate(source))
 if dark and not check:
  from led_ring import blackout_idle
  blackout_idle()
 with runtime_surfaces(root,root/'shared/hardware/presentation_safety_play_20261110',config,time.monotonic,dark=dark,mode2=mode2,isolate_tof=isolate_tof,effort_stop=effort_stop,auto_id1_return=auto_id1_return,contact_ids=selected_ids,id2_contact_recovery=id2_contact_recovery,id2_effort_stop=id2_effort_stop,auto_contacts=auto_contacts,id4_effort_stop=id4_effort_stop,accepted_coordination='--accepted-coordination'in sys.argv):
  if check:print('SIX_STATE_TRIAL_CHECK_OK_NO_DEVICE_ACCESS');return
  initial_gate=InitialButtonStart().open()
  try:
   with view(dark=dark,mode2=mode2,isolate_tof=isolate_tof,auto_id1_return=auto_id1_return,initial_gate=initial_gate,auto_contacts=auto_contacts):
    sys.argv=viewer_arguments(preview,here/'profile.json')
    exec(compile(source,str(preview),'exec'),dict(__name__='__main__',__file__=str(preview),trial_initial_gate=initial_gate,trial_take_restart=take_restart,trial_start_after_button=start_after_button))
  finally:initial_gate.close()
 for n,h in m['protected_sha256'].items():
  if hashlib.sha256((root/n).read_bytes()).hexdigest()!=h:raise RuntimeError('Protected original changed during trial: '+n)

if __name__=='__main__':main()
