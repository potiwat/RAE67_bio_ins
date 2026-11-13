"""Angry-only head-command experiment; arm commands and Safety are untouched."""
import math


def filtered_goal(state,source,target,now,tau=.10):
    if (type(source)is not int or type(target)is not int or
            type(now)not in(int,float)or not math.isfinite(now)):
        raise ValueError('Finite command clock and integer pitch goals required')
    if state is None:return dict(value=float(source),time_s=now),source
    dt=now-state['time_s']
    if dt<0 or not math.isfinite(dt):raise ValueError('Pitch command clock regressed')
    gain=-math.expm1(-min(dt,.1)/tau)
    value=state['value']+gain*(target-state['value'])
    return dict(value=value,time_s=now),round(value)


def goal_pitch(original):
    def pitch(c,goal):
        route=getattr(c,'pose_route',None)
        enabled=(getattr(route,'completion_behavior',None)=='angry'
                 and getattr(route,'heading_saved',False)
                 and getattr(route,'range_phase',None)in('advance','tilt','complete')
                 and not getattr(route,'safety_hold',False)
                 and not route._cancelled()
                 and c.state in('READY','FOLLOWING')and c.pitch_tracking_enabled)
        if not enabled:return original(c,goal)
        low,high=c.active_pitch_window();source=c.last_pitch_goal
        # Never let filtering conceal a rejected source command or invent a
        # new clamp. Existing controller guards own all pitch authorization.
        if type(goal)is not int or not low<=goal<=high:return original(c,goal)
        if type(source)is not int or not low<=source<=high:return original(c,goal)
        state,out=filtered_goal(getattr(route,'trial_head_filter',None),source,goal,route.m.now())
        result=original(c,out)
        if result:
            route.trial_head_filter=state
            recorder=getattr(getattr(c.bus,'central_feedback',None),'recorder',None)
            if recorder is not None:
                recorder.event('ANGRY_PITCH_FILTER',desired_goal=goal,sent_goal=out,
                               lag_ticks=goal-out,tau_s=.1,phase=route.range_phase)
        return result
    return pitch
