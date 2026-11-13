"""Bounded optical-quality grace during an operator-authorized return only.

Never invent distance, renew a clear timestamp with an ambiguous frame, use
stale input, or grant initial R clearance from degraded optical evidence.
"""
from physical_distance import distance_input_kind

class ReturnDistancePolicy:
 def __init__(self):self.last_clear_s=None
 def update(self,sample,now,returning):
  sample=sample or {};kind=distance_input_kind(sample,now)
  if sample.get('error')not in(None,'invalid measurement'):
   self.last_clear_s=None;state='hardware_fault';quality='hardware_fault'
  elif kind in('range','no_target'):
   state='clear'if kind=='no_target'or sample['distance_cm']>=28. else'near'
   self.last_clear_s=sample['received_s']if state=='clear'else None;quality=kind
  elif (kind=='unreliable'and returning and self.last_clear_s is not None and
        0<=now-self.last_clear_s<=.5):
   state='clear';quality='recent_clear_grace'
  else:
   state='unknown';quality=kind
   if kind!='unreliable':self.last_clear_s=None
  return dict(state=state,quality=quality,kind=kind,last_confirmed_clear_s=self.last_clear_s,
              grace_limit_s=.5,observed_s=now,sample=sample)
