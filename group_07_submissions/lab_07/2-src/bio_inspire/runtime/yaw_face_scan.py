"""Opt-in missing-player yaw scan in the existing motor owner; no devices."""
import math
from bounded_motion import BoundedMotion,MotionLimits


def validate(config):
    flag=config.get('yaw_face_scan_enabled',False)
    if type(flag)is not bool or flag and (config.get('fast_awake_trial') is not True
            or config.get('native_posture_compensation') is not True
            or config.get('gaze_enabled') is not True or config.get('yaw_range_deg')!=30):
        raise ValueError('Yaw acquisition scan needs approved awake/gaze30deg profile')
    return flag


def _stop(m,reason,hold=False):
    scan=getattr(m,'yaw_face_scan',None)
    if scan is not None:
        if hold:
            c=m.controller
            c.bus.hold_actual(1)
            c.last_goal=int.from_bytes(c.bus.read(1,42,2),'little')
        m.yaw_face_scan=None;m.visual.position=None
    m.yaw_scan_handoff=None
    m.yaw_scan_missing_since=None
    m.yaw_scan_status=dict(active=False,reason=reason)


def service(m,result,now):
    c=m.controller;route=getattr(c,'pose_route',None)
    mode=getattr(m,'behavior_trial','normal');phase=getattr(route,'phase',None)
    allowed_mode=mode=='normal'
    blocked=(getattr(m,'yaw_face_scan_enabled',False) is not True or not allowed_mode
             or not getattr(m,'gaze_enabled',True) or not getattr(m,'yaw_follow_enabled',True)
             or not getattr(m,'follow_enabled',False) or getattr(m,'head_probe_active',False)
             or getattr(m,'joint_mode',False) or getattr(m,'operator_stopped',False)
             or c.state not in ('READY','FOLLOWING') or m.stopping.is_set() or m.urgent_stop.is_set()
             or phase in ('look','return','tilt') or getattr(route,'safety_hold',False)
             or phase=='lean' and not getattr(route,'head_tracking_active',False))
    if blocked:
        _stop(m,'owner_or_stop');return False
    obs=(result or {}).get('observation') or {};intent=(result or {}).get('intent') or {}
    stamp=obs.get('captured_s');xy=intent.get('error_xy')
    fresh=(type(now) in (int,float) and math.isfinite(now)
           and type(stamp) in (int,float) and math.isfinite(stamp) and 0<=now-stamp<=.5)
    visible=(fresh and obs.get('status') in ('ACQUIRED','TRACKING') and intent.get('mode')=='FOLLOW'
             and isinstance(xy,(tuple,list)) and len(xy)==2
             and all(type(v) in (int,float) and math.isfinite(v) and -1<=v<=1 for v in xy))
    handoff=getattr(m,'yaw_scan_handoff',None)
    if handoff is not None:
        if not visible:
            _stop(m,'face_handoff_lost');return True
        if stamp>handoff['stopped_s'] and (not handoff['frames'] or stamp>handoff['frames'][-1]):
            handoff['frames'].append(stamp)
        ready=(len(handoff['frames'])>=2 and handoff['frames'][-1]-handoff['frames'][0]>=.1-1e-9)
        m.visual.reset(max(m.visual.low,min(m.visual.high,c.last_goal)),now)
        m.yaw_scan_status=dict(active=False,reason='face_handoff_ready' if ready else 'face_braking')
        if not ready:return True
        m.yaw_scan_handoff=None
        m.yaw_scan_serial=getattr(m,'yaw_scan_serial',0)+1
        m.yaw_scan_found=dict(serial=m.yaw_scan_serial,time_s=now,captured_s=stamp)
        actual=next(r['position_raw'] for r in c.last_rows if r['id']==1)
        m.visual.reset(max(m.visual.low,min(m.visual.high,actual)),now)
        return False
    if visible:
        was_scanning=getattr(m,'yaw_face_scan',None) is not None
        _stop(m,'face_found',hold=was_scanning)
        if was_scanning:
            stopped=max(now,m.now())
            m.yaw_scan_handoff=dict(stopped_s=stopped,frames=[])
            m.visual.reset(max(m.visual.low,min(m.visual.high,c.last_goal)),now)
            return True  # Do not overwrite the measured hold with this pre-stop image.
        return False
    missing=fresh and obs.get('status') in ('LOST','WAITING') and intent.get('mode')=='SEARCH'
    if not missing:
        _stop(m,'unusable_frame',hold=getattr(m,'yaw_face_scan',None) is not None);return False
    last=getattr(m,'last_tracking_seen_s',None)
    had_face=type(last) in (int,float) and math.isfinite(last) and 0<=now-last
    since=getattr(m,'yaw_scan_missing_since',None)
    if since is None:m.yaw_scan_missing_since=since=now
    if had_face and now-last<=.5:
        m.yaw_scan_status=dict(active=False,reason='recent_exit');return False
    # Time spent in another behavior never counts toward Normal acquisition.
    elapsed=now-max(last,since) if had_face else now-since
    if elapsed<1.:
        m.yaw_scan_status=dict(active=False,reason='confirm_missing');return False
    v=m.visual;scan=getattr(m,'yaw_face_scan',None)
    limits=MotionLimits(v.low,v.high,v.max_speed,v.max_acceleration,v.max_dt)
    if scan is None or now-scan['motion'].time>v.max_dt:
        actual=next(r['position_raw'] for r in c.last_rows if r['id']==1)
        actual=max(v.low,min(v.high,actual))
        target=v.low if actual>=(v.low+v.high)/2 else v.high
        scan=m.yaw_face_scan=dict(motion=BoundedMotion(actual,now,limits),target=target,turns=0)
    motion=scan['motion'];motion.limits=limits
    if abs(motion.position-scan['target'])<=1. and abs(motion.velocity)<1.:
        scan['target']=v.high if scan['target']==v.low else v.low;scan['turns']+=1
    goal=round(motion.step(scan['target'],now))
    if m.stopping.is_set() or m.urgent_stop.is_set():_stop(m,'cancelled');return True
    c.goal_yaw(goal);m.held=False
    m.yaw_scan_status=dict(active=True,reason='no_history' if not had_face else 'exit_memory_expired',
                           target_raw=scan['target'],command_raw=goal,turns=scan['turns'],
                           velocity_ticks_s=motion.velocity,bounds_raw=[v.low,v.high])
    return True
