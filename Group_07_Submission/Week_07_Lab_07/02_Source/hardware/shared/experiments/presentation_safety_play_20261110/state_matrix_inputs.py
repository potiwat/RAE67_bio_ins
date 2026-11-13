"""Diagnostic FSM events only; no UART, sensor spoofing, or motion profiles."""
STATES=('normal','interested','happy','angry','afraid','sleepy')
class StateDrive:
 def __init__(self):self.request=None;self.seen=None;self.serial=0
 def select(self,state):
  if state not in STATES:raise ValueError('Unknown diagnostic state')
  self.serial+=1;self.request=(state,self.serial)
 def clear(self):self.request=None
 def filter(self,now,candidates):
  request=self.request
  if request is None:return candidates
  state,serial=request;events=list(candidates)
  # Logical Near drives the existing Afraid FSM route only. The real ToF
  # producer, native safety checks and Near veto are never changed.
  if state=='afraid':events=[e for e in events if e['kind']!='clear']
  if request!=self.seen or state=='afraid':
   kind=dict(normal='clear',interested='button',happy='touch',angry='touch_burst',afraid='near',sleepy='idle')[state]
   events.append(dict(kind=kind,source_s=now,source_id=f'diagnostic_{state}_{serial}'))
   self.seen=request
  return events
