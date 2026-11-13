"""Process-local CPG LED phase binding, no oscillator or motor mutations."""
import inspect,textwrap,math,sys

def phase_for(m,state):
 router=getattr(m,'rhythm_driver',None)
 driver=getattr(router,'happy' if state=='happy'else 'afraid' if state=='afraid'else 'breathing',None)
 if driver is None and state=='afraid':driver=getattr(m,'afraid_rhythm_driver',None)
 if driver is None:driver=router
 rhythm=getattr(driver,'rhythm',None);phase=getattr(rhythm,'decoder_phase_cycles',getattr(rhythm,'phase_cycles',None))
 divisor=getattr(driver,'phase_divisor',1.) if state=='happy'else 1.
 if type(phase)not in(int,float)or not math.isfinite(phase)or type(divisor)not in(int,float)or not math.isfinite(divisor)or divisor<=0:return None,'missing CPG phase: steady minimum'
 return phase/divisor,'happy decoder phase/divisor'if state=='happy'else 'active '+state+' CPG decoder phase'

def build_service(original):
 source=textwrap.dedent(inspect.getsource(original))
 old='    brightness=.05+.03*.5*(1+math.cos(2*math.pi*(now-m.presentation_led_origin_s)/5.))'
 if source.count(old)!=1 or source.count('period_s=5.')!=1:raise RuntimeError('LED source changed; inspect before patching')
 source=source.replace(old,'    phase,phase_source=_phase_for(m,state)\n    brightness=.05 if phase is None else .05+.03*.5*(1+math.cos(2*math.pi*phase))')
 source=source.replace('period_s=5.','period_s=None,phase_cycles=phase,phase_source=phase_source')
 scope=dict(original.__globals__,_phase_for=phase_for);exec(compile(source,__file__,'exec'),scope);return scope['service_breathing']

def install():
 from bio_inspire.runtime import presentation_led as mod
 service=build_service(mod.service_breathing);mod.service_breathing=service
 alias=sys.modules.get('presentation_led')
 if alias is not None:alias.service_breathing=service
