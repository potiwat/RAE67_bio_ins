"""Optional group extension; the original five-state Lab policy stays default."""
from collections import deque
import math
from bio_inspire.runtime.lab_fsm import LabFSM,transition


class TouchBurst:
    def __init__(self):self.times=deque(maxlen=3);self.last=None
    def clear(self):self.times.clear();self.last=None
    def press(self,stamp,now):
        if (type(stamp) not in (int,float) or not math.isfinite(stamp)
                or not 0<=now-stamp<=2. or self.last is not None and stamp<=self.last):return False
        self.last=stamp
        while self.times and stamp-self.times[0]>2.:self.times.popleft()
        self.times.append(stamp)
        if len(self.times)<3:return False
        self.times.clear();return True


def angry_transition(state,event):
    if event in ('fault','near','clear'):return transition(state,event)
    if state=='afraid':return None
    if state=='angry':return 'normal' if event=='timeout' else None
    if event=='touch_burst':return 'angry'
    return transition(state,event)


class AngryFSM(LabFSM):
    priority={k:n for n,k in enumerate(('fault','near','clear','touch_burst','touch','button','approach','timeout','idle'))}
    active_states=('interested','happy','angry')
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.near_active=False
    def policy(self,state,event):
        if state=='angry' and event=='timeout':return 'afraid' if self.near_active else 'normal'
        return angry_transition(state,event)
    def step(self,now,candidates,*,ready=True,held=False):
        if any(e['kind']=='near' for e in candidates):self.near_active=True
        elif any(e['kind']=='clear' for e in candidates):self.near_active=False
        if self.state=='angry':
            # Distance is remembered, not an immediate emotion interruption.
            # At timeout go directly to Afraid if still near, without a Normal hop.
            candidates=[e for e in candidates if e['kind'] in ('fault','timeout')]
            held=False
        return super().step(now,candidates,ready=ready,held=held)
