"""Process-local experimental LED range. No motor/model or original edits."""
import inspect,textwrap,math,subprocess
from shared.experiments.central_feedback_shadow_20261110.cpg_led import phase_for
from led_ring import LedRing as OriginalLedRing

def blackout_output(m,state='normal_parked'):
 ring=m.led_ring;m.led_ring=None;m.last_led_behavior=None;m.presentation_led_last_frame=None
 m.presentation_led_output=dict(state=state,requested_brightness=0.,enabled=False,off_command_completed=False)
 try:
  if ring is not None:ring.close();m.presentation_led_output['off_command_completed']=True
 except(OSError,RuntimeError,ValueError,subprocess.SubprocessError)as error:
  m.presentation_led_output['error']=str(error);print('PARK_LED_OFF_FAILED',str(error),flush=True)

def build_driver(original=OriginalLedRing):
 source=textwrap.dedent(inspect.getsource(original.show_color))
 if source.count('not .05<=brightness<=.08')!=1:raise RuntimeError('Inspect changed LED driver validator')
 source=source.replace('not .05<=brightness<=.08','not .03<=brightness<=.08').replace('between5and8percent','between3and8percent')
 scope=dict(original.show_color.__globals__);exec(compile(source,__file__,'exec'),scope)
 return type('TrialLedRing',(original,),dict(show_color=scope['show_color'],__module__=__name__))

def build_service(original):
 source=textwrap.dedent(inspect.getsource(original))
 old='    brightness=.05+.03*.5*(1+math.cos(2*math.pi*(now-m.presentation_led_origin_s)/5.))'
 if source.count(old)!=1 or source.count('period_s=5.')!=1:raise RuntimeError('Inspect changed original LED source')
 source=source.replace(old,'    phase,phase_source=_phase_for(m,state)\n    brightness=.03 if phase is None else max(.03,min(.08,.03+.05*.5*(1+math.cos(2*math.pi*phase))))')
 source=source.replace('period_s=5.','period_s=None,phase_cycles=phase,phase_source=phase_source,brightness_floor=.03')
 if source.count('(OSError,RuntimeError,subprocess.SubprocessError)')!=2:raise RuntimeError('Inspect changed decorative LED exception guards')
 source=source.replace('(OSError,RuntimeError,subprocess.SubprocessError)','(OSError,RuntimeError,ValueError,subprocess.SubprocessError)')
 scope=dict(original.__globals__,_phase_for=phase_for);exec(compile(source,__file__,'exec'),scope)
 service=scope['service_breathing']
 def guarded(m,state,force=False):
  if getattr(m,'safety_recovery_led_off',False):
   if m.led_ring is not None:blackout_output(m,'safety_recovery')
   return
  timing=getattr(getattr(getattr(m.bus,'central_feedback',None),'brake_capture',None),'pipeline_timing',None)if hasattr(m,'bus')else None
  return service(m,state,force=force)if timing is None else timing.call('led_output',service,m,state,force=force)
 return guarded
