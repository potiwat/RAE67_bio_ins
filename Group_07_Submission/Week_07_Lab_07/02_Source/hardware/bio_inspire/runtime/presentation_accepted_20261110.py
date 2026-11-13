"""User-accepted presentation tempo/LED update. No Safety or hardware writes.

Process-local opt-in from the presentation entry point only. Original experiment
profiles and their default owners stay unchanged.
"""
import math,sys,subprocess
from bio_inspire.runtime.presentation_tempo import PresentationRhythms as Base
from bio_inspire.runtime.state_rhythms import StateRhythms
from bio_inspire.runtime.presentation_led import COLORS

PHI_LOW=.11798049926757813
def happy_phi(h):
 if type(h)not in(int,float)or not math.isfinite(h)or not 0<=h<=1:raise ValueError('Expected bounded real hormone')
 return PHI_LOW+(.13-PHI_LOW)*h

class AcceptedRhythms(Base):
 def __init__(self,*args,**kwargs):
  super().__init__(*args,**kwargs)
  if self.presentation_target_period_s!=2.5:raise ValueError('Accepted presentation requires 2.5s source decoder')
 def step(self,m,now):
  StateRhythms.step(self,m,now)
  if self.mode=='happy':
   status=self.happy.rhythm.modulation_status.get('state_ahm',{})
   if status.get('applied')is True:
    phi=happy_phi(status['h']);self.happy.rhythm.set_ahm_phi(phi)
    self.happy.rhythm.modulation_status['state_ahm']={**status,'phi_next':phi,'mapping':'accepted_happy_H_band_28_to_25_reference'}
   self.happy.rhythm.modulation_status.update(presentation_tempo_override=False,accepted_happy_hormone=True,low_h_target_period_s=2.8,high_h_target_period_s=2.5)

def phase_for(m,state):
 router=getattr(m,'rhythm_driver',None)
 driver=getattr(router,'happy'if state=='happy'else'afraid'if state=='afraid'else'breathing',None)
 if driver is None and state=='afraid':driver=getattr(m,'afraid_rhythm_driver',None)
 if driver is None:driver=router
 rhythm=getattr(driver,'rhythm',None);phase=getattr(rhythm,'decoder_phase_cycles',getattr(rhythm,'phase_cycles',None))
 divisor=getattr(driver,'phase_divisor',1.)if state=='happy'else 1.
 if type(phase)not in(int,float)or not math.isfinite(phase)or type(divisor)not in(int,float)or not math.isfinite(divisor)or divisor<=0:return None
 return phase/divisor

def service_breathing(m,state,force=False):
 if state not in COLORS or getattr(m,'presentation_led_disabled',False):return
 now=m.now()
 if not force and now-getattr(m,'presentation_led_last_s',-math.inf)<.1:return
 phase=phase_for(m,state);brightness=.05 if phase is None else .05+.03*.5*(1+math.cos(2*math.pi*phase));color=COLORS[state]
 try:
  if m.led_ring is None:
   from led_ring import LedRing
   m.led_ring=LedRing();force=True
  if force or (color,brightness)!=getattr(m,'presentation_led_last_frame',None):m.led_ring.show_color(color,brightness=brightness)
 except (OSError,RuntimeError,subprocess.SubprocessError)as e:
  m.presentation_led_disabled=True;m.presentation_led_output=dict(state=state,disabled=True,error=str(e),failed_s=now)
  ring=m.led_ring;m.led_ring=None
  try:
   if ring is not None:ring.close()
  except (OSError,RuntimeError,subprocess.SubprocessError)as cleanup:m.presentation_led_output['cleanup_error']=str(cleanup)
  return
 m.last_led_behavior=state;m.presentation_led_last_s=now;m.presentation_led_last_color=color;m.presentation_led_last_frame=(color,brightness)
 m.presentation_led_output=dict(state=state,rgb_255=color,period_s=None,phase_cycles=phase,phase_source='active CPG decoder',brightness_ceiling=.08,requested_brightness=brightness,actual_color_quantized=True)

def install():
 from bio_inspire.runtime import presentation_tempo,presentation_led
 presentation_tempo.PresentationRhythms=AcceptedRhythms
 presentation_led.service_breathing=service_breathing
 alias=sys.modules.get('presentation_led')
 if alias is not None:alias.service_breathing=service_breathing
