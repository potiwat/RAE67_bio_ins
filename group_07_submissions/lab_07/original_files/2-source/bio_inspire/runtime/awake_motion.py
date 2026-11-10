"""Opt-in awake RAM acceleration and visual limits, using the sole UART owner."""
from acceleration_restore import AccelerationRestore

ACC={1:3,2:8,3:8,4:12,5:6}
BASE_ACC={1:3,2:1,3:1,4:1,5:1}

def validate(config):
    flag=config.get('fast_awake_trial',False)
    if type(flag)is not bool or flag and (config.get('motion_speed_raw')!=600
            or config.get('automatic_fsm_enabled') is not True
            or config.get('native_posture_compensation') is not True):
        raise ValueError('Fast awake requires existing600 automatic compensated profile')
    gentle=config.get('interested_gentle_entry',False)
    if type(gentle)is not bool or gentle and (not flag
            or config.get('interest_native_body_speed_raw')!=600
            or config.get('interest_native_neck') is not True or config.get('interest_gaze_priority') is not True):
        raise ValueError('Gentle Interested requires reviewed fast native compensated entry')
    return flag

def _allowed(m):
    route=getattr(m.controller,'pose_route',None)
    angry_hold=(getattr(m,'behavior_trial',None) in ('angry','angry_transition')
                and getattr(route,'phase',None) in ('lean','complete')
                and getattr(route,'safety_hold',False))
    return (getattr(m,'fast_awake_trial',False) is True
            and m.controller.state in ('READY','FOLLOWING')
            and not getattr(m,'operator_stopped',False)
            and not m.stopping.is_set() and not m.urgent_stop.is_set()
            and not angry_hold)

class AwakeMotion:
    def __init__(self,m):
        self.saved=[];self.active=False
        for name in ('visual','pitch_visual'):
            v=getattr(m,name,None)
            if v is not None:self.saved.append((v,v.max_speed,v.max_acceleration))
    def ensure(self,m,role):
        c=m.controller;b=c.bus
        if not hasattr(b,'acceleration_restore'):b.acceleration_restore=AccelerationRestore()
        g=b.acceleration_restore
        wide=(role=='happy' and getattr(m,'happy_wide_caps_trial',False) is True)
        values={1:8,2:16,3:16,4:24,5:6} if wide else {**ACC,2:1,3:1} if role=='angry_approach' else ACC
        b.happy_wide_caps_trial=wide
        b.awake_dynamic_acceleration_trial=True
        try:
            for sid,value in values.items():
                if m.stopping.is_set() or m.urgent_stop.is_set():return
                same=sid in g.pinned and g.floor.get(sid)==value
                if same:continue
                if g.floor.get(sid,value)>value:
                    if sid in g.pinned or g.pending.get(sid)!=value:g.unpin(sid,value)
                    continue  # Keep braking until three actual stationary arrivals.
                g.pin(sid,value,c.normal_tolerances[sid])
                if b.read(sid,41,1)!=bytes((value,)):b.write(sid,41,bytes((value,)))
        finally:
            b.awake_dynamic_acceleration_trial=False
            b.happy_wide_caps_trial=False
        for name,acc in (('visual',3),('pitch_visual',6)):
            v=getattr(m,name,None)
            if v is not None:v.max_speed=800.;v.max_acceleration=acc*8.7*4096/360
        self.active=True
    def sleep(self,m):
        if not self.active:return
        g=getattr(m.controller.bus,'acceleration_restore',None)
        if g is not None:
            for sid,value in BASE_ACC.items():g.unpin(sid,value)
        for v,speed,acc in self.saved:v.max_speed=speed;v.max_acceleration=acc
        self.active=False

def prepare_awake(m,target=None):
    if not _allowed(m):return
    role=target or getattr(m,'behavior_trial','normal')
    if role.startswith('sleepy'):return
    route=getattr(m.controller,'pose_route',None)
    if (target is None and role in ('angry','angry_transition')
            and getattr(route,'phase',None) in ('lean','complete')
            and getattr(route,'completion_behavior',None)=='angry'
            and getattr(route,'range_phase',None) in ('acquire','advance','paused','tilt','complete')):
        role='angry_approach'
    policy=getattr(m,'awake_motion_policy',None)
    if policy is None:policy=m.awake_motion_policy=AwakeMotion(m)
    policy.ensure(m,role)

def prepare_sleep(m):
    policy=getattr(m,'awake_motion_policy',None)
    if policy is not None:policy.sleep(m)

def sleep_ready(m):
    g=getattr(m.controller.bus,'acceleration_restore',None)
    return g is None or not g.pending
