"""Operator-approved retreat preview; no ToF automation or CPG in this stage."""
import math


def validate_taught_pose(pose):
    if pose is None:return None
    if not isinstance(pose,dict) or set(pose)!=set(range(1,6)) or any(type(k)is not int or type(v)is not int or not 0<=v<=4095 for k,v in pose.items()):
        raise ValueError('Five recorded raw positions required for taught crouch')
    return dict(pose)


class AfraidPose:
    phase='retreat'
    head_tracking_active=True
    force_normal=False

    def __init__(self,c,rows,fold_down=False,taught=None,duration_s=10.,now=None):
        self.c=c;self.stable=0
        self.taught=validate_taught_pose(taught)
        self.owner=None;self.progress=0.;self.started=now
        self.target={2:c.normal[2]+68,3:c.normal[3]+(68 if fold_down else -68),4:c.normal[4]}
        if self.taught is not None:
            allowed=(3.,6.,10.) if getattr(c,'fast_awake_trial',False) else (6.,10.)
            if duration_s not in allowed or type(now) not in (int,float) or not math.isfinite(now):raise ValueError('Approved crouch duration and clock required')
            self.target={i:self.taught[i] for i in (2,3,4)}
            self.duration_s=duration_s
            native={i:int.from_bytes(c.bus.read(i,42,2),'little') for i in (2,3,4,5)}
            by_id={r['id']:r for r in rows}
            def start_goal(i):
                r=by_id[i]
                return r['position_raw'] if r['speed_raw'] or r['moving_raw'] or abs(native[i]-r['position_raw'])>c.normal_tolerances[i] else native[i]
            self.entry={i:min(self.target[i],start_goal(i)) if i in (2,3) else start_goal(i) for i in (2,3,4)}
            self.pitch_command_window=(min(c.pitch_window[0],self.taught[5]),max(c.pitch_window[1],self.taught[5]))
            self.entry_head=max(self.pitch_command_window[0],start_goal(5))
            self.head_window=(self.pitch_command_window[0],max(self.pitch_command_window[1],self.entry_head))
            self.head_return_ceiling=self.entry_head
            self.last_sent={i:native[i] for i in (2,3,4)}
        self.final_windows={i:(q-c.normal_tolerances[i],q+c.normal_tolerances[i]) for i,q in self.target.items()}
        self.path_windows={}
        for row in rows:
            i=row['id']
            if i in self.target:
                old=int.from_bytes(c.bus.read(i,42,2),'little')
                q=self.target[i];tol=c.normal_tolerances[i]
                self.path_windows[i]=(max(0,min(row['position_raw'],old,q)-tol),min(4095,max(row['position_raw'],old,q)+tol))
            elif i==1:
                old=c.feedback_window(i)
                self.path_windows[i]=(min(old[0],c.yaw_window[0]-6),max(old[1],c.yaw_window[1]+6))
            else:
                bounds=c.active_pitch_window()
                old=c.feedback_window(i)
                self.path_windows[i]=(min(old[0],bounds[0]-6),max(old[1],bounds[1]+6))
        c.pose_route_windows=dict(self.path_windows)
        c.bus.windows.update(self.path_windows)
        c.bus.windows[1]=c.yaw_window
        c.behavior_pitch_window=(min(c.pitch_window[0],rows[4]['position_raw']),max(c.pitch_window[1],rows[4]['position_raw']))
        c.sleepy_return_pending=True
        if self.taught is not None:
            self.path_windows[5]=(min(self.path_windows[5][0],self.head_window[0]-6),max(self.path_windows[5][1],self.head_window[1]+6))
            c.pose_route_windows=dict(self.path_windows)
            c.behavior_pitch_window=self.head_window;c.sleepy_return_pending=False

    def send(self,m):
        self.owner=m
        if self.taught is not None:
            for i,q in self.entry.items():
                if m.stopping.is_set() or m.urgent_stop.is_set():raise RuntimeError('Crouch entry cancelled')
                if self.last_sent[i]!=q:
                    self.c.bus.write(i,42,q.to_bytes(2,'little'));self.last_sent[i]=q;self.c.last_joint_targets[i]=q
            return
        c=self.c
        for i,q in self.target.items():
            if m.stopping.is_set() or m.urgent_stop.is_set():raise RuntimeError('Afraid request cancelled')
            c.bus.write(i,42,q.to_bytes(2,'little'))
            c.last_joint_targets[i]=q
        c.current_roll_goal=c.normal[4]

    def step(self,rows):
        if self.phase in ('retreat','held') and self.taught is not None:self.contract_head(rows)
        if self.phase!='retreat':return
        if self.taught is not None:
            m=self.owner
            if m is None or m.stopping.is_set() or m.urgent_stop.is_set() or getattr(m,'operator_stopped',False):return
            u=max(0.,min(1.,(self.c.last_tick-self.started)/self.duration_s))
            # Approved6s response: cubic easing has less initial dead travel
            # than the original10s quintic, with zero endpoint velocity.
            self.progress=u*u*(3-2*u) if self.duration_s in (3.,6.) else u*u*u*(10+u*(-15+6*u))
            for i,target in self.target.items():
                goal=round(self.entry[i]+(target-self.entry[i])*self.progress)
                if m.stopping.is_set() or m.urgent_stop.is_set():return
                if self.last_sent[i]!=goal:
                    self.c.bus.write(i,42,goal.to_bytes(2,'little'));self.last_sent[i]=goal
                    self.c.last_joint_targets[i]=goal
            if u<1.:return
        if self.taught is None and not getattr(self.c,'sleepy_return_pending',False):
            self.path_windows[5]=(self.c.pitch_window[0]-6,self.c.pitch_window[1]+6)
            self.c.pose_route_windows=dict(self.path_windows)
        arrived=all(not r['speed_raw'] and not r['moving_raw'] and abs(r['position_raw']-self.target[r['id']])<=self.c.normal_tolerances[r['id']] for r in rows if r['id'] in self.target)
        self.stable=self.stable+1 if arrived else 0
        if self.stable>=3:
            self.phase='held';c=self.c;c.pose_route_windows=None
            c.behavior_joint_windows={**getattr(c,'behavior_joint_windows',{}),**self.final_windows}
            c.behavior_joint_allowances={**getattr(c,'behavior_joint_allowances',{}),**{i:0 for i in self.target}}
            c.bus.windows.update(self.final_windows)

    def cancel(self):self.phase='cancelled'

    def head_reference(self):
        return self.entry_head+(self.taught[5]-self.entry_head)*self.progress

    def head_goal(self,goal):
        low,high=self.pitch_command_window;c=self.c
        if goal>high:
            if not low<=goal<=self.head_return_ceiling:raise ValueError('Head return must not move farther outside awake bounds')
            c.bus.write(5,42,goal.to_bytes(2,'little'));c.last_pitch_goal=goal
        else:c.goal_pitch(goal)
        self.head_return_ceiling=min(self.head_return_ceiling,goal)

    def contract_head(self,rows):
        if self.head_window==self.pitch_command_window:return
        low,high=self.pitch_command_window;head=next(r for r in rows if r['id']==5)
        if not low<=head['position_raw']<=high:return
        model=getattr(self.owner,'afraid_head_model',None) if self.owner is not None else None
        if model is not None and not model.contract(low,high):return
        if model is None and not low<=int.from_bytes(self.c.bus.read(5,42,2),'little')<=high:return
        self.head_window=self.pitch_command_window
        self.path_windows[5]=(low-6,high+6)
        if self.c.pose_route_windows is not None:self.c.pose_route_windows[5]=self.path_windows[5]
        self.c.behavior_pitch_window=self.pitch_command_window;self.c.bus.windows[5]=self.pitch_command_window


