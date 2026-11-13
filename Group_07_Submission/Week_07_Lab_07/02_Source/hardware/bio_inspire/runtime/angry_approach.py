"""Bounded ToF-guided Angry approach in the existing UART owner.
One measured calibration point is not face-specific depth or verified IK.
"""
import math
from pose_route import PoseRoute
from physical_distance import valid_distance_sample

MIN_TOF_CM=15.
STOP_TOF_CM=24.8  # approximate front gap20cm via measured15->18.3 offset, plus1.5cm margin

def validate(config):
    flag=config.get('angry_face_approach',False)
    degrees=config.get('angry_approach_degrees',9)
    if type(degrees)is not int or degrees not in (9,12,15,18) or degrees!=9 and flag is not True:
        raise ValueError('Angry extension requires reviewed9or12or15or18degrees')
    up=config.get('angry_head_up_deg',0)
    if type(up)is not int or up not in (0,3) or up and (degrees!=18 or flag is not True):
        raise ValueError('Angry head offset requires approved18degree route and0or3degrees')
    if type(flag)is not bool or flag and any(config.get(k)is not True for k in
            ('angry_normal_level','physical_tof_enabled','native_posture_compensation')):
        raise ValueError('Angry approach requires normal-level, ToF and compensated head')
    return flag

class AngryApproachRoute(PoseRoute):
    def __init__(self,m,target):
        self.m=m;self.started_s=m.now();self.range_phase='return';self.range_reason=None
        self.last_range_cm=None;self.stop_range_cm=None;self.stop_time_s=None;self.face_visible=False
        self.pause_reason=None;self.resume_count=0;self.last_good_key=None;self.last_head_lag=None;self.range_diagnostic={}
        self.heading_saved=False;self.heading=None;self.safety_hold=False
        self.forward_speed_raw=None;self.presentation_forward_start=None;self.presentation_lead_start=None;self.presentation_near_latched=False
        self.settling_windows={};self.settling_counts={}
        self.pending_sync_goals=None;self.pending_sync_s=None;self.sync_launch_report=None
        self.entry_aim=None;self.acquisition_source=None
        self.held_goals=None;self.good=0;self.tilt_goal=m.controller.normal[4];self.tilt_stable=0
        super().__init__(m.controller,target,target,level_only=True,defer_level_send=True)
        self.completion_behavior='angry';self.angry_level_started_s=self.started_s
        self.measured_head_compensation=True;self.native_lean_started=False
        self.approach_degrees=getattr(m,'angry_approach_degrees',9)
        if type(self.approach_degrees)is not int or self.approach_degrees not in (9,12,15,18):
            raise ValueError('Angry extension requires reviewed9or12or15or18degrees')
        self.angry_roll_degrees=getattr(m,'presentation_angry_roll_deg',6)
        if (type(self.angry_roll_degrees)is not int or self.angry_roll_degrees not in (6,12,15)
                or self.angry_roll_degrees!=6 and not getattr(m,'presentation_angry_constant_speed25',False)):
            raise ValueError('Angry wrist roll requires reviewed6or12or15degrees and presentation trial for increased roll')
        self.angry_roll_ticks=round(self.angry_roll_degrees*4096/360)
        # Explicitly approved paired recipe; keep older9/12 profiles unchanged.
        self.minimum_tof_cm=10. if self.approach_degrees>=15 else MIN_TOF_CM
        self.stop_tof_cm=19.8 if self.approach_degrees>=15 else STOP_TOF_CM
        self.target_front_cm=15. if self.approach_degrees>=15 else 20.
        up=getattr(m,'angry_head_up_deg',0)
        if type(up)is not int or up not in (0,3) or up and self.approach_degrees!=18:
            raise ValueError('Angry head offset requires approved18degree route and0or3degrees')
        self.head_up_bias_ticks=-round(up*4096/360)
        self.angry_pitch_window=((self.c.normal[5]-round(40*4096/360),self.c.pitch_window[1])
                                 if self.approach_degrees==18 else self.c.pitch_window)
        ticks=round(self.approach_degrees*4096/360)
        self.endpoints={2:self.c.normal[2]-ticks,3:self.c.normal[3]+ticks}
        for i,q in {**self.endpoints,4:self.c.normal[4]-self.angry_roll_ticks}.items():
            lo,hi=self.path_windows[i];tol=self.c.normal_tolerances[i]
            self.path_windows[i]=(min(lo,q-tol),max(hi,q+tol))
        for i,w in ((1,self.c.yaw_window),(5,self.angry_pitch_window)):
            lo,hi=self.path_windows[i];self.path_windows[i]=(min(lo,w[0]-6),max(hi,w[1]+6))
        self.c.pose_route_windows=dict(self.path_windows);self.c.bus.windows.update(self.path_windows)
    def cancel(self):
        self.pending_sync_goals=None
        super().cancel()
        c=self.c
        if (getattr(self,'approach_degrees',None)==18
                and getattr(c,'interest_pitch_window',None)==self.angry_pitch_window):
            old=c.feedback_window(5)
            c.interest_pitch_window=None
            c.behavior_pitch_window=(min(old[0],c.pitch_window[0]),max(old[1],c.pitch_window[1]))
            c.sleepy_return_pending=True
            c.bus.windows[5]=c.behavior_pitch_window
    def _cancelled(self):
        return (self.m.stopping.is_set() or self.m.urgent_stop.is_set()
                or getattr(self.m,'operator_stopped',False) or self.c.state not in ('READY','FOLLOWING'))
    def head_compensation_target(self,rows):
        # Predict only a small postural lead from measured arms. Never send
        # the full endpoint head pose while the slow arms are still at entry.
        if self._cancelled() or self.safety_hold or self.range_phase!='advance':return None
        actual={r['id']:r['position_raw'] for r in rows if r['id'] in (2,3)}
        delta={i:self.endpoints[i]-actual[i] for i in (2,3)}
        remaining=sum(abs(v) for v in delta.values())
        scale=min(1.,34/remaining) if remaining else 0.
        if getattr(self.m,'presentation_angry_smooth',False):scale*=self._presentation_ramp(self.presentation_lead_start)
        return {i:actual[i]+math.trunc(delta[i]*scale) for i in (2,3)}
    def head_reference_bias(self):
        bias=(self.head_up_bias_ticks if self.heading_saved and not self.safety_hold
                and not self._cancelled() and self.phase in ('lean','complete') else 0.)
        if getattr(self.m,'presentation_angry_smooth',False):bias*=self._presentation_ramp(self.presentation_forward_start)
        return bias
    def _presentation_ramp(self,start):
        if start is None:return 0.
        u=max(0.,min(1.,(self.m.now()-start)/.5))
        return u*u*(3-2*u)
    def _forward_speed(self,cm):
        if not getattr(self.m,'presentation_angry_smooth',False):return 17
        if getattr(self.m,'presentation_angry_constant_speed25',False) is True:return 25
        if cm<35.:self.presentation_near_latched=True
        return 17 if self.presentation_near_latched else 25
    def _set_forward_speed(self,value):
        if self.forward_speed_raw==value:return
        self.c.bus.presentation_angry_speed_trial=getattr(self.m,'presentation_angry_smooth',False) is True
        self.c.bus.interested_native_body_trial=True
        try:
            for sid in (2,3):
                if self._cancelled():return
                self.c.bus.write(sid,46,value.to_bytes(2,'little'))
            self.forward_speed_raw=value
        finally:
            self.c.bus.presentation_angry_speed_trial=False;self.c.bus.interested_native_body_trial=False
    def commit_pending_head(self,goal):
        """Join a pending native launch with this cycle's compensated head.

        No global write buffering: holds, parameter writes and readbacks stay
        immediate. Subsequent head updates never resend the arm endpoint.
        """
        if self.pending_sync_goals is None:return None
        if self._cancelled() or self.phase!='lean' or self.range_phase!='advance':
            self.pending_sync_goals=None;return False
        now=self.m.now();face,cm=self._face_range(now);self.last_range_cm=cm
        rows=self.c.last_rows
        if now-self.started_s>=12.:
            self._finish(rows,'entry_budget');return False
        if cm is not None and cm<=self.minimum_tof_cm:
            self._minimum_hold(rows);return False
        if cm is None:
            self._pause_forward(rows,'range_unreliable');return False
        if cm<=self.stop_tof_cm:
            self._finish(rows,'range_brake_guard',tilt=True);return False
        if now-self.pending_sync_s>.5:
            self._pause_forward(rows,'sync_head_frame_expired');return False
        if (not self.c.pitch_tracking_enabled or type(goal)is not int
                or not self.c.active_pitch_window()[0]<=goal<=self.c.active_pitch_window()[1]):
            raise ValueError('Angry Sync head outside existing pitch authorization')
        self._set_forward_speed(self._forward_speed(cm))
        goals={**self.pending_sync_goals,5:goal}
        self.c.bus.windows[5]=self.c.active_pitch_window()
        self.c.bus.sync_body_head_position_trial=True
        try:self.sync_launch_report=self.c.bus.sync_positions(goals,self._cancelled)
        finally:self.c.bus.sync_body_head_position_trial=False
        self.pending_sync_goals=None
        self.c.last_joint_targets.update({i:goals[i] for i in (2,3)})
        self.c.last_pitch_goal=goal
        return True
    def _face_range(self,now):
        r=getattr(self.m,'latest_result',None) or {};o=r.get('observation') or {};i=r.get('intent') or {}
        stamp=o.get('captured_s');xy=i.get('error_xy')
        face=(o.get('status') in ('TRACKING','ACQUIRED') and i.get('mode')=='FOLLOW'
              and type(stamp) in (int,float) and math.isfinite(stamp) and 0<=now-stamp<=.5
              and isinstance(xy,(tuple,list)) and len(xy)==2 and all(type(v) in (int,float) and math.isfinite(v) and abs(v)<=1. for v in xy))
        self.face_centered=face and all(abs(v)<=.2 for v in xy)
        source=getattr(self.m,'physical_distance',None)
        d=source.latest() if source is not None else None
        d=d if isinstance(d,dict) else {}
        range_now=max(now,self.m.now());stamp=d.get('received_s');cm=d.get('distance_cm')
        valid=(d.get('measurement_state','range')=='range' and valid_distance_sample(d,range_now))
        self.measurement_key=d.get('sequence',d.get('received_s'))
        self.range_diagnostic=dict(age_s=range_now-stamp if type(stamp) in (int,float) else None,state=d.get('measurement_state'),status=d.get('range_status_raw'))
        return face,cm if valid else None
    def _remember_heading(self,rows):
        by_id={r['id']:r for r in rows}
        self.heading=dict(time_s=self.m.now(),yaw_raw=self.c.last_goal if type(self.c.last_goal)is int else by_id[1]['position_raw'],
                          pitch_raw=self.c.last_pitch_goal if type(self.c.last_pitch_goal)is int else by_id[5]['position_raw'],
                          body_raw={i:by_id[i]['position_raw'] for i in (2,3)})
        for name in ('visual','pitch_visual'):
            v=getattr(self.m,name,None)
            if v is not None:v.velocity=0.;v.filtered_error=0.
        self.heading_saved=True
    def _recent_entry_aim(self,rows,now):
        if self.entry_aim is None:return False
        age=now-self.entry_aim['captured_s']
        if not 0<=age<=1.:return False
        q={r['id']:r['position_raw'] for r in rows}
        old=self.entry_aim['pose']
        # Compare orientation, not camera pixels from a different body pose.
        pitch_change=(q[5]-q[2]+q[3])-(old[5]-old[2]+old[3])
        return abs(q[1]-old[1])<=34 and abs(pitch_change)<=34
    def _minimum_hold(self,rows):
        self.pending_sync_goals=None
        self.safety_hold=True;self.range_reason=f'minimum_tof_{self.minimum_tof_cm:g}';self.stop_time_s=self.m.now();self.stop_range_cm=self.last_range_cm
        self.m.follow_enabled=False;self.m.held=True
        if not self.c.hold(f'Angry: ToF minimum{self.minimum_tof_cm:g}cm; forward stopped',all_axes=True):return
        rows=self.c.bus.snapshot()
        self.held_goals={i:int.from_bytes(self.c.bus.read(i,42,2),'little') for i in (2,3)}
        self.c.angry_body_reference=dict(self.held_goals)
        self.tilt_goal=int.from_bytes(self.c.bus.read(4,42,2),'little')
        head=next(r for r in rows if r['id']==5);old=self.c.feedback_window(5)
        self.c.behavior_pitch_window=(min(old[0],head['position_raw']),max(old[1],head['position_raw']))
        self._complete(rows)
        self.c.bus.windows[5]=self.c.behavior_pitch_window
    def _hold_body_once(self,rows):
        self.pending_sync_goals=None
        if self.held_goals is not None:return
        self.held_goals={i:self.c.normal[i] for i in (2,3)}
        if self.native_lean_started or self.range_phase=='return':
            for row in rows:
                i=row['id']
                if i not in (2,3):continue
                q=row['position_raw']  # Stop at actual pose; clamping can introduce new forward motion.
                if self._cancelled():return
                self.c.bus.write(i,42,q.to_bytes(2,'little'));self.held_goals[i]=q
                self.c.last_joint_targets[i]=q
        self.c.angry_body_reference=dict(self.held_goals)
    def _pause_forward(self,rows,reason):
        if self.range_phase!='paused':self._hold_body_once(rows)
        self.range_phase='paused';self.pause_reason=reason;self.waiting_for_player=True
        self.good=0;self.last_good_key=None
    def _complete(self,rows):
        self.pending_sync_goals=None
        self._hold_body_once(rows)
        self.phase='complete';self.range_phase='complete';self.head_tracking_active=True
        self.c.pose_route_windows=None
        windows={i:(q-self.c.normal_tolerances[i],q+self.c.normal_tolerances[i]) for i,q in {**self.held_goals,4:self.tilt_goal}.items()}
        # A hold command does not instantly stop native ramps. Preserve only
        # the already-reviewed route envelope while these joints decelerate.
        # Completion/timers remain finite; tightening must not gate the FSM.
        for row in rows:
            sid=row['id']
            if sid in windows and (row['moving_raw'] or row['speed_raw']):
                self.settling_windows[sid]=windows[sid];self.settling_counts[sid]=0
                windows[sid]=self.path_windows[sid]
        self.c.behavior_joint_windows={**getattr(self.c,'behavior_joint_windows',{}),**windows}
        self.c.behavior_joint_allowances={**getattr(self.c,'behavior_joint_allowances',{}),**{i:0 for i in windows}}
        self.c.bus.windows.update(windows);self.c.bus.windows[1]=self.c.yaw_window;self.c.bus.windows[5]=self.c.active_pitch_window()
    def _service_settling_windows(self,rows):
        for row in rows:
            sid=row['id'];window=self.settling_windows.get(sid)
            if window is None:continue
            stable=not row['moving_raw'] and not row['speed_raw'] and window[0]<=row['position_raw']<=window[1]
            self.settling_counts[sid]=self.settling_counts[sid]+1 if stable else 0
            if self.settling_counts[sid]>=3:
                self.c.behavior_joint_windows[sid]=window;self.c.bus.windows[sid]=window
                del self.settling_windows[sid];del self.settling_counts[sid]
    def _finish(self,rows,reason,tilt=False):
        self.range_reason=reason
        if self.stop_time_s is None:self.stop_time_s=self.m.now();self.stop_range_cm=self.last_range_cm
        self._hold_body_once(rows)
        if self._cancelled():return
        if tilt:
            self.tilt_goal=self.c.normal[4]-self.angry_roll_ticks
            self.c.bus.write(4,42,self.tilt_goal.to_bytes(2,'little'));self.c.current_roll_goal=self.tilt_goal
            self.range_phase='tilt';self.waiting_for_player=False;return
        # A timeout during neck motion must not tighten feedback around an unreached goal.
        roll=next(r for r in rows if r['id']==4)
        self.tilt_goal=roll['position_raw']
        roll_goal=roll.get('goal_raw')
        if type(roll_goal)is not int:roll_goal=int.from_bytes(self.c.bus.read(4,42,2),'little')
        if roll['moving_raw'] or roll['speed_raw'] or abs(roll_goal-self.tilt_goal)>2:
            self.c.bus.write(4,42,self.tilt_goal.to_bytes(2,'little'));self.c.current_roll_goal=self.tilt_goal
        if self.range_phase=='return':
            head=next(r for r in rows if r['id']==5)
            old=self.c.feedback_window(5);ordinary=self.c.pitch_window
            self.angry_pitch_restore_window=ordinary
            self.c.interest_pitch_window=(min(old[0],ordinary[0],head['position_raw']),max(old[1],ordinary[1],head['position_raw']))
            self.c.behavior_pitch_window=self.c.interest_pitch_window
            self.c.bus.windows[5]=self.c.interest_pitch_window
            self.c.bus.write(5,42,head['position_raw'].to_bytes(2,'little'));self.c.last_pitch_goal=head['position_raw']
        self._complete(rows)
    def step(self,rows):
        if self._cancelled() or self.phase=='cancelled':return
        now=self.m.now()
        face,cm=self._face_range(now);self.last_range_cm=cm;self.face_visible=face
        if not self.heading_saved and self.face_centered:
            observation=self.m.latest_result['observation']
            self.entry_aim=dict(captured_s=observation['captured_s'],pose={r['id']:r['position_raw'] for r in rows})
        if cm is not None and cm<=self.minimum_tof_cm:
            if not self.safety_hold:self._minimum_hold(rows)
            return
        if self.phase=='complete':
            self._service_settling_windows(rows);return
        if now-self.started_s>=12.:
            self._finish(rows,'entry_budget');return
        if self.phase=='return':
            if self.level_send_pending and cm is None:return
            super().step(rows)
            if self.phase=='complete':
                self.phase='lean';self.range_phase='acquire';self.head_tracking_active=True
                self.stage_target={**self.return_pose,**self.endpoints};self.waiting_for_player=True
                self.c.interest_pitch_window=self.angry_pitch_window
                self.c.pose_route_windows=dict(self.path_windows);self.c.bus.windows.update(self.path_windows)
                self.m._reset_pitch()
                from bio_inspire.runtime.awake_motion import prepare_awake
                prepare_awake(self.m,'angry_approach')
            return
        if self.range_phase=='tilt':
            roll=next(r for r in rows if r['id']==4)
            arrived=not roll['speed_raw'] and not roll['moving_raw'] and abs(roll['position_raw']-self.tilt_goal)<=self.c.normal_tolerances[4]
            self.tilt_stable=self.tilt_stable+1 if arrived else 0
            if self.tilt_stable>=3:self._complete(rows)
            return
        if cm is None:
            if self.native_lean_started:self._pause_forward(rows,'range_unreliable')
            else:self.good=0;self.waiting_for_player=True
            return
        if not self.heading_saved:
            remembered=not face and self._recent_entry_aim(rows,now)
            if not self.face_centered and not remembered:
                self.good=0;self.waiting_for_player=True;return
            self.acquisition_source='recent_pose_memory' if remembered else 'live_face'
            error=getattr(self.c,'interest_head_following_error',None)
            lag=error(rows) if callable(error) else None;self.last_head_lag=lag
            if type(lag) not in (int,float) or not math.isfinite(lag) or abs(lag)>34:
                self.good=0;self.waiting_for_player=True;return
        launching=not self.native_lean_started or self.range_phase=='paused'
        if launching:
            if self.measurement_key!=self.last_good_key:self.good+=1;self.last_good_key=self.measurement_key
            if self.good<3:self.waiting_for_player=True;return
            restore=getattr(self.c.bus,'acceleration_restore',None)
            if getattr(self.m,'fast_awake_trial',False) and restore is not None and any(i in restore.pending for i in (2,3)):
                self.waiting_for_player=True;return
        self.waiting_for_player=False
        if not self.heading_saved:self._remember_heading(rows)
        if cm<=self.stop_tof_cm:
            self._finish(rows,'range_brake_guard',tilt=True);return
        if self.native_lean_started and self.range_phase=='advance' and getattr(self.m,'presentation_angry_smooth',False):
            self._set_forward_speed(self._forward_speed(cm))
        if launching:
            if self.range_phase=='paused':self.resume_count+=1
            self.held_goals=None;self.pause_reason=None
            if getattr(self.m,'presentation_angry_smooth',False):
                unsent=(getattr(self.m,'presentation_angry_sync_positions',False) and self.sync_launch_report is None)
                if self.presentation_forward_start is None or unsent:self.presentation_forward_start=now
                self.presentation_lead_start=now
            if getattr(self.m,'presentation_angry_smooth',False):self._set_forward_speed(self._forward_speed(cm))
            self.c.bus.interested_native_body_trial=True
            try:
                for i,q in self.endpoints.items():
                    if self._cancelled():return
                    self.c.bus.write(i,41,b'\1')
                    if not getattr(self.m,'presentation_angry_smooth',False):self.c.bus.write(i,46,(17).to_bytes(2,'little'))
                    if not getattr(self.m,'presentation_angry_sync_positions',False):
                        self.c.bus.write(i,42,q.to_bytes(2,'little'));self.c.last_joint_targets[i]=q
            finally:self.c.bus.interested_native_body_trial=False
            if getattr(self.m,'presentation_angry_sync_positions',False):
                self.pending_sync_goals=dict(self.endpoints);self.pending_sync_s=now
            self.native_lean_started=True;self.range_phase='advance'
        arrived=all(not r['speed_raw'] and not r['moving_raw'] and abs(r['position_raw']-self.endpoints[r['id']])<=self.c.normal_tolerances[r['id']] for r in rows if r['id'] in (2,3))
        if arrived:self._finish(rows,'joint_limit',tilt=True)

    def status(self):
        return dict(phase=self.range_phase,reason=self.range_reason,range_cm=self.last_range_cm,
                    sync_pending_goals=self.pending_sync_goals,sync_launch_report=self.sync_launch_report,
                    settling_joint_ids=sorted(self.settling_windows),
                    forward_speed_raw=self.forward_speed_raw,presentation_smooth=getattr(self.m,'presentation_angry_smooth',False),
                    constant_speed25_trial=getattr(self.m,'presentation_angry_constant_speed25',False),
                    stop_range_cm=self.stop_range_cm,stop_time_s=self.stop_time_s,
                    stop_guard_cm=self.stop_tof_cm,calibration_sensor_cm=18.3,calibration_front_gap_cm=15.,approximate_target_front_gap_cm=self.target_front_cm,target_sensor_cm=self.stop_tof_cm-1.5,
                    last_forward_face_visible=self.face_visible,body_goals=self.held_goals,forward_started=self.native_lean_started,
                    tilt_goal_raw=self.tilt_goal,tilt_degrees=self.angry_roll_degrees,measured_head_compensation=True,
                    pause_reason=self.pause_reason,resume_count=self.resume_count,head_lag_ticks=self.last_head_lag,
                    range_diagnostic=self.range_diagnostic,heading_saved=self.heading_saved,heading=self.heading,
                    safety_hold=self.safety_hold,minimum_tof_cm=self.minimum_tof_cm,
                    approach_degrees=self.approach_degrees,postural_head_lead_ticks=34,
                    angry_pitch_window=self.angry_pitch_window,head_up_bias_ticks=self.head_up_bias_ticks,
                    acquisition_source=self.acquisition_source,
                    entry_aim_captured_s=None if self.entry_aim is None else self.entry_aim['captured_s'])
