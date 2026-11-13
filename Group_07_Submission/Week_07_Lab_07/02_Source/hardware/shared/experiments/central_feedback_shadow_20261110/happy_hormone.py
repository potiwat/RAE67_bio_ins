"""Hormone-dependent Happy. 2s candidate is software-only until tracking review."""
from bio_inspire.runtime.presentation_tempo import PresentationRhythms
from bio_inspire.runtime.state_rhythms import StateRhythms
import math

# Software calibration: unchanged Happy decoder / alpha1.1 / dt.05 /
# time_scale3.402/3.8; measured logical period ~2.8000s at this phi.
PHI_LOW=.11798049926757813
def happy_phi(h):
 if type(h)not in(int,float)or not math.isfinite(h)or not 0<=h<=1:raise ValueError('Expected real bounded H')
 return PHI_LOW+(.13-PHI_LOW)*h

class HormonePresentationRhythms(PresentationRhythms):
 def __init__(self,*args,experimental_high_h_period_s=2.5,**kwargs):
  super().__init__(*args,**kwargs)
  if self.presentation_target_period_s!=2.5:raise ValueError('Expected accepted2.5s source profile')
  if experimental_high_h_period_s not in (2.,2.2,2.5):raise ValueError('Unreviewed reference period')
  self.happy.phase_divisor*=experimental_high_h_period_s/2.5
  self.presentation_target_period_s=experimental_high_h_period_s
 def step(self,m,now):
  # Retain genuine S/H and phase; set only next Happy interval. Other states
  # retain their original .10+.03H mapping. No motor profile changes.
  StateRhythms.step(self,m,now)
  if self.mode=='happy':
   status=self.happy.rhythm.modulation_status.get('state_ahm',{})
   if status.get('applied')is True:
    phi=happy_phi(status['h']);self.happy.rhythm.set_ahm_phi(phi)
    self.happy.rhythm.modulation_status['state_ahm']={**status,'phi_next':phi,'mapping':'experimental_happy_H_band_28_to_25_reference'}
   self.happy.rhythm.modulation_status.update(presentation_tempo_override=False,experimental_happy_hormone=True,experimental_low_h_target_period_s=2.8,experimental_high_h_target_period_s=self.presentation_target_period_s)

def install():
 from bio_inspire.runtime import presentation_tempo
 presentation_tempo.PresentationRhythms=HormonePresentationRhythms
