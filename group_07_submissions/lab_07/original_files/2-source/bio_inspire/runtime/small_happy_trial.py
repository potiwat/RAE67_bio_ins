"""Opt-in Happy: continuous gaze center + CPG offsets, one position frame.

Body dance stays Normal +/-34 ticks; yaw sum uses reviewed wide gaze bounds.
Final floating command motion is velocity/acceleration limited before rounding.
These are command-space limits, not measured physical motion certification.
"""
import math
from bio_inspire.runtime.body_rhythm import BodyRhythm
from bio_inspire.runtime.happy_path import HappyReferencePath
from bounded_motion import BoundedMotion, MotionLimits
from visual_servo import VisualServo

def validate_small_happy_profile(config):
    from bio_inspire.runtime.taught_happy import validate
    validate(config)
    required_true=('gaze_enabled','vertical_tracking_enabled','physical_touch_enabled','touch_required_for_happy','small_happy_wide_gaze_trial')
    combined=config.get('all_states_cpg_enabled') is True
    if combined and any(config.get(k) is not True for k in ('yaw_follow_enabled','state_leds_enabled','physical_button_enabled','afraid_cpg_enabled','afraid_pose_trial_enabled')):
        raise ValueError('Combined state profile requires gaze, button, LEDs and taught Afraid CPG')
    required_false=('cpg_trial_enabled','head4_probe_enabled','body_probe_pitch_follow_enabled','body_probe_selection_enabled')
    if not combined:required_false+=('yaw_follow_enabled','state_leds_enabled','physical_button_enabled')
    if (any(config.get(k) is not True for k in required_true)
            or any(config.get(k) is not False for k in required_false)
            or (config.get('speed_raw'),config.get('motion_speed_raw'),config.get('acceleration_raw')) not in ((400,400,3),(600,600,3))
            or type(config.get('small_happy_speed_raw',400))is not int or config.get('small_happy_speed_raw',400) not in (400,750,1000)
            or config.get('small_happy_time_scale',.5) not in (.5,.75)
            or type(config.get('small_happy_body_acceleration_raw',1))is not int or config.get('small_happy_body_acceleration_raw',1) not in (1,3)
            or config.get('yaw_range_deg')!=30 or config.get('yaw_paths_operator_confirmed_deg')!=30):
        raise ValueError('Happy needs approved30deg wide gaze, one yaw owner, Touch and400/3; LEDs disabled')

    if type(config.get('small_happy_roll_deg',6))is not int or config.get('small_happy_roll_deg',6) not in (6,8) or (config.get('small_happy_roll_deg',6)==8 and not config.get('small_happy_expanded_trial',False)):raise ValueError('Unreviewed Happy roll')
    if type(config.get('small_happy_expanded_trial',False)) is not bool:raise ValueError('Happy expansion flag must be boolean')
    if config.get('small_happy_expanded_trial',False) and (config.get('small_happy_speed_raw')!=1000 or config.get('small_happy_body_acceleration_raw')!=3):raise ValueError('Expanded Happy needs approved1000/ACC3')
    if config.get('small_happy_speed_raw')==1000 and not config.get('small_happy_expanded_trial',False):raise ValueError('Happy1000 requires expanded trial')