def enter_afraid(m):
    c=m.controller
    if not getattr(m,'afraid_pose_trial_enabled',False):return
    if m.stopping.is_set() or m.urgent_stop.is_set() or getattr(m,'operator_stopped',False):return
    if c.state not in ('READY','FOLLOWING') or getattr(m,'behavior_trial',None)=='afraid':return
    rows=c.bus.snapshot()
    if ([r['id'] for r in rows]!=list(range(1,6)) or any(r['mode'] or r['status_raw'] or r['torque_raw']!=1 or not c.feedback_window(r['id'])[0]<=r['position_raw']<=c.feedback_window(r['id'])[1] for r in rows)):
        raise RuntimeError('Afraid requires healthy feedback inside current reviewed bounds')
    if m.stopping.is_set() or m.urgent_stop.is_set():return
    from bio_inspire.runtime.sleepy_trial import finish_sleepy_native_fold
    finish_sleepy_native_fold(c)
    old=getattr(c,'pose_route',None)
    if old is not None:old.cancel()
    route=AfraidPose(c,rows,fold_down=getattr(m,'afraid_fold_down',False),
        taught=getattr(m,'afraid_taught_pose',None),duration_s=getattr(m,'afraid_crouch_duration_s',10.),now=m.now())
    m.behavior_trial='afraid';m.pending_behavior=None;m.interested_roll_due=None;m.sleepy_entry_prepared=False
    m.pending_happy_from_touch=False;m.sleepy_trial_active=False
    from bio_inspire.runtime.three_state_behavior import _small_happy_speed
    _small_happy_speed(m,False)
    c.pose_route=route;c.interest_pitch_window=None
    if route.taught is not None:c.interest_pitch_window=route.pitch_command_window
    from bio_inspire.runtime.awake_motion import prepare_awake
    prepare_awake(m,'afraid')
    m.yaw_follow_enabled=True
    c.tracking_speed=c.motion_speed
    c.configure_tracking(yaw=True,pitch=True)
    if route.taught is not None:c.bus.windows[5]=route.head_window
    m.visual.position=None;m._reset_pitch();m.follow_enabled=True;m.held=False
    m.afraid_head_model=None
    route.send(m)
    if m.stopping.is_set() or m.urgent_stop.is_set():return
    if m.led_ring is None:
        from led_ring import LedRing
        m.led_ring=LedRing()
    m.led_ring.afraid();m.last_led_behavior='afraid'


