"""Pure evidence detector: excessive effort without requiring a full stall.

Consumes validated CentralDetector results. It grants no motion/stop authority
itself. An explicit isolated trial may route its evidence to the existing stop
supervisor. The original path uses configured thresholds; the experimental ID2 blocked
path uses shorter persistence. Force is not measured.
"""
from collections import deque
import math

class JointEffortEvidence:
 def __init__(self,config,sid):
  if type(sid)is not int or sid not in range(1,6)or str(sid)not in config['ids']:raise ValueError('Explicit configured motor ID required')
  self.sid=sid;self.config=config;self.history=deque();self.last=None
 def update(self,result):
  out=dict(candidate_stop=False,advisory_only=True,physically_validated=False)
  if result.get('id')!=self.sid:return out
  t=result.get('time_s')
  if type(t)not in(int,float)or not math.isfinite(t):self.history.clear();self.last=None;return out
  valid=result.get('decision')=='MONITOR'
  if self.last is not None and(not 0<t-self.last<=self.config['maximum_gap_s']):valid=False
  self.last=t
  keys=('current_raw','pwm_magnitude_raw','internal_error_ticks')
  if not valid or any(type(result.get(k))is not int for k in keys):self.history.clear();return out
  p=self.config['ids'][str(self.sid)];error=result['internal_error_ticks']
  suspect=(result['current_raw']>p['current_limit_raw']and result['pwm_magnitude_raw']>p['pwm_limit_raw']and abs(error)>p['internal_error_limit_ticks'])
  if not suspect:self.history.clear();return out
  sign=1 if error>0 else -1
  if self.history and self.history[-1][2]!=sign:self.history.clear()
  self.history.append((t,result.get('position_raw'),sign,error))
  window=self.config['stall_window_s']
  while len(self.history)>1 and t-self.history[1][0]>=window:self.history.popleft()
  duration=t-self.history[0][0]
  if len(self.history)>=self.config['minimum_samples']and duration>=window-1e-9:
   positions=[entry[1] for entry in self.history if type(entry[1])is int]
   out.update(candidate_stop=True,reason='sustained excess current + PWM + internal error despite encoder progress',duration_s=duration,encoder_span_ticks=max(positions)-min(positions)if positions else None,error_growth_ticks=abs(error)-abs(self.history[0][3]))
  return out

class ID1EffortEvidence(JointEffortEvidence):
 def __init__(self,config):super().__init__(config,1)

class ID4EffortEvidence:
 """Trial head-current evidence, independent of behavior labels.

 Keep the global-motion envelope as a conventional path. The extra path
 uses the SAME fitted current ceiling, with PWM/error presence checks;
 requiring all three global peaks masked the recorded gentle contact.
 These are native proxies, not a measured contact-force threshold.
 """
 def __init__(self,config):
  self.slow=JointEffortEvidence(config,4)
  sensitive={**config,'stall_window_s':.15,'minimum_samples':4,
             'ids':{**config['ids'],'4':{**config['ids']['4'],
                     'pwm_limit_raw':32,'internal_error_limit_ticks':8}}}
  self.current_supported=JointEffortEvidence(sensitive,4)
 def update(self,result):
  slow=self.slow.update(result);fast=self.current_supported.update(result)
  if fast['candidate_stop']:
   fast.update(path='id4_current_supported',reason='sustained head current above fitted free-motion ceiling with nontrivial PWM and tracking error')
   return fast
  return slow


class ID2EffortEvidence:
 """Experimental composite: retain moving-effort evidence, add blocked ramp.

 Fast evidence is a replay-derived candidate, not calibrated contact force or
 a guarantee that the supply will not sag. Native faults remain authoritative.
 """
 def __init__(self,config):
  self.config=config;self.slow=JointEffortEvidence(config,2);self.history=deque();self.last=None
  # Isolated replay-derived trial, deliberately independent of emotion labels.
  sensitive={**config,'stall_window_s':.15,'minimum_samples':4,'ids':{**config['ids'],'2':{**config['ids']['2'],'current_limit_raw':25,'pwm_limit_raw':240,'internal_error_limit_ticks':25}}}
  self.moving=JointEffortEvidence(sensitive,2)
 def update(self,result):
  slow=self.slow.update(result)
  moving=self.moving.update(result)
  if moving['candidate_stop']and moving['error_growth_ticks']>=6 and not slow['candidate_stop']:
   # Moderate, steady lag while the encoder follows a changing pose is not
   # itself obstruction. Require the same six-tick residual growth used by
   # the blocked-reference path. Strong conventional and context evidence
   # remain independent; no behavior-name exception or higher drive cap.
   slow={**moving,'path':'moving_sensitive','reason':'sustained moderate effort with growing tracking residual while motion may continue'}
  out=dict(candidate_stop=False,advisory_only=True,physically_validated=False)
  if result.get('id')!=2:return slow
  t=result.get('time_s')
  if type(t)not in(int,float)or not math.isfinite(t):self.history.clear();self.last=None;return slow
  valid=result.get('decision')=='MONITOR'
  if self.last is not None and not 0<t-self.last<=self.config['maximum_gap_s']:valid=False
  self.last=t
  keys=('position_raw','current_raw','pwm_magnitude_raw','internal_error_ticks')
  if not valid or any(type(result.get(k))is not int for k in keys):self.history.clear();return slow
  q=result['position_raw'];e=result['internal_error_ticks'];sign=1 if e>0 else -1
  if not(result['current_raw']>self.config['ids']['2']['current_limit_raw']and result['pwm_magnitude_raw']>250 and abs(e)>22):self.history.clear();return slow
  if self.history and self.history[-1][3]!=sign:self.history.clear()
  self.history.append((t,q,e,sign))
  while len(self.history)>1 and t-self.history[1][0]>=.1-1e-9:self.history.popleft()
  duration=t-self.history[0][0]
  span=max(x[1]for x in self.history)-min(x[1]for x in self.history)
  first=self.history[0];reference_progress=sign*((q+e)-(first[1]+first[2]));growth=abs(e)-abs(first[2])
  if len(self.history)>=3 and duration>=.1-1e-9 and span<=2 and reference_progress>=6 and growth>=6:
   out.update(candidate_stop=True,path='fast_blocked',reason='encoder blocked while internal reference and effort rise',duration_s=duration,encoder_span_ticks=span,reference_progress_ticks=reference_progress,error_growth_ticks=growth)
   return out
  return slow