class SmallHappyTrial:
    manual=None
    def __init__(self,time_scale=.5,expanded=False,roll_deg=6,taught_center=False,fast_trial=False,fast_period_s=8.,head_up_deg=0,height_probe=False,probe_step_deg=3,dynamic_trial=False,wide_caps_trial=False):
        if type(taught_center)is not bool or taught_center and not expanded:raise ValueError('Taught center requires expanded Happy')
        if type(fast_trial)is not bool or fast_trial and not taught_center:raise ValueError('Fast Happy requires taught center')
        if type(dynamic_trial)is not bool or dynamic_trial and (not fast_trial or fast_period_s not in (3.8,4.5,5.) or height_probe):
            raise ValueError('Dynamic Happy requires fast taught3.8or4.5or5s, no probe')
        if fast_period_s in (3.8,4.5) and not dynamic_trial:raise ValueError('3.8or4.5s requires dynamic Happy')
        if type(wide_caps_trial)is not bool or wide_caps_trial and (not dynamic_trial or fast_period_s!=3.8):
            raise ValueError('Wide Happy caps require dynamic3.8s')
        self.wide_caps_trial=wide_caps_trial
        self.dynamic_trial=dynamic_trial
        if type(fast_period_s) not in (int,float) or fast_period_s not in (3.8,4.5,5.,6.,8.) or fast_period_s!=8. and not fast_trial:
            raise ValueError('Fast Happy period must be3.8or4.5or5or6or8 in fast trial')
        if type(head_up_deg)is not int or head_up_deg not in (0,5) or head_up_deg and not fast_trial:
            raise ValueError('Happy head offset requires fast taught trial and0or5deg')
        if type(height_probe)is not bool or height_probe and (not fast_trial or fast_period_s!=8. or head_up_deg):
            raise ValueError('Height probe requires accepted8s fast Happy without head bias')
        self.height_probe=height_probe
        if type(probe_step_deg)is not int or probe_step_deg not in (3,6) or probe_step_deg!=3 and not height_probe:
            raise ValueError('Height observation step must be3or6 in explicit probe')
        self.probe_ticks=round(probe_step_deg*4096/360)
        self.head_up_ticks=round(head_up_deg*4096/360)
        self.fast_trial=fast_trial
        self.taught_center=taught_center
        from bio_inspire.runtime.taught_happy import PHASE_DIVISOR,ENTRY_SECONDS
        self.phase_divisor=PHASE_DIVISOR if taught_center else 1.
        self.entry_seconds=ENTRY_SECONDS if taught_center else 2.
        if fast_trial:
            from bio_inspire.runtime.taught_happy import FAST_PHASE_DIVISOR,FAST_ENTRY_SECONDS
            self.phase_divisor=FAST_PHASE_DIVISOR*fast_period_s/8.
            self.entry_seconds=(2. if fast_period_s==3.8 else 3.) if dynamic_trial else FAST_ENTRY_SECONDS
        if type(expanded)is not bool:raise ValueError('Happy expansion flag must be boolean')
        if type(roll_deg)is not int or roll_deg not in (6,8) or (roll_deg==8 and not expanded):raise ValueError('Unreviewed Happy roll')
        self.roll_ticks=91 if roll_deg==8 else 68
        self.expanded=expanded;self.yaw_ticks=68 if expanded else 34;self.body_ticks=51 if expanded else 34
        if expanded:time_scale=3.402/3.8
        if time_scale not in (.5,.75,3.402/3.8):raise ValueError('Only approved Happy cycle timing')
        self.rhythm=BodyRhythm(phi=.1,time_scale=time_scale);self.reference=HappyReferencePath()
        self.last_sent={};self.limiters={};self.gaze_center=None
        self.began=None;self.last_visible=None;self.was_active=False;self.last_error_xy=None
        self.rhythm.active_joint_ids=(1,2,3,4) if expanded else (1,2,3)
        self.rhythm.modulation_status=dict(condition='happy_continuous_gaze_limited_commands',amplitude_deg_limit=34*360/4096,command_offsets_deg={i:None for i in (1,2,3)},legacy_breathing_decoder_used=False)
    def request_amplitude(self,value,now):raise ValueError('Fixed approved +/-3deg dance trial')
    def _pause(self):
        self.was_active=False;self.limiters={};self.gaze_center=None
        self.body_contracted=set();self.body_inside={2:0,3:0}
    def step(self,m,now):
        c=m.controller
        cancelled=lambda:m.stopping.is_set() or m.urgent_stop.is_set() or getattr(m,'operator_stopped',False)
        route=getattr(c,'pose_route',None)
        active=(not cancelled() and c.state in ('READY','FOLLOWING') and getattr(m,'behavior_trial','normal')=='happy'
                and not getattr(m,'head_probe_active',False)
                and not (route is not None and route.phase in ('look','return','lean','tilt')))
        self.rhythm.advance(now,active)
        if not active:
            self._pause()
            self.rhythm.modulation_status={**self.rhythm.modulation_status,'small_happy':'inactive','output_held':True,'gaze_mode':'hold','search_remaining_s':None,'planned_motion':None,'requested_targets_float':None,'command_targets_float':None}
            if getattr(m,'behavior_trial','normal')!='happy':self.last_sent={};self.last_visible=None
            return
        result=getattr(m,'latest_result',None) or {};obs=result.get('observation') or {};intent=result.get('intent') or {}
        stamp=obs.get('captured_s');xy=intent.get('error_xy')
        dance_only=getattr(m,'happy_dance_only',False) is True
        fresh=type(stamp) in (int,float) and math.isfinite(stamp) and 0<=now-stamp<=.5
        visible=(not dance_only and fresh and obs.get('status') in ('TRACKING','ACQUIRED') and intent.get('mode')=='FOLLOW'
                 and isinstance(xy,(tuple,list)) and len(xy)==2
                 and all(type(v) in (int,float) and math.isfinite(v) and -1<=v<=1 for v in xy))
        if visible:self.last_visible=stamp;self.last_error_xy=tuple(xy)
        recent=self.last_visible is not None and 0<=now-self.last_visible<=.5
        searching=not dance_only and fresh and recent and obs.get('status') in ('LOST','WAITING') and intent.get('mode')=='SEARCH'
        # Ambiguity never selects a new face or searches; short ambiguity holds
        # the gaze input while the existing dance/command dynamics continue.
        grace=not dance_only and fresh and recent and obs.get('status')=='AMBIGUOUS' and intent.get('mode')=='HOLD'
        # Face detection gates gaze, not the autonomous bounded dance. A fresh
        # missing-face result is different from a stale/stalled camera stream.
        heartbeat=getattr(m,'last_frame',None)
        camera_alive=(type(heartbeat) in (int,float) and math.isfinite(heartbeat) and 0<=now-heartbeat<=.5)
        missing=(dance_only and (camera_alive or fresh) or fresh and (
                   (obs.get('status') in ('LOST','WAITING') and intent.get('mode')=='SEARCH')
                   or (obs.get('status')=='AMBIGUOUS' and intent.get('mode')=='HOLD')))
        if not (visible or searching or grace or missing):
            self._pause()
            self.rhythm.modulation_status={**self.rhythm.modulation_status,'small_happy':'paused_no_recent_face','output_held':True,'gaze_mode':'hold','search_remaining_s':None,'face_status_used':obs.get('status'),'face_source_id':obs.get('source_id'),'planned_motion':None,'requested_targets_float':None,'command_targets_float':None}
            return
        v=m.visual
        from bio_inspire.runtime.taught_happy import BODY_CENTERS,ROLL_BOUNDS
        centers=BODY_CENTERS if self.taught_center else c.normal
        roll_low,roll_high=ROLL_BOUNDS if self.taught_center else (c.normal[4]-self.roll_ticks,c.normal[4]+self.roll_ticks)
        roll_center=(roll_low+roll_high)/2;roll_span=(roll_high-roll_low)/2
        low,high=v.low,v.high
        body_acc=getattr(m,'happy_body_acceleration_raw',1)
        if type(body_acc)is not int or body_acc not in (1,3):raise ValueError('Unreviewed Happy body acceleration')
        body_bounds={i:(centers[i]-self.body_ticks,centers[i]+self.body_ticks) for i in (2,3)}
        if self.height_probe:body_bounds[2]=(body_bounds[2][0],max(body_bounds[2][1],centers[2]+self.probe_ticks))
        speed=1200. if self.wide_caps_trial else 800. if self.dynamic_trial else v.max_speed
        body_acc=16 if self.wide_caps_trial else 8 if self.dynamic_trial else body_acc
        if self.dynamic_trial:base_acc=8.7*4096/360
        else:base_acc=v.max_acceleration/3
        limits={1:MotionLimits(low,high,speed,base_acc*8 if self.wide_caps_trial else v.max_acceleration,v.max_dt),
                **{i:MotionLimits(*body_bounds[i],speed,base_acc*body_acc,v.max_dt) for i in (2,3)}}
        if self.expanded:
            actual_roll=next(r['position_raw'] for r in c.last_rows if r['id']==4)
            roll_entry=getattr(c,'happy_roll_entry_raw',actual_roll)
            limits[4]=MotionLimits(min(roll_low,roll_entry),max(roll_high,roll_entry),speed,base_acc*(24 if self.wide_caps_trial else 12 if self.dynamic_trial else 6 if self.fast_trial else 1),v.max_dt)
        entry=getattr(c,'happy_entry_targets',{}) if getattr(m,'automatic_fsm_enabled',False) else {}
        if entry:
            for i in (2,3):
                if i not in getattr(self,'body_contracted',set()):
                    k=limits[i];limits[i]=MotionLimits(min(k.low,entry[i]),max(k.high,entry[i]),k.speed,k.acceleration,k.max_dt)
        if not self.was_active:
            self.began=now
            self.resume_from={1:self.last_sent.get(1,getattr(m,'happy_yaw_base',c.normal[1])),
                              **{i:self.last_sent.get(i,entry.get(i,c.normal[i])) for i in (2,3)}}
            if self.expanded:self.resume_from[4]=self.last_sent.get(4,roll_entry)
            self.body_contracted=set();self.body_inside={2:0,3:0}
            self.limiters={i:BoundedMotion(q,now,limits[i]) for i,q in self.resume_from.items()}
            self.gaze_center=VisualServo(low+self.yaw_ticks,high-self.yaw_ticks,v.max_speed,v.max_acceleration,v.beta,v.deadband,v.half_width,v.max_dt)
            self.gaze_center.reset(max(low+self.yaw_ticks,min(high-self.yaw_ticks,self.resume_from[1])),now)
        self.was_active=True
        if c.direction not in (-1,1):raise ValueError('Reviewed yaw direction required')
        error=c.direction*160*(xy[0] if visible else self.last_error_xy[0]) if visible or searching else None
        center=c.normal[1] if dance_only else self.gaze_center.step(error,now,(obs.get('source_id'),stamp))
        x,y=self.reference.sample(self.rhythm.decoder_phase_cycles/self.phase_divisor).position
        vertical=(y-.5)/math.sqrt(1.25)
        t=max(0.,min(1.,(now-self.began)/self.entry_seconds));weight=t*t*(3-2*t)
        raw={1:center+self.yaw_ticks*x,2:centers[2]-self.body_ticks*vertical,3:centers[3]-self.body_ticks*vertical}
        if self.expanded:raw[4]=roll_center-roll_span*x
        probe_offset=getattr(m,'happy_height_probe_offset_ticks',0) if self.height_probe else 0
        if self.height_probe:
            if type(probe_offset)is not int or probe_offset not in (0,self.probe_ticks):raise ValueError('Height probe offset outside selected endpoint')
            raw={1:center,2:centers[2]+probe_offset,3:centers[3],4:c.normal[4]}
        requested={i:self.resume_from[i]+(raw[i]-self.resume_from[i])*weight for i in raw}
        floating={i:self.limiters[i].step(q,now) for i,q in requested.items()}
        if entry and weight>=1.:
            for i in (2,3):
                f=self.limiters[i];k=f.limits;p=f.position;speed=f.velocity
                lo,hi=body_bounds[i]
                room=hi-p if speed>=0 else p-lo
                if lo<=p<=hi and speed*speed/(2*k.acceleration)<=room:
                    f.limits=MotionLimits(lo,hi,k.speed,k.acceleration,k.max_dt);self.body_contracted.add(i)
        goals={i:round(q) for i,q in floating.items()}
        m.posture_body_plan=dict(mode='happy',time_s=now,goals={i:goals[i] for i in (2,3)},head_bias_ticks=-self.head_up_ticks*weight)
        if any(not limits[i].low<=q<=limits[i].high for i,q in goals.items()):raise ValueError('Rounded Happy command outside approved sum limits')
        c.behavior_joint_windows={**getattr(c,'behavior_joint_windows',{}),**{i:(body_bounds[i][0]-c.normal_tolerances[i],body_bounds[i][1]+c.normal_tolerances[i]) for i in (2,3)}}
        if entry:
            for i in (2,3):
                lo,hi=c.behavior_joint_windows[i]
                row=next(r for r in c.last_rows if r['id']==i)
                self.body_inside[i]=self.body_inside[i]+1 if i in self.body_contracted and lo<=row['position_raw']<=hi else 0
                if self.body_inside[i]<3:
                    old=c.happy_entry_feedback[i];c.behavior_joint_windows[i]=(min(lo,old[0]),max(hi,old[1]))
        if self.expanded:
            old_roll=getattr(c,'happy_entry_feedback',{}).get(4,(roll_entry,roll_entry))
            c.behavior_joint_windows[4]=(min(roll_low-c.normal_tolerances[4],roll_entry-c.normal_tolerances[4],old_roll[0]),max(roll_high+c.normal_tolerances[4],roll_entry+c.normal_tolerances[4],old_roll[1]))
        c.behavior_joint_allowances={**getattr(c,'behavior_joint_allowances',{}),2:0,3:0}
        if self.expanded:c.behavior_joint_allowances[4]=0
        for i in goals:c.bus.windows[i]=(limits[i].low,limits[i].high)
        changed=any(self.last_sent.get(i)!=q for i,q in goals.items());transport='unicast_goal_ack_readback'
        if getattr(c.bus,'sync_position_trial',False):
            transport='position_sync_write_then_per_joint_readback'
            if changed:
                sync_ids=(1,2,3,4) if self.taught_center else (1,2,3)
                self.last_sync_report=c.bus.sync_positions({i:goals[i] for i in sync_ids},cancelled)
                if self.expanded and not self.taught_center and not cancelled():c.bus.write(4,42,goals[4].to_bytes(2,'little'))
                self.last_sent.update(goals);c.last_goal=goals[1]
                for i in (2,3):c.last_joint_targets[i]=goals[i]
        else:
            for i,q in goals.items():
                if cancelled():return
                if self.last_sent.get(i)!=q:
                    c.bus.write(i,42,q.to_bytes(2,'little'));self.last_sent[i]=q
                    if i==1:c.last_goal=q
                    else:c.last_joint_targets[i]=q
        if self.expanded:
            c.current_roll_goal=goals[4];c.last_joint_targets[4]=goals[4]
        planned={i:dict(position_ticks=self.limiters[i].position,velocity_ticks_s=self.limiters[i].velocity,
                         max_speed_ticks_s=limits[i].speed,max_acceleration_ticks_s2=limits[i].acceleration) for i in goals}
        self.rhythm.modulation_status=dict(small_happy='running',joint_space_only=True,condition='happy_continuous_gaze_limited_commands',
            amplitude_deg_limit=self.body_ticks*360/4096,command_offsets_deg={i:(q-c.normal[i])*360/4096 for i,q in goals.items()},
            envelope=weight,output_held=False,legacy_breathing_decoder_used=False,requested_targets_float=requested,
            command_targets_float=floating,command_targets_raw=goals,planned_motion=planned,
            phase_cycles=self.rhythm.decoder_phase_cycles,transport=transport,sync_position_report=getattr(self,'last_sync_report',None),
            fade_weight=weight,head_control='ID5_posture_only' if dance_only else 'ID5_gaze_plus_ID1_gaze_and_dance',yaw_owner='fixed_center_plus_dance' if dance_only else 'gaze_plus_dance',gaze_center_raw=center,
            gaze_mode='dance_only' if dance_only else 'follow' if visible else 'recent_exit' if searching else 'ambiguity_hold' if grace else 'face_missing_hold',
            search_budget_s=.5,search_remaining_s=max(0.,.5-(now-self.last_visible)) if searching else None,
            face_source_id=obs.get('source_id'),face_status_used=obs.get('status'),control_now_s=now,requested_period_s_approx=3.402/self.rhythm.time_scale*self.phase_divisor,
            taught_center_trial=self.taught_center,body_centers_raw={i:centers[i] for i in (2,3)},roll_command_bounds_raw=(roll_low,roll_high),entry_seconds=self.entry_seconds,
            height_probe=dict(active=True,offset_ticks=probe_offset,cpg_output_paused=True) if self.height_probe else None)
