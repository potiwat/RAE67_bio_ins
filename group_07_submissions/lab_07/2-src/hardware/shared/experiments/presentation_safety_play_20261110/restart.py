"""Post-Normal five-release gate; no UART or automatic fault recovery."""
def verify_parked_retirement(adapter,rows):
 """Retain existing active Normal holds; never rebase a loaded-axis goal."""
 a=adapter;m=a.m;c=m.controller
 if (not a.restart_claimed or a.core.phase not in('NORMAL_PARKED','CLOSED')or
     a.core.error or a.core.pending is not None or {r['id']for r in rows}!=set(range(1,6))):
  raise RuntimeError('Parked retirement state not verified')
 goals=getattr(a,'restart_hold_goals',{})
 if set(goals)!=set(range(1,6)):raise RuntimeError('Missing parked hold goals')
 proof={}
 for r in rows:
  i=r['id'];t=c.normal_tolerances[i]
  if (r['mode']!=0 or r['torque_raw']!=1 or r['status_raw']or r['speed_raw']or r['moving_raw']or
      r['goal_raw']!=goals[i]or abs(r['internal_target_raw']-r['goal_raw'])>2 or
      abs(r['goal_raw']-c.normal[i])>t or abs(r['position_raw']-c.normal[i])>t):
   raise RuntimeError('Parked retirement native hold changed ID'+str(i))
  writer=getattr(a,'stop_writer',None)
  if i==1 and writer is not None and writer.audit.get('id1_contact_deflection'):
   if abs(r['position_raw']-r['goal_raw'])>12 or(r['load_raw']&1023)>=32 or r['current_raw']>=3:
    raise RuntimeError('Parked retirement ID1 contact not released')
  proof[str(i)]={k:r[k]for k in('position_raw','goal_raw','internal_target_raw')}
 release=getattr(a,'contact_release_verified',None)
 if callable(release)and not release(rows,parked=True):raise RuntimeError('Fresh parked support effort/release unconfirmed')
 return proof

class ButtonRestartGate:
 def __init__(self,diagnostics):
  self.sequence=diagnostics['stable_sequence'];self.count=0;self.pressed=False
 @property
 def ready(self):return self.count==5
 def update(self,diagnostics):
  if diagnostics.get('sampler_error'):raise RuntimeError('Restart button sampler: '+diagnostics['sampler_error'])
  for edge in diagnostics['stable_edges']:
   seq=edge['sequence']
   if seq<=self.sequence:continue
   if seq!=self.sequence+1:raise RuntimeError('Restart button edge history incomplete')
   self.sequence=seq
   if self.ready:continue
   if edge['pressed']:self.pressed=True
   elif self.pressed:self.count+=1;self.pressed=False
  return self.ready

def take_restart(motor,key):
 """GUI consumes owner-published permission, then retires the old UART owner."""
 if motor is None or key!=255:return False
 with motor.lock:
  if motor.stopping.is_set()or motor.urgent_stop.is_set():return False
  a=motor.bus.central_feedback.brake_capture
  view=motor._view.get('trial_safety',{})
  token=a.restart_request
  if (a.restart_claimed or token is None or tuple(view.get('restart_token')or())!=token or
      a.core.phase!='NORMAL_PARKED'or a.core.error or a.core.pending is not None):return False
  a.restart_request=None;a.restart_claimed=True
  return True

def with_restart_gate(source):
 """Inject at the GUI key boundary; Q/ESC/H and window-close take priority."""
 anchor="                if behavior_panel is not None:key=behavior_panel.take(key)"
 if source.count(anchor)!=1:raise RuntimeError('Preview key boundary changed')
 source=source.replace(anchor,anchor+"\n                trial_button_restart = cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) >= 1 and trial_take_restart(motor,key)\n                if trial_button_restart:key=ord('m')")
 start="motor=operator_motor_start(motor,args.normal_profile,CameraMotor);motor_error=''"
 if source.count(start)!=1:raise RuntimeError('Preview motor handoff changed')
 return source.replace(start,"motor=trial_start_after_button(motor,args.normal_profile,CameraMotor,trial_button_restart);motor_error=''")

def start_after_button(motor,profile,factory,automatic=False):
 if not automatic:
  from camera_preview import operator_motor_start
  return operator_motor_start(motor,profile,factory)
 a=motor.bus.central_feedback.brake_capture
 def healthy_handoff():
  return (a.restart_claimed and a.core.phase in ('NORMAL_PARKED','CLOSED')and
          not a.core.error and a.core.pending is None and not motor.urgent_stop.is_set()and
          motor.controller.state!='FAULT'and not motor.fault_message()and
          not getattr(motor.bus,'unsafe_damping_axes',())and getattr(a,'id1_contact_released',lambda:True)())
 if not healthy_handoff()or motor.stopping.is_set():raise RuntimeError('Button restart blocked: intervening Stop/fault')
 a.retiring_parked_owner=True
 motor.disconnect_for_retry()
 # Explicit M may retry a fault. Automatic button handoff must never use
 # that permission: require the retired owner's confirmed hold/cleanup.
 if (not motor.cleanup_confirmed or not motor.finished.is_set()or
     (motor.watchdog is not None and motor.watchdog.is_alive())or not healthy_handoff()):
  raise RuntimeError('Button restart blocked: old owner hold/cleanup or safety unconfirmed')
 from .restart_settle import restart_scope
 with restart_scope(a.restart_hold_goals):
  return factory(profile,operator_start=True)
