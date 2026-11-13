"""Lab06/07 group policy and clocked arbitration, without hardware effects.

Policy source: references/bio_inspire/group07_student_policy.py.txt.
Timing/priority: references/bio_inspire/group07_config.json and Lab07 bridge.
"""
from collections import deque

STATES=('normal','interested','happy','afraid','sleepy')
PRIORITY={kind:n for n,kind in enumerate(('fault','near','clear','touch','button','approach','timeout','idle'))}

def transition(state,event):
    if event=='fault':return 'normal'
    if event=='near':return 'afraid'
    if event=='clear':return 'normal'
    if state=='afraid':return None
    if event=='touch':return 'happy'
    if event in ('button','approach'):return 'interested'
    if event=='timeout' and state in ('interested','happy'):return 'normal'
    if event=='idle' and state=='normal':return 'sleepy'
    return None

class LabFSM:
    priority=PRIORITY
    active_states=('interested','happy')
    policy=staticmethod(transition)
    def __init__(self,now,active_timeout_s=2.,motion_aware=False,sleep_after_s=6.,happy_timeout_s=None):
        if happy_timeout_s is not None and (type(happy_timeout_s) not in (int,float) or happy_timeout_s!=7.):raise ValueError('Unreviewed Happy timeout')
        self.happy_timeout_s=happy_timeout_s
        self.state='normal';self.entry=now;self.last_activity=now
        self.sleep_after_s=sleep_after_s;self.active_timeout_s=active_timeout_s;self.motion_aware=motion_aware
        self.clock_ready=False;self.active_since=now;self.idle_since=now
        self.events=deque(maxlen=180);self.serial=0;self.last_winner=None
    def step(self,now,candidates,*,ready=True,held=False):
        choices=[dict(q) for q in candidates]
        eligible=ready and not held
        if self.motion_aware:
            if not eligible or not self.clock_ready:self.active_since=now;self.idle_since=now
            self.clock_ready=eligible
        active=self.active_since if self.motion_aware else self.entry
        idle=self.idle_since if self.motion_aware else self.last_activity
        duration=self.happy_timeout_s if self.state=='happy' and self.happy_timeout_s is not None else self.active_timeout_s
        if (not self.motion_aware or eligible) and self.state in self.active_states and now-active>=duration-1e-9:
            choices.append(dict(kind='timeout',source_s=active+duration,source_id='internal_timeout'))
        if (not self.motion_aware or eligible) and self.state=='normal' and now-idle>=self.sleep_after_s-1e-9:
            choices.append(dict(kind='idle',source_s=idle+self.sleep_after_s,source_id='internal_idle'))
        if not choices:return None
        choices.sort(key=lambda q:self.priority[q['kind']]);winner=choices[0]
        old=self.state;target=self.policy(old,winner['kind'])
        if winner['kind'] in ('button','touch','approach','near','clear'):
            self.last_activity=now
            if self.motion_aware:self.active_since=now;self.idle_since=now
        changed=target is not None and target!=old
        if changed:
            self.state=target;self.entry=now
            if self.motion_aware:self.clock_ready=False
        for n,event in enumerate(choices):
            self.serial+=1
            event.update(event_id=f'fsm_{self.serial:06d}',recognized_s=now,old_state=old,new_state=self.state,
                         status='discarded_priority' if n else 'transition' if changed else 'no_state_change' if target==old else 'policy_held')
            self.events.append(event)
        self.last_winner=self.events[-len(choices)]
        return self.last_winner