def apply_afraid_gaze(m,result,now):
    """Head-only loss handling must never cancel the body retreat monitor."""
    if m.stopping.is_set() or m.urgent_stop.is_set() or getattr(m,'operator_stopped',False):return
    c=m.controller;obs=(result or {}).get('observation') or {};intent=(result or {}).get('intent') or {}
    xy=intent.get('error_xy');stamp=obs.get('captured_s')
    visible=(obs.get('status') in ('TRACKING','ACQUIRED') and intent.get('mode')=='FOLLOW'
             and type(stamp) in (int,float) and math.isfinite(stamp) and 0<=now-stamp<=.5
             and isinstance(xy,(tuple,list)) and len(xy)==2
             and all(type(v) in (int,float) and math.isfinite(v) and -1<=v<=1 for v in xy))
    route=getattr(c,'pose_route',None)
    if getattr(route,'taught',None) is not None:
        m.pitch_reacquire=m._face_exit_memory(obs,intent,now,visible)
        if m.afraid_head_model is None:
            from bio_inspire.runtime.taught_crouch_head import TaughtCrouchHead
            m.pitch_visual.low,m.pitch_visual.high=route.head_window
            m.afraid_head_model=TaughtCrouchHead(m.pitch_visual,route.entry_head,now,
                native_posture=getattr(m,'native_posture_compensation',False))
        head_error=m.pitch_direction*90*(xy[1] if visible else m.last_tracking_error_xy[1]) if visible or m.pitch_reacquire else None
        goal=m.afraid_head_model.step(route.head_reference(),head_error,now,(obs.get('source_id'),stamp),route.pitch_command_window)
        if m.stopping.is_set() or m.urgent_stop.is_set():return
        route.head_goal(goal)
    else:m._apply_small_happy_head(result,now)
    if m.visual.position is None:
        if not visible:return
        actual=next(r['position_raw'] for r in c.last_rows if r['id']==1)
        m.visual.reset(max(m.visual.low,min(m.visual.high,actual)),now)
    searching=getattr(m,'pitch_reacquire',False)
    error=c.direction*160*(xy[0] if visible else m.last_tracking_error_xy[0]) if visible or searching else None
    goal=round(m.visual.step(error,now,(obs.get('source_id'),stamp)))
    if m.stopping.is_set() or m.urgent_stop.is_set():return
    c.goal_yaw(goal)
