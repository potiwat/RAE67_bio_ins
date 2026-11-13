"""Pure advisory detector: no serial imports, actuator, state writes or callbacks."""
from collections import deque
import math

def percentile(values,p):
 x=sorted(values);k=(len(x)-1)*p;a=int(k);return x[a]+(x[min(a+1,len(x)-1)]-x[a])*(k-a)

def fit_config(rows):
 config=dict(schema_version=1,mode='offline_shadow',actuation_enabled=False,physically_validated=False,maximum_gap_s=.20,stall_window_s=.30,minimum_samples=4,position_span_ticks=2,formula='ceil(P99 + max(P75-P25, 1)) per ID and signal',ids={})
 for sid in range(1,6):
  x=[r for r in rows if r['id']==sid and r.get('controller_state')in ('READY','FOLLOWING') and r.get('complete_feedback') is True and not r.get('mode') and r.get('torque_raw')==1 and not r.get('status_raw') and not r.get('operator_stopped')]
  if len(x)<30:raise ValueError('Insufficient fit data for ID'+str(sid))
  def bound(values):return math.ceil(percentile(values,.99)+max(percentile(values,.75)-percentile(values,.25),1.))
  config['ids'][str(sid)]=dict(fit_samples=len(x),current_limit_raw=bound([r['current_raw']for r in x]),pwm_limit_raw=bound([abs(r['load_signed_raw'])for r in x]),internal_error_limit_ticks=bound([abs(r['internal_target_raw']-r['position_raw'])for r in x]),reference_position_min_ticks=min(r['position_raw']for r in x),reference_position_max_ticks=max(r['position_raw']for r in x),reference_speed_max_raw=max(abs(r['speed_signed_raw'])for r in x))
 return config

class CentralDetector:
 def __init__(self,config):
  if config.get('actuation_enabled') is not False or config.get('mode')!='offline_shadow':raise ValueError('This module cannot enable actuation')
  if set(config['ids'])!=set(map(str,range(1,6))):raise ValueError('Explicit ID1-5 configuration required')
  self.config=config;self.history={i:deque()for i in range(1,6)};self.last={};self.sign={}
 def reset(self):
  self.last.clear();self.sign.clear()
  for h in self.history.values():h.clear()
 def update(self,row):
  sid=row.get('id');t=row.get('time_s');base=dict(id=sid,time_s=t,decision='MONITOR',reason='',outside_reference=False,shadow_only=True)
  def result(decision,reason):
   if sid in self.history:self.history[sid].clear()
   return dict(base,decision=decision,reason=reason)
  if type(sid)is not int or sid not in self.history:return result('WOULD_HOLD_DATA','invalid ID')
  if type(t)not in (int,float) or not math.isfinite(t):return result('WOULD_HOLD_DATA','invalid timestamp')
  previous=self.last.get(sid)
  if previous is not None and t<=previous:return result('WOULD_HOLD_DATA','non-increasing timestamp')
  self.last[sid]=t
  if row.get('controller_state')in ('INIT','NORMAL_STARTUP'):return result('UNARMED_STARTUP','startup not qualified in this detector')
  if previous is not None and t-previous>self.config['maximum_gap_s']:
   return dict(result('WOULD_HOLD_DATA','feedback gap'),gap_s=t-previous,gap_start_s=previous+self.config['maximum_gap_s'],gap_end_s=t)
  if row.get('controller_state')not in ('READY','FOLLOWING') or row.get('operator_stopped'):return result('WOULD_HOLD_DATA','controller not ready or operator stop')
  if row.get('complete_feedback')is not True:return result('WOULD_HOLD_DATA','incomplete native feedback')
  if row.get('mode')!=0 or row.get('torque_raw')!=1 or row.get('status_raw')!=0:return result('WOULD_HOLD_DATA','native mode/torque/status fault')
  for key,maximum in (('position_raw',4095),('goal_raw',4095),('internal_target_raw',4095),('current_raw',65535),('load_raw',2047),('speed_raw',65535)):
   if type(row.get(key))is not int or not 0<=row[key]<=maximum:return result('WOULD_HOLD_DATA','invalid '+key)
  q=row['position_raw'];error=row['internal_target_raw']-q;duty=row['load_raw']&1023;current=row['current_raw'];speed=row['speed_raw']&32767;p=self.config['ids'][str(sid)]
  base['outside_reference']=not p['reference_position_min_ticks']<=q<=p['reference_position_max_ticks'] or speed>p['reference_speed_max_raw']
  base.update(current_raw=current,pwm_magnitude_raw=duty,internal_error_ticks=error)
  suspect=current>p['current_limit_raw'] and duty>p['pwm_limit_raw'] and abs(error)>p['internal_error_limit_ticks']
  h=self.history[sid]
  if not suspect:h.clear();return base
  direction=1 if error>0 else -1
  if self.sign.get(sid)!=direction:h.clear()
  self.sign[sid]=direction;h.append((t,q))
  while len(h)>1 and t-h[1][0]>=self.config['stall_window_s']:h.popleft()
  duration=t-h[0][0];span=max(v for _,v in h)-min(v for _,v in h)
  if len(h)>=self.config['minimum_samples'] and duration>=self.config['stall_window_s']-1e-9 and span<=self.config['position_span_ticks']:
   return dict(base,decision='WOULD_STOP_RESISTANCE',reason='sustained excess current + PWM + internal error + little encoder progress',evidence_duration_s=duration,encoder_span_ticks=span)
  return base
