"""Lab07 near20/clear28cm hysteresis; motor dispatch stays in UART owner."""
import math
from physical_distance import distance_input_kind


class DistanceGate:
    def __init__(self):self.near=False;self.last_confirmed_near_s=None
    def step(self,sample,now):
        cm=(sample or {}).get('distance_cm');stamp=(sample or {}).get('received_s')
        kind=distance_input_kind(sample,now)
        if kind=='fault':return 'fault'
        if kind=='unreliable':
            # Approved behavior timeout: an ambiguous completed frame must
            # not keep a prior proximity event latched indefinitely.
            if not self.near:return None
            if self.last_confirmed_near_s is None:self.last_confirmed_near_s=stamp
            if now-self.last_confirmed_near_s<.5-1e-9:return None
            self.near=False;self.last_confirmed_near_s=None;return 'clear'
        old=self.near;self.near=False if kind=='no_target' else cm<28. if old else cm<=20.
        self.last_confirmed_near_s=stamp if self.near else None
        return 'near' if self.near and not old else 'clear' if old and not self.near else None


def poll_distance(m,now,dispatch=True):
    source=getattr(m,'physical_distance',None)
    if source is None:return False
    c=m.controller;sample=source.latest()
    if c.state!='WAIT_TOF' and getattr(m,'distance_resume_startup',False):m.distance_resume_startup=False
    # Producer may publish between the caller's clock read and latest().
    # Observe time after the snapshot before testing receipt freshness.
    now=max(now,m.now())
    prior_near=m.distance_gate.near
    prior_confirmed=m.distance_gate.last_confirmed_near_s
    event=m.distance_gate.step(sample,now)
    m.distance_view=dict(sample or {},near=m.distance_gate.near,event=event)
    if c.state in ('FAULT','STOPPED') or getattr(m,'operator_stopped',False):return False
    if m.stopping.is_set() or m.urgent_stop.is_set():return True
    if event=='fault':
        m.distance_unreliable_recovery_since=None
        if c.state=='WAIT_TOF':return True
        startup_wait=(c.state=='NORMAL_STARTUP' and getattr(m,'presentation_startup_tof_recovery',False) is True)
        recoverable=c.state in ('READY','FOLLOWING') or startup_wait
        m._hold('ToF: waiting for a fresh valid distance',all_axes=True)
        m.follow_enabled=False
        if c.state=='FAULT':return True  # A failed motor hold is never recoverable here.
        if not recoverable:c.state='FAULT';return True
        m.distance_resume_startup=startup_wait
        m.behavior_trial='distance_wait'
        m.pending_behavior=None;m.pending_happy_from_touch=False
        m.interested_roll_due=None
        c.state='WAIT_TOF'
        return True
    if c.state=='WAIT_TOF':
        # Fresh data alone does not re-arm motors or overrule STOP. The
        # ordinary controller checks all five feedback/torque/status bounds.
        observed_near=m.distance_gate.near
        observed_confirmed=m.distance_gate.last_confirmed_near_s
        c.tick(now)
        if c.state!='WAIT_TOF':return True
        if m.stopping.is_set() or m.urgent_stop.is_set() or getattr(m,'operator_stopped',False):return True
        # UART feedback is blocking. Its completion must not authorize a
        # return from a distance snapshot that expired or changed meanwhile.
        sample=source.latest();now=max(now,m.now())
        # Preserve positive proximity evidence read before the blocking
        # feedback, while still requiring a current frame for recovery.
        m.distance_gate.near=prior_near or observed_near
        confirmations=[t for t in (prior_confirmed,observed_confirmed) if t is not None]
        m.distance_gate.last_confirmed_near_s=max(confirmations) if confirmations else None
        event=m.distance_gate.step(sample,now)
        m.distance_view=dict(sample or {},near=m.distance_gate.near,event=event)
        if event=='fault':
            m.distance_unreliable_recovery_since=None
            return True
        kind=distance_input_kind(sample,now)
        if kind=='unreliable' and event!='clear':
            # A one-frame stale gap can enter WAIT with no prior Near latch.
            # Fresh completed ambiguous frames then produced no Clear event,
            # leaving the controller in WAIT forever. Use the already approved
            # 0.5s unknown-quality release policy, without inventing a distance.
            since=getattr(m,'distance_unreliable_recovery_since',None)
            if since is None:m.distance_unreliable_recovery_since=now;return True
            if now-since<.5-1e-9 or m.distance_gate.near:return True
        else:m.distance_unreliable_recovery_since=None
        if not m.distance_gate.near and kind=='range' and sample['distance_cm']<28.:return True
        c.state='READY';c.last_error=''
        if not dispatch:return True
        if m.distance_gate.near:
            from bio_inspire.runtime.afraid_pose import enter_afraid
            enter_afraid(m)
        else:
            from bio_inspire.runtime.three_state_behavior import handle_state_key
            handle_state_key(m,ord('n'))
        m.distance_resume_startup=False
        return True
    if c.state not in ('READY','FOLLOWING'):return False
    if not dispatch:return m.distance_gate.near or event=='clear'
    if m.distance_gate.near:
        if getattr(m,'behavior_trial',None)!='afraid':
            from bio_inspire.runtime.afraid_pose import enter_afraid
            enter_afraid(m)
        return True
    if getattr(m,'behavior_trial',None)=='afraid':
        from bio_inspire.runtime.three_state_behavior import handle_state_key
        handle_state_key(m,ord('n'));return True
    return False
