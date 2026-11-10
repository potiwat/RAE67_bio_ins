"""Measured-body orientation reference plus the existing visual correction.

Proposed orientation-only model, not calibrated FK/IK or face recognition.
Probe observations 20261102T131403Z establish opposite image-y effects for
ID2 and ID3. Equal STS encoder scales/parallel pitch axes motivate the unit
delta signs below; translation and wrist-roll residuals remain visual error.
"""
import math
from bio_inspire.runtime.taught_crouch_head import TaughtCrouchHead


class InterestedHead:
    def __init__(self,visual,rows,now,entry_pitch=None,native_posture=False):
        self.visual=visual;self.entry=self.positions(rows)
        if entry_pitch is not None and (type(entry_pitch)is not int or not visual.low<=entry_pitch<=visual.high):
            raise ValueError('Awake head reference must be inside reviewed gaze window')
        self.entry_pitch=max(visual.low,min(visual.high,self.entry[5])) if entry_pitch is None else entry_pitch
        self.model=TaughtCrouchHead(visual,self.entry_pitch,now,native_posture=native_posture)
        self.planned_reference=None;self.reference_bias_ticks=0.
    @staticmethod
    def positions(rows):
        values={r['id']:r['position_raw'] for r in rows if r.get('id') in (2,3,5)}
        if set(values)!={2,3,5} or any(type(q)is not int or not 0<=q<=4095 for q in values.values()):
            raise ValueError('Fresh body/head encoder rows required')
        return values
    def reference(self,rows):
        p=self.positions(rows)
        q=self.entry_pitch+(p[2]-self.entry[2])-(p[3]-self.entry[3])+self.reference_bias_ticks
        return max(self.visual.low,min(self.visual.high,q))
    def step(self,rows,error,now,measurement,body_target=None,reference_bias_ticks=0.):
        if (type(reference_bias_ticks) not in (int,float) or not math.isfinite(reference_bias_ticks)
                or not -57.<=reference_bias_ticks<=0.):raise ValueError('Head reference offset outside taught trial')
        self.reference_bias_ticks=float(reference_bias_ticks)
        reference=self.reference(rows);self.planned_reference=None
        if self.model.native_posture and body_target is not None:
            if any(type(body_target.get(i))is not int or not 0<=body_target[i]<=4095 for i in (2,3)):
                raise ValueError('Reviewed body position targets required')
            reference=self.entry_pitch+(body_target[2]-self.entry[2])-(body_target[3]-self.entry[3])+self.reference_bias_ticks
            reference=max(self.visual.low,min(self.visual.high,reference))
            self.planned_reference=reference
        return self.model.step(reference,error,now,measurement)
    def following_error(self,rows):
        # Include the new measured body pose while retaining the visual offset.
        desired=self.visual.position+self.reference(rows)-self.model.reference
        desired=max(self.visual.low,min(self.visual.high,desired))
        error=desired-self.positions(rows)[5]
        if (self.planned_reference is not None
                and error*(self.planned_reference-self.reference(rows))<0):
            return 0.  # Intentional head anticipation must not stall the catching-up body.
        return error
    def limit_feedback(self,goal):
        motion=self.model.motion;difference=goal-motion.position
        # Keep the absolute posture reference; clipping an actuator command
        # must not erase body compensation while the actuator catches up.
        if motion.velocity*difference<0:motion.velocity=0.
        if self.visual.velocity*difference<0:self.visual.velocity=0.
        motion.position=float(goal)


def active(m):
    route=getattr(m.controller,'pose_route',None)
    if (getattr(m,'native_posture_compensation',False) and getattr(m,'behavior_trial',None) in ('normal','happy')
            and not (getattr(m,'behavior_trial',None)=='happy' and getattr(m,'happy_head_wake_goal',None) is not None)):
        return True
    return (getattr(m,'interest_body_pitch_compensation',False)
            and getattr(m,'behavior_trial',None) in ('button_look','interested_transition','interested','angry_transition','angry')
            and getattr(route,'phase',None) in ('lean','complete','cancelled'))


def apply_gaze(m,result,now):
    """Head compensation continues on actual body motion, never fake vision."""
    if m.stopping.is_set() or m.urgent_stop.is_set() or getattr(m,'operator_stopped',False):return
    c=m.controller;obs=(result or {}).get('observation') or {};intent=(result or {}).get('intent') or {}
    route=getattr(c,'pose_route',None)
    if getattr(route,'safety_hold',False):return
    if getattr(route,'heading_saved',False) and getattr(route,'phase',None)=='lean':
        m.pitch_reacquire=False
        m._apply_pitch(dict(mode='HOLD',error_xy=None),obs,now,False)
        # Yaw is deliberately suspended here. Reacquire from fresh encoder
        # feedback on resumption, rather than integrating the entire pause.
        m.visual.position=None
        return  # Remembered aim plus body compensation; no live face chasing.
    if getattr(m,'behavior_trial',None)=='happy' and getattr(m,'happy_dance_only',False) is True:
        m.pitch_reacquire=False
        m._apply_pitch(dict(mode='HOLD',error_xy=None),obs,now,False)
        return  # Keep deterministic body/head compensation, discard visual gaze only.
    xy=intent.get('error_xy');stamp=obs.get('captured_s')
    visible=(obs.get('status') in ('TRACKING','ACQUIRED') and intent.get('mode')=='FOLLOW'
             and type(stamp) in (int,float) and math.isfinite(stamp) and 0<=now-stamp<=.5
             and isinstance(xy,(tuple,list)) and len(xy)==2
             and all(type(v) in (int,float) and math.isfinite(v) and -1<=v<=1 for v in xy))
    m.pitch_reacquire=m._face_exit_memory(obs,intent,now,visible)
    m._apply_pitch(intent,obs,now,visible)
    if c.state not in ('READY','FOLLOWING') or m.stopping.is_set() or m.urgent_stop.is_set():return
    if getattr(m,'behavior_trial',None)=='happy':return  # Happy decoder alone owns yaw.
    if not getattr(m,'yaw_follow_enabled',True):return
    if m.visual.position is None:
        if not visible:return
        actual=next(r['position_raw'] for r in c.last_rows if r['id']==1)
        m.visual.reset(max(m.visual.low,min(m.visual.high,actual)),now)
    error=c.direction*160*(xy[0] if visible else m.last_tracking_error_xy[0]) if visible or m.pitch_reacquire else None
    goal=round(m.visual.step(error,now,(obs.get('source_id'),stamp)))
    if not (m.stopping.is_set() or m.urgent_stop.is_set()):c.goal_yaw(goal)
