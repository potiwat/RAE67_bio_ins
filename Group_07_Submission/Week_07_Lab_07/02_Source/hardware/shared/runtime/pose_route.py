"""One supervised out-and-back pose request, using the existing UART owner."""
from motion_composer import compose_goals
import math
class PoseRoute:
    def __init__(self,controller,target,return_pose=None,post_steps=(),final_windows=None,normal_only=False,start_post=False,level_only=False,defer_level_send=False,button_dynamic=False,coordinated_return=None,preserve_normal_yaw=False):
        if type(preserve_normal_yaw)is not bool or preserve_normal_yaw and (not normal_only or target!=controller.normal or post_steps):
            raise ValueError('Preserve yaw requires explicit Normal body return')
        if type(button_dynamic)is not bool or button_dynamic and (normal_only or start_post or level_only or controller.motion_speed!=600):
            raise ValueError('Dynamic button glance requires explicit outward600 route')
        if coordinated_return is None:
            coordinated_return=(getattr(controller,'coordinated_pose_transitions',False) is True
                                and (normal_only or level_only or button_dynamic))
        if type(coordinated_return)is not bool or coordinated_return and (not (normal_only or level_only or button_dynamic) or controller.motion_speed!=600):
            raise ValueError('Coordinated pose requires explicit Normal/level/dynamic-button600 route')
        self.coordinated_return=coordinated_return;self.return_progress=0.
        self.button_dynamic=button_dynamic
        self.c=controller;self.target=dict(target);self.phase='look';self.stable=0
        self.post_steps=list(post_steps);self.remaining_steps=list(post_steps)
        self.final_windows=dict(final_windows or {});self.force_normal=False;self.stage_target=None
        self.head_tracking_active=False;self.level_send_pending=defer_level_send
        self.paused_for_face=False
        self.lean_models=None;self.waiting_for_player=False;self.gaze_wait_elapsed_s=0.;self.lean_in_motion=False
        self.native_neck_pending=False;self.native_neck_entry=None
        self.native_lean_time=None;self.native_lean_started=False;self.native_lean_speed=None
        self.settle_progress=None
        self.face_wait_last=None
        if type(level_only)is not bool:raise ValueError('Explicit level-only route required')
        if type(defer_level_send)is not bool or defer_level_send and not level_only:raise ValueError('Deferred send requires level-only route')
        if level_only and (normal_only or start_post or post_steps or any(target.get(i)!=controller.normal[i] for i in (2,3,4,5))
                           or type(target.get(1))is not int or not controller.yaw_window[0]<=target[1]<=controller.yaw_window[1]):
            raise ValueError('Level-only route uses Normal body/head and bounded player yaw')
        c=controller;rows=c.bus.snapshot()
        if c.state not in ('READY','FOLLOWING') or len(rows)!=5 or any(r['mode'] or r['status_raw'] or r['torque_raw']!=1 or not c.feedback_window(r['id'])[0]<=r['position_raw']<=c.feedback_window(r['id'])[1] for r in rows):
            raise ValueError('LOOK BUTTON needs healthy current pose inside reviewed bounds')
        if set(target)!=set(c.normal) or any(type(v)is not int or not 0<=v<=4095 for v in target.values()):raise ValueError('Five recorded raw targets required')
        self.return_pose=({i:int.from_bytes(c.bus.read(i,42,2),'little') for i in c.normal} if return_pose is None else dict(return_pose))
        if set(self.return_pose)!=set(c.normal) or any(type(v)is not int or not 0<=v<=4095 for v in self.return_pose.values()):raise ValueError('Five saved return targets required')
        self.previous_bus_windows=dict(c.bus.windows)
        for name,pose in self.post_steps:
            if name not in ('lean','tilt') or set(pose)!=set(c.normal) or any(type(v)is not int or not 0<=v<=4095 for v in pose.values()):raise ValueError('Invalid post-look pose')
        c.behavior_sweep=None
        actual={r['id']:r['position_raw'] for r in rows}
        normal_target=dict(c.normal)
        if preserve_normal_yaw:
            if not c.yaw_window[0]<=actual[1]<=c.yaw_window[1]:
                raise ValueError('Current yaw outside reviewed Normal yaw bounds')
            normal_target[1]=actual[1]
            target=dict(normal_target);self.target=dict(target)
            self.return_pose=dict(normal_target)
        self.return_start=dict(actual)
        previous_feedback={i:c.feedback_window(i) for i in target}
        points=[actual,c.normal,self.return_pose,target]+[pose for name,pose in self.post_steps]
        self.path_windows={i:(min(p[i] for p in points)-c.normal_tolerances[i],max(p[i] for p in points)+c.normal_tolerances[i]) for i in target}
        # Any state preemption can reverse a native ramp. Keep the previous
        # reviewed feedback envelope until the new route settles; only the
        # explicit recorded route targets are sent as commands.
        self.path_windows={i:(min(low,previous_feedback[i][0]),max(high,previous_feedback[i][1]))
                           for i,(low,high) in self.path_windows.items()}
        c.pose_route_windows=dict(self.path_windows)
        c.bus.windows.update(c.pose_route_windows)
        if start_post:
            if not self.remaining_steps or self.remaining_steps[0][0]!='lean':raise ValueError('Direct Interested requires recorded lean step')
            self.phase,self.stage_target=self.remaining_steps.pop(0)
            self.head_tracking_active=getattr(c,'interest_head_tracking',False)
            if self.head_tracking_active:
                c.interest_pitch_window=getattr(c,'interest_pitch_window_request',None)
                for i,window in ((1,c.yaw_window),(5,c.active_pitch_window())):
                    low,high=self.path_windows[i]
                    self.path_windows[i]=(min(low,window[0]-6),max(high,window[1]+6))
                c.pose_route_windows=dict(self.path_windows);c.bus.windows.update(self.path_windows)
            for i in target:
                c.bus.write(i,46,c.motion_speed.to_bytes(2,'little'));c.bus.write(i,41,b'\1')
            self.send(self.stage_target);return
        if normal_only or level_only:
            if normal_only and (target!=normal_target or self.post_steps):raise ValueError('Direct Normal requires recorded Normal body and bounded yaw')
            self.force_normal=normal_only;self.phase='return';self.return_pose=dict(target)
            c.interest_pitch_window=None
            if not self.level_send_pending:self._send_level_return()
            return
        c.bus.button_look_speed_trial=True
        c.bus.button_look_dynamic_acceleration_trial=self.button_dynamic
        try:
            if self.button_dynamic:
                from acceleration_restore import AccelerationRestore
                if not hasattr(c.bus,'acceleration_restore'):c.bus.acceleration_restore=AccelerationRestore()
            for i in target:
                speed=600 if self.button_dynamic else getattr(c,'button_look_speed_raw',1000)
                acc={1:3,2:8,3:8,4:12,5:6}[i] if self.button_dynamic else 1
                c.bus.write(i,46,speed.to_bytes(2,'little'))
                if self.button_dynamic:c.bus.acceleration_restore.protect(i,acc,c.normal_tolerances[i])
                c.bus.write(i,41,bytes((acc,)))
                if self.button_dynamic:c.bus.acceleration_restore.defer(i,1)
        finally:
            c.bus.button_look_speed_trial=False
            c.bus.button_look_dynamic_acceleration_trial=False
        if self.coordinated_return:self._begin_coordinated_return(target)
        else:self.send(target)
    def _send_level_return(self):
        self.level_send_pending=False
        for i in self.return_pose:
            self.c.bus.write(i,46,self.c.motion_speed.to_bytes(2,'little'));self.c.bus.write(i,41,b'\1')
        if self.coordinated_return:self._begin_coordinated_return(self.return_pose)
        else:self.send(self.return_pose)
    def _begin_coordinated_return(self,target):
        rows=self.c.bus.snapshot()
        self.return_start={r['id']:r['position_raw'] for r in rows}
        self.motion_target=dict(target);self.return_progress=0.
        self.return_started=self._return_now();self.return_last_time=self.return_started
        # Same command ceilings as accepted awake motion; derive one common
        # duration so native ramp differences cannot schedule independent poses.
        acc={1:3,2:8,3:8,4:12,5:6};base=8.7*4096/360
        delta={i:abs(self.motion_target[i]-q) for i,q in self.return_start.items()}
        self.return_duration=max(.5,*[max(1.875*d/600.,math.sqrt(5.774*d/(base*acc[i]))) for i,d in delta.items()])
        self.send(self.return_start)
    def _return_now(self):
        c=self.c
        return c.control_clock() if callable(getattr(c,'control_clock',None)) else c.control_now_s
    def _step_coordinated_return(self):
        now=self._return_now()
        if not math.isfinite(now) or now<self.return_last_time:
            raise ValueError('Invalid coordinated return control interval')
        if self.return_progress>=1.:
            self.return_last_time=now
            return True  # Endpoint already sent; only healthy arrival feedback is pending.
        if now-self.return_last_time>.5:
            raise ValueError('Invalid coordinated return control interval')
        self.return_last_time=now
        u=max(0.,min(1.,(now-self.return_started)/self.return_duration))
        self.return_progress=u*u*u*(10.+u*(-15.+6.*u))
        goals={i:round(q+(self.motion_target[i]-q)*self.return_progress) for i,q in self.return_start.items()}
        if goals!=getattr(self,'last_sent_goals',None):self.send(goals)
        return u>=1.
    def send(self,target):
        native_body=getattr(self.c,'interest_native_body_speed_raw',None)
        if self.phase=='lean' and self.head_tracking_active and native_body is not None and self.native_lean_time is None:
            # Hold existing loaded goals until gaze is fresh. The final body
            # targets are sent once, leaving the servo's ramp in charge.
            initial={i:int.from_bytes(self.c.bus.read(i,42,2),'little') for i in (2,3,4)}
            self.native_lean_time=self.c.control_clock() if callable(getattr(self.c,'control_clock',None)) else self.c.control_now_s
            self.c.lean_started_s=self.native_lean_time;self.waiting_for_player=True
            target={**target,**initial}
        if self.phase=='lean' and self.head_tracking_active and native_body is None and getattr(self.c,'interest_gaze_priority',False) and self.lean_models is None:
            from bounded_motion import BoundedMotion,MotionLimits
            c=self.c;speed,acc,max_dt=c.lean_command_limits
            initial={i:int.from_bytes(c.bus.read(i,42,2),'little') for i in (2,3,4)}
            if getattr(c,'interest_body_acceleration_raw',1)==3:
                c.bus.interested_body_acc3_trial=True
                try:
                    for sid in (2,3):c.bus.write(sid,41,b'\3')
                finally:c.bus.interested_body_acc3_trial=False
            stamp=c.control_clock() if callable(getattr(c,'control_clock',None)) else c.control_now_s
            native_neck=getattr(c,'interest_native_neck',False)
            self.lean_models={i:BoundedMotion(initial[i],stamp,
                MotionLimits(*self.path_windows[i],speed/(2 if i in (2,3) else 1),acc/(2 if i in (2,3) else 1),max_dt)) for i in ((2,3) if native_neck else (2,3,4))}
            self.native_neck_pending=native_neck;self.native_neck_entry=initial[4]
            c.lean_started_s=stamp
            self.waiting_for_player=True
            target={**target,**{i:round(v.position) for i,v in self.lean_models.items()}}
            if native_neck:target[4]=initial[4]
        bounds=self.c.bus.windows
        if self.head_tracking_active and self.phase=='lean':
            # ID1/5 are not sent by this route. Their saved historical pose can
            # still contain Sleepy's droop while gaze has contracted its own
            # command window. Validate that history against its reviewed path,
            # not as though it were a new gaze command; actual head writes
            # remain exclusively validated by goal_yaw/goal_pitch below.
            bounds={**bounds,**{i:self.path_windows[i] for i in (1,5)}}
        goals=compose_goals(target,bounds,exclusive=True,state=self.c.state)
        if goals is None:return
        from coordinated_positions import write_positions
        outgoing={i:goals[i] for i in sorted(goals)
            if not (self.head_tracking_active and self.phase=='lean' and i in (1,5))
            and not (self.phase=='lean' and (self.lean_models is not None or self.native_lean_time is not None)
                     and getattr(self,'last_sent_goals',{}).get(i)==goals[i])}
        if outgoing and write_positions(self.c.bus,outgoing,source='pose_'+self.phase) is None:return
        for i in outgoing:
            if i==1:self.c.last_goal=goals[i]
            elif i==5:self.c.last_pitch_goal=goals[i]
            elif i==4:self.c.current_roll_goal=goals[i]
        self.last_sent_goals=dict(goals)
        if getattr(self,'last_logged_phase',None)!=self.phase:
            print('POSE_ROUTE_GOAL',self.phase,'force_normal',self.force_normal,goals,flush=True)
            self.last_logged_phase=self.phase
    def return_normal(self,force_normal=False):
        self.head_tracking_active=False
        if force_normal:
            self.c.interest_pitch_window=None
            self.force_normal=True;self.remaining_steps=[];self.return_pose=dict(self.c.normal)
            for sid in (2,3):self.c.bus.write(sid,41,b'\1')
            for row in self.c.bus.snapshot():
                i=row['id'];low,high=self.path_windows[i]
                self.path_windows[i]=(min(low,row['position_raw']-self.c.normal_tolerances[i]),max(high,row['position_raw']+self.c.normal_tolerances[i]))
        self.c.pose_route_windows=dict(self.path_windows);self.c.bus.windows.update(self.path_windows)
        self.phase='return';self.stable=0
        self.c.bus.button_look_return_trial=True
        try:
            speed=self.c.motion_speed if self.force_normal else getattr(self.c,'button_return_speed_raw',750)
            for i in sorted(self.c.normal):self.c.bus.write(i,46,speed.to_bytes(2,'little'))
        finally:self.c.bus.button_look_return_trial=False
        if getattr(self.c,'coordinated_pose_transitions',False) is True and self.c.motion_speed==600:
            self.coordinated_return=True
        if self.coordinated_return:self._begin_coordinated_return(self.return_pose)
        else:self.send(self.return_pose)
    def step(self,rows):
        if self.phase not in ('look','return','lean','tilt'):return
        if self.coordinated_return and self.c.state not in ('READY','FOLLOWING'):return
        if self.level_send_pending:self._send_level_return();return
        if self.coordinated_return and self.phase in ('look','return') and not self._step_coordinated_return():
            self.stable=0;return
        if self.phase=='lean' and self.native_lean_time is not None:
            now=self.c.control_clock() if callable(getattr(self.c,'control_clock',None)) else self.c.control_now_s
            stamp=getattr(self.c,'interest_face_stamp',now)
            ready=(getattr(self.c,'face_ready_for_interest',False) and type(stamp) in (int,float)
                   and math.isfinite(stamp) and 0<=now-stamp<=self.c.lean_command_limits[2])
            head_error=getattr(self.c,'interest_head_following_error',None)
            head_limit=getattr(self.c,'interest_head_following_limit',None)
            gentle=(getattr(self.c,'interested_gentle_entry',False) is True
                    and getattr(self,'completion_behavior',None)!='angry')
            if gentle and getattr(self.c,'interest_finish_without_face',False) is True:
                # The recorded gesture is independent of face acquisition.
                # Head posture compensation still initializes and follows the
                # body; missing vision must not suppress the body/neck pose.
                ready=True
            # A fresh image alone does not prove the posture compensation has
            # initialized. Wait for the existing head controller to report lag.
            if getattr(self,'completion_behavior',None)=='angry':ready=True  # Deterministic pose must not wait for the face it is restoring.
            ready=ready and callable(head_error) and head_limit==34
            if ready:ready=abs(head_error(rows))<=head_limit
            self.waiting_for_player=not ready
            if not ready:self.gaze_wait_elapsed_s+=max(0.,now-self.native_lean_time)
            self.native_lean_time=now
            speed=(150 if gentle else self.c.interest_native_body_speed_raw) if ready else 1
            if (ready or self.native_lean_started) and speed!=self.native_lean_speed:
                self.c.bus.interested_native_body_trial=True
                self.c.bus.interested_gentle_entry_trial=gentle
                try:
                    for sid in (2,3):
                        self.c.bus.write(sid,41,b'\1')
                        self.c.bus.write(sid,46,speed.to_bytes(2,'little'))
                    if ready and gentle and not self.native_lean_started:
                        self.c.bus.write(4,46,(100).to_bytes(2,'little'))
                finally:
                    self.c.bus.interested_native_body_trial=False
                    self.c.bus.interested_gentle_entry_trial=False
                self.native_lean_speed=speed
            if ready and not self.native_lean_started:
                self.send(self.stage_target);self.native_lean_started=True
            if not ready:self.settle_progress=None;self.stable=0;return
        if self.phase=='lean' and self.lean_models is not None:
            now=self.c.control_clock() if callable(getattr(self.c,'control_clock',None)) else self.c.control_now_s
            ready=getattr(self.c,'face_ready_for_interest',False) if self.lean_in_motion or getattr(self.c,'interest_native_neck',False) else getattr(self.c,'interest_face_centered',False)
            stamp=getattr(self.c,'interest_face_stamp',now)
            ready=ready and type(stamp) in (int,float) and math.isfinite(stamp) and 0<=now-stamp<=self.c.lean_command_limits[2]
            head_error=getattr(self.c,'interest_head_following_error',None)
            head_limit=getattr(self.c,'interest_head_following_limit',None)
            if ready and callable(head_error) and head_limit is not None:
                ready=abs(head_error(rows))<=head_limit
            self.waiting_for_player=not ready
            self.lean_in_motion=ready
            if self.waiting_for_player:self.gaze_wait_elapsed_s+=now-self.lean_models[2].time
            goals=dict(self.stage_target)
            if self.native_neck_pending:
                if ready:self.native_neck_pending=False
                else:goals[4]=self.native_neck_entry
            for i,model in self.lean_models.items():
                from bounded_motion import MotionLimits
                error=getattr(self.c,'interest_vertical_error_px',None)
                band=getattr(self.c,'interest_deadband_px',None)
                factor=min(1.,band/max(band,error)) if ready and type(error) in (int,float) and type(band) in (int,float) and band>0 else 1.
                speed,acc,max_dt=self.c.lean_command_limits;divisor=2 if i in (2,3) else 1
                velocity=speed/divisor
                lean_rate=getattr(self.c,'interest_lean_speed_deg_s',None)
                if i in (2,3) and lean_rate is not None:velocity=min(velocity,lean_rate*4096/360)
                model.limits=MotionLimits(*self.path_windows[i],velocity*factor,acc/divisor,max_dt)
                target=model.position if self.waiting_for_player else self.stage_target[i]
                goals[i]=round(model.step(target,now))
            self.send(goals)
            if self.waiting_for_player or any(abs(v.position-self.stage_target[i])>=.5 or abs(v.velocity)>1e-6 for i,v in self.lean_models.items()):
                self.settle_progress=None;self.stable=0;return
        if self.phase=='lean' and self.head_tracking_active and not getattr(self.c,'interest_finish_without_face',False):
            if not getattr(self.c,'face_ready_for_interest',False):
                self._mark_player_wait()
                if not self.paused_for_face:
                    # Preserve loaded position targets: rebasing to encoder can
                    # ratchet a gravity-loaded joint each time a face is lost.
                    for i in (2,3,4):self.c.bus.write(i,46,(1).to_bytes(2,'little'))
                    self.paused_for_face=True;self.stable=0
                    print('POSE_ROUTE_SLOW face lost during lean; goals preserved',flush=True)
                self.settle_progress=None
                return
            if self.paused_for_face:
                self.paused_for_face=False;self.stable=0;self.waiting_for_player=False;self.face_wait_last=None
                for i in (2,3,4):self.c.bus.write(i,46,self.c.motion_speed.to_bytes(2,'little'))
                return
        target=self.target if self.phase=='look' else self.return_pose if self.phase=='return' else self.stage_target
        arrived=all(not r['speed_raw'] and not r['moving_raw'] and abs(r['position_raw']-target[r['id']])<=self.c.normal_tolerances[r['id']] for r in rows if not(self.head_tracking_active and self.phase=='lean' and r['id'] in (1,5)))
        self._check_settling(rows,target,arrived)
        self.stable=self.stable+1 if arrived else 0
        if self.stable<3:return
        if self.phase=='look':self.return_normal()
        elif self.remaining_steps:
            if self.phase=='return' and getattr(self.c,'interest_head_tracking',False) and not getattr(self.c,'face_ready_for_interest',False) and not getattr(self.c,'interest_finish_without_face',False):
                self._mark_player_wait()
                return  # Existing Interested timer bounds this player wait.
            self.waiting_for_player=False;self.face_wait_last=None
            self.phase,self.stage_target=self.remaining_steps.pop(0);self.stable=0
            self.head_tracking_active=self.phase=='lean' and getattr(self.c,'interest_head_tracking',False)
            if self.head_tracking_active:
                self.c.interest_pitch_window=getattr(self.c,'interest_pitch_window_request',None)
                for i,window in ((1,self.c.yaw_window),(5,self.c.active_pitch_window())):
                    low,high=self.path_windows[i]
                    self.path_windows[i]=(min(low,window[0]-6),max(high,window[1]+6))
                self.c.pose_route_windows=dict(self.path_windows);self.c.bus.windows.update(self.path_windows)
            for i in sorted(self.c.normal):self.c.bus.write(i,46,self.c.motion_speed.to_bytes(2,'little'))
            self.send(self.stage_target)
        else:
            if self.native_lean_time is not None:
                restore=(2,3,4) if getattr(self.c,'interested_gentle_entry',False) is True and getattr(self,'completion_behavior',None)!='angry' else (2,3)
                for sid in restore:self.c.bus.write(sid,46,self.c.motion_speed.to_bytes(2,'little'))
            self.phase='complete';self.c.pose_route_windows=None
            self.c.bus.windows.update(self.previous_bus_windows)
            if self.force_normal:
                for i in list(getattr(self.c,'behavior_joint_windows',{})):
                    getattr(self.c,'behavior_joint_windows',{}).pop(i,None)
                    getattr(self.c,'behavior_joint_allowances',{}).pop(i,None)
                self.c.behavior_pitch_window=None;self.c.sleepy_return_pending=False
                self.c.bus.windows.update(self.c.windows)
                self.c.bus.windows[1]=self.c.yaw_window;self.c.bus.windows[5]=self.c.pitch_window
            elif self.final_windows:
                self.c.behavior_joint_windows={**getattr(self.c,'behavior_joint_windows',{}),**self.final_windows}
                # final_windows already contain the full reviewed tolerance.
                self.c.behavior_joint_allowances={**getattr(self.c,'behavior_joint_allowances',{}),**{i:0 for i in self.final_windows}}
                self.c.bus.windows.update(self.final_windows)
    def _mark_player_wait(self):
        now=self.c.last_tick
        if self.face_wait_last is not None:self.gaze_wait_elapsed_s+=max(0.,now-self.face_wait_last)
        self.face_wait_last=now;self.waiting_for_player=True
    def _check_settling(self,rows,target,arrived):
        if arrived and self.stable>=2:self.settle_progress=None;return
        watched=[r for r in rows if not(self.head_tracking_active and self.phase=='lean' and r['id'] in (1,5))]
        key=(self.phase,tuple((r['id'],target[r['id']]) for r in watched))
        excess=sum(max(0,abs(r['position_raw']-target[r['id']])-self.c.normal_tolerances[r['id']]) for r in watched)
        now=self.c.last_tick;prior=self.settle_progress
        if prior is None or prior[0]!=key or excess<prior[1]:
            self.settle_progress=(key,excess,now);return
        if now-prior[2]>=5.:
            detail=', '.join(f"ID{r['id']} error={abs(r['position_raw']-target[r['id']])} tol={self.c.normal_tolerances[r['id']]} moving={r['moving_raw']}" for r in watched)
            # NormalGaze's existing exception path holds all axes and cancels
            # this route. Never fake completion or enlarge physical tolerances.
            raise RuntimeError('Pose settle stalled '+self.phase+': '+detail)
    def cancel(self):self.phase='cancelled';self.head_tracking_active=False
