"""Single UART owner worker; display never waits for servo reads or writes."""
import json
import math
import threading
import time
from collections import deque
from pathlib import Path
from bio_inspire.runtime.happy_height_probe import head_snapshot
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'shared'/'runtime'))
from normal_gaze_motor import NormalGaze,open_bus
from visual_servo import VisualServo
from manual_tuning import validate_values,read_values,apply_values,trajectory_speed_limit,apply_group_pid_trial,ensure_base_pid


def diagnostic_trace_capacity(value):
    if type(value)is not int or value not in (40,180,600,2400):raise ValueError('Unbounded diagnostic trace')
    return value


def next_control_deadline(previous,now):
    # Approved upper rate 20 Hz; late UART cycles never queue catch-up commands.
    return max(previous+.05,now)

def motor_status(controller,now,pending):
    c=controller;waiting=[]
    if c.state=='NORMAL_STARTUP':
        for r in c.last_rows:
            sid=r['id'];error=r['position_raw']-c.normal[sid];limit=c.normal_tolerances[sid]
            if abs(error)>limit:waiting.append(f'ID{sid} error={error} limit={limit}')
            elif r['speed_raw'] or r['moving_raw']:waiting.append(f'ID{sid} moving')
    return dict(time_s=now,state=c.state,pending_behavior=pending,waiting=waiting,rows=c.last_rows,
                normal_raw=c.normal,normal_tolerances=c.normal_tolerances,error=getattr(c,'last_error',''),
                route_phase=getattr(getattr(c,'pose_route',None),'phase',None))


class CameraMotor:
    def __init__(self,profile,initial_joint=None,operator_start=False,park_only=False):
        profile_bytes=Path(profile).read_bytes()
        config=json.loads(profile_bytes.decode('utf-8-sig'))
        from bio_inspire.runtime.awake_motion import validate as validate_awake
        self.fast_awake_trial=validate_awake(config)
        from bio_inspire.runtime.yaw_face_scan import validate as validate_yaw_scan
        self.yaw_face_scan_enabled=validate_yaw_scan(config)
        from bio_inspire.runtime.angry_behavior import validate_profile as validate_angry_profile
        validate_angry_profile(config)
        from bio_inspire.runtime.automatic_fsm import validate_approach_config
        self.approach_requires_face=validate_approach_config(config)
        from bio_inspire.runtime.session_recording import validate_recording
        self.lab07_recording_seconds=validate_recording(config)
        from bio_inspire.runtime.lab07_start_gate import validate_gate,ButtonStartGate
        self.lab07_start_gate=ButtonStartGate() if validate_gate(config) else None
        from bio_inspire.runtime.automatic_trial import validate as validate_automatic_trial,AutomaticTrial
        self.automatic_trial=AutomaticTrial(config.get('normal_ahm_condition')) if validate_automatic_trial(config) else None
        if type(park_only)is not bool or park_only and (not operator_start or config.get('boot_auto_start_approved') is not True or self.lab07_recording_seconds is not None):
            raise ValueError('Park-only requires explicit approved boot start')
        self.park_only=park_only
        self.lab07_condition=config.get('normal_ahm_condition')
        self.lab07_pair_id=config.get('lab07_pair_id','unassigned')
        self.lab07_profile_path=str(Path(profile).resolve())
        if self.lab07_recording_seconds is not None:
            from bio_inspire.runtime.session_recording import recording_metadata
            self.lab07_metadata=recording_metadata(profile_bytes)
        button_dynamic=config.get('button_look_dynamic_trial',False)
        if type(button_dynamic)is not bool or button_dynamic and (config.get('motion_speed_raw')!=600 or config.get('automatic_fsm_enabled') is not True):
            raise ValueError('Dynamic button requires existing600 automatic profile')
        from bio_inspire.runtime.normal_ahm import validate_trial_config,NormalAHM
        normal_ahm_condition=validate_trial_config(config)
        from bio_inspire.runtime.presentation_tempo import owner_class
        rhythm_owner_class=owner_class(config)
        self.presentation_normal_preserve_yaw=config.get('presentation_normal_preserve_yaw',False)
        self.presentation_angry_smooth=config.get('presentation_angry_smooth',False)
        self.presentation_angry_sync_positions=config.get('presentation_angry_sync_positions',False)
        self.presentation_angry_constant_speed25=config.get('presentation_angry_constant_speed25',False)
        self.presentation_angry_roll_deg=config.get('presentation_angry_roll_deg',6)
        self.presentation_led_breathing=config.get('presentation_led_breathing',False)
        self.presentation_startup_tof_recovery=config.get('presentation_startup_tof_recovery',False)
        from bio_inspire.runtime.normal_measurement import NormalMeasurement
        self.normal_measurement=NormalMeasurement.from_profile(config,profile)
        if config.get('sleepy_native_fold_enabled',False):
            from bio_inspire.runtime.sleepy_trial import sleepy_fold_values
            sleepy_fold_values(config.get('sleepy_native_fold_degrees',6),config.get('sleepy_native_fold_speed_raw',9))
        if type(config.get('sleepy_native_fold_enabled',False)) is not bool or (config.get('sleepy_native_fold_enabled',False) and not config.get('sleepy_deep_rest_enabled',False)):raise ValueError('Native Sleepy requires deep rest')
        if config.get('fsm_happy_timeout_s') is not None and (type(config['fsm_happy_timeout_s']) not in (int,float) or config['fsm_happy_timeout_s']!=7.):
            raise ValueError('Unreviewed Happy timeout')
        if config.get('angry_enabled') is True and (config.get('fsm_active_timeout_s')!=5.
                or config.get('fsm_motion_aware') is not True):
            raise ValueError('Angry requires5s motion-aware clock before opening hardware')
        taught=config.get('afraid_taught_pose_raw')
        if taught is not None:
            from bio_inspire.runtime.afraid_pose import validate_taught_pose
            if not isinstance(taught,dict) or set(taught)!=set(map(str,range(1,6))):raise ValueError('Recorded five-joint crouch required')
            taught=validate_taught_pose({int(k):v for k,v in taught.items()})
            if config.get('afraid_crouch_duration_s') not in ((3.,6.,10.) if self.fast_awake_trial else (6.,10.)):raise ValueError('Approved crouch duration required')
        self.afraid_taught_pose=taught
        self.afraid_crouch_duration_s=config.get('afraid_crouch_duration_s',10.)
        self.all_states_cpg_enabled=config.get('all_states_cpg_enabled') is True
        if type(config.get('sleepy_deep_rest_enabled',False)) is not bool:
            raise ValueError('Sleepy deep rest flag must be boolean')
        if config.get('sleepy_deep_rest_enabled',False) and (not config.get('all_states_cpg_enabled',False) or config.get('cpg_sleepy_amplitude_deg')!=2. or config.get('cpg_active_joint_ids')!=[2,3]):
            raise ValueError('Deep Sleepy requires existing two-joint breathing owner')
        self.automatic_fsm_enabled=config.get('automatic_fsm_enabled') is True
        if self.automatic_fsm_enabled and (config.get('fsm_active_timeout_s',2.) not in (2.,5.) or config.get('fsm_sleep_after_s',6.) not in (6.,10.)):
            raise ValueError('Automatic FSM uses approved timeout2s/5s / idle6s/10s')
        if self.automatic_fsm_enabled and (not self.all_states_cpg_enabled or any(config.get(k) is not True for k in ('physical_tof_enabled','physical_touch_enabled','physical_button_enabled'))):
            raise ValueError('Automatic FSM requires real inputs and five-state motion profile')
        if self.all_states_cpg_enabled and (config.get('small_happy_trial') is not True or config.get('afraid_cpg_enabled') is not True):
            raise ValueError('Five-state CPG requires approved Happy and Afraid drivers')
        if config.get('afraid_cpg_enabled') is True and (taught is None or config.get('afraid_pose_trial_enabled') is not True):
            raise ValueError('Afraid CPG requires approved taught crouch profile')
        if config.get('physical_tof_enabled') is True and not (config.get('afraid_pose_trial_enabled') is True and config.get('afraid_fold_down') is True):
            raise ValueError('ToF trial requires approved Afraid fold-down profile')
        if config.get('small_happy_trial') is True:
            from bio_inspire.runtime.small_happy_trial import validate_small_happy_profile
            validate_small_happy_profile(config)
        self.head_probe_joint_id=config.get('head_probe_joint_id',4)
        self.body_probe_selection_enabled=config.get('body_probe_selection_enabled') is True
        self.body_probe_pitch_follow_enabled=config.get('body_probe_pitch_follow_enabled') is True
        if self.body_probe_pitch_follow_enabled and not (self.body_probe_selection_enabled and config.get('vertical_tracking_enabled') is True):
            raise ValueError('Body pitch follow requires explicit body probe and approved vertical tracking')
        allowed_probes=(2,3,4,5) if self.body_probe_selection_enabled else (4,5)
        if type(self.head_probe_joint_id)is not int or self.head_probe_joint_id not in allowed_probes:raise ValueError('Unreviewed probe ID/profile')
        self.joint_mode=config.get('manual_joint_tuning') is True
        self.gaze_enabled=config.get('gaze_enabled',True) is True
        if initial_joint is not None:
            if not self.joint_mode or initial_joint not in (1,2,3,4,5):raise ValueError('Invalid manual initial joint')
            config['manual_tuning_id']=initial_joint
        self.tuning_enabled=config.get('manual_tuning') is True
        self.tuning_id=config.get('manual_tuning_id',1)
        if self.tuning_id not in ((1,2,3,4,5) if self.joint_mode else (1,5)):raise ValueError('Unreviewed tuning joint')
        self.pitch_range_deg=config.get('pitch_range_deg',3)
        self.pitch_clearance_confirmed=((self.pitch_range_deg==3 or config.get('interested_pitch_up_deg')==18) and config.get('gaze_pitch_up_deg') is None) or (config.get('gaze_pitch_up_deg')==30 and config.get('pitch_paths_operator_confirmed_up_deg')==30)
        self.pitch_probe_requested=set()
        self.yaw_clearance_confirmed=config.get('yaw_range_deg') not in (20,30) or config.get('yaw_paths_operator_confirmed_deg')==config.get('yaw_range_deg')
        self.yaw_probe_requested=set()
        self.yaw_follow_enabled=config.get('yaw_follow_enabled',True) is True
        self.pitch_enabled=config.get('vertical_tracking_enabled') is True
        self.pitch_direction=config.get('pitch_direction')
        if self.pitch_enabled and (self.pitch_direction!=1 or config.get('pitch_probe_enabled') is not True):
            raise ValueError('Reviewed pitch direction and probes required')
        tracking=(config.get('speed_raw'),config.get('acceleration_raw'),config.get('yaw_range_deg'))
        if self.tuning_enabled:
            reviewed_wide=(tracking==(200,3,20) and config.get('motion_speed_raw')==200) or (tracking in ((400,3,30),(600,3,30)) and config.get('motion_speed_raw') in (200,400,600))
            if type(tracking[0])is not int or not (reviewed_wide or (1<=tracking[0]<=100 or tracking[0]==config.get('motion_speed_raw')==200) and tracking[1:]==(3,10)):
                raise ValueError('Manual speed1..100 acc3 yaw10 only')
        elif tracking not in ((1,1,3),(3,3,10),(4,3,10)):raise ValueError('Unreviewed yaw tracking profile')
        normal={int(k):v for k,v in config['normal_raw'].items()}
        if normal!={1:2019,2:2837,3:2746,4:1997,5:2696}:raise ValueError('Normal differs from recorded pose')
        self.controller=NormalGaze(None,{int(k):v for k,v in config['origin_raw'].items()},normal,
                                  tracking_speed=tracking[0],tracking_acceleration=tracking[1],yaw_range_deg=tracking[2],
                                  manual_tuning=self.tuning_enabled,command_margin_ticks=config.get('command_margin_ticks',0),
                                  pitch_probe=config.get('pitch_probe_enabled',False),pitch_tracking=self.pitch_enabled,pitch_range_deg=self.pitch_range_deg,manual_joints=self.joint_mode,limb_range_deg=config.get('limb_range_deg',3),loaded_probe_deg=config.get('loaded_probe_deg'),motion_speed=config.get('motion_speed_raw',1),normal_tolerances={int(k):v for k,v in config.get('normal_tolerances_ticks',{}).items()},pitch_up_deg=config.get('gaze_pitch_up_deg'))
        self.range_deg=tracking[2];self.deadband_px=config.get('deadband_px',6)
        self.controller.fast_awake_trial=self.fast_awake_trial
        self.controller.interest_head_tracking=self.gaze_enabled and self.pitch_enabled
        self.controller.control_clock=self.now
        self.controller.interest_gaze_priority=config.get('interest_gaze_priority') is True
        self.controller.interested_gentle_entry=config.get('interested_gentle_entry',False)
        self.controller.interest_native_neck=config.get('interest_native_neck') is True
        self.controller.interest_native_body_speed_raw=config.get('interest_native_body_speed_raw')
        if self.controller.interest_native_body_speed_raw is not None:
            if (type(self.controller.interest_native_body_speed_raw)is not int or self.controller.interest_native_body_speed_raw not in ((17,600) if self.fast_awake_trial else (17,))
                    or not self.controller.interest_native_neck or not self.controller.interest_gaze_priority
                    or config.get('interest_body_acceleration_raw',1)!=1):
                raise ValueError('Unreviewed Interested native body trial')
        self.controller.interest_lean_speed_deg_s=config.get('interest_lean_speed_deg_s')
        if self.controller.interest_lean_speed_deg_s is not None and (type(self.controller.interest_lean_speed_deg_s) not in (int,float) or self.controller.interest_lean_speed_deg_s!=1.5):
            raise ValueError('Unreviewed Interested lean rate')
        self.interest_body_pitch_compensation=config.get('interest_body_pitch_compensation') is True
        self.native_posture_compensation=config.get('native_posture_compensation') is True
        self.controller.coordinated_pose_transitions=self.fast_awake_trial and self.native_posture_compensation
        self.interested_pitch_lead_ticks=config.get('interested_pitch_lead_ticks')
        if self.interested_pitch_lead_ticks is not None and (type(self.interested_pitch_lead_ticks)is not int or self.interested_pitch_lead_ticks!=34):
            raise ValueError('Unreviewed Interested head lead')
        self.controller.interest_body_acceleration_raw=config.get('interest_body_acceleration_raw',1)
        if type(self.controller.interest_body_acceleration_raw)is not int or self.controller.interest_body_acceleration_raw not in (1,3):
            raise ValueError('Unreviewed Interested body acceleration')
        if self.native_posture_compensation and (not self.gaze_enabled or not self.pitch_enabled
                or not self.interest_body_pitch_compensation or self.interested_pitch_lead_ticks!=34
                or config.get('motion_speed_raw')!=600 or config.get('gaze_pitch_up_deg')!=30):
            raise ValueError('Native posture requires reviewed600-speed awake gaze/body compensation profile')
        if (self.controller.interest_native_body_speed_raw is not None
                and (not self.interest_body_pitch_compensation or self.interested_pitch_lead_ticks!=34
                     or not self.controller.interest_head_tracking or config.get('interest_finish_without_face') is not True)):
            raise ValueError('Native Interested body requires compensated bounded head tracking')
        self.controller.face_ready_for_interest=False
        up=config.get('interested_pitch_up_deg',6)
        if type(up)is not int or up not in (6,18):raise ValueError('Unreviewed Interested pitch range')
        self.controller.sleepy_deep_rest_enabled=config.get('sleepy_deep_rest_enabled',False)
        self.controller.sleepy_native_fold_enabled=config.get('sleepy_native_fold_enabled',False)
        self.controller.sleepy_native_fold_degrees=config.get('sleepy_native_fold_degrees',6)
        self.controller.sleepy_native_fold_speed_raw=config.get('sleepy_native_fold_speed_raw',9)
        self.controller.interest_pitch_window_request=self.controller.pitch_window if config.get('gaze_pitch_up_deg')==30 else (normal[5]-(205 if up==18 else 68),normal[5]+68)
        max_speed=trajectory_speed_limit(tracking[0])
        max_accel=tracking[1]*8.7*4096/360
        margin=self.controller.command_margin_ticks
        self.visual=VisualServo(self.controller.yaw_window[0]+margin,self.controller.yaw_window[1]-margin,max_speed,max_accel,
                                config.get('filter_beta',.25),self.deadband_px,160.,.5)
        self.pitch_visual=(VisualServo(self.controller.pitch_window[0],self.controller.pitch_window[1],
                           trajectory_speed_limit(self.controller.motion_speed),8.7*4096/360,config.get('filter_beta',.25),self.deadband_px,90.,.5)
                           if self.pitch_enabled else None)
        if self.pitch_visual is not None:
            v=self.pitch_visual
            self.controller.lean_command_limits=(v.max_speed,v.max_acceleration,v.max_dt)
        from physical_touch import reviewed_touch_debounce
        self.touch_debounce_s=reviewed_touch_debounce(config.get('touch_debounce_s',.06))
        self.angry_normal_level=config.get('angry_normal_level',False)
        if type(self.angry_normal_level)is not bool:raise ValueError('Explicit Angry normal-level flag required')
        from bio_inspire.runtime.angry_approach import validate as validate_angry_approach
        self.angry_face_approach=validate_angry_approach(config)
        self.angry_approach_degrees=config.get('angry_approach_degrees',9)
        self.angry_head_up_deg=config.get('angry_head_up_deg',0)
        self.happy_dance_only=config.get('happy_dance_only',False)
        if type(self.happy_dance_only)is not bool or self.happy_dance_only and config.get('happy_dynamic_trial') is not True:
            raise ValueError('Happy dance-only requires explicit dynamic recipe')
        self.bus=open_bus();self.controller.bus=self.bus
        self.bus.sync_position_trial=config.get("small_happy_sync_position_trial") is True and config.get("small_happy_trial") is True
        self.bus.sync_roll_position_trial=config.get('happy_taught_center_trial') is True
        self.bus.presentation_all_state_sync_positions=config.get('presentation_all_state_sync_positions',False)
        # Same single health read per joint; diagnostic only adds internal
        # target/current bytes, without any extra position/control writes.
        self.bus.extended_feedback_diagnostic=config.get('small_happy_trial') is True
        self.bus.manual_tuning=self.tuning_enabled
        self.bus.manual_joint_mode=self.joint_mode
        self.controller.interest_finish_without_face=config.get('interest_finish_without_face') is True
        self.controller.button_look_speed_raw=config.get('button_look_speed_raw',1000)
        self.controller.button_look_dynamic_trial=button_dynamic
        self.controller.button_return_speed_raw=config.get('button_return_speed_raw',750)
        if self.controller.button_look_speed_raw not in (1000,1250) or self.controller.button_return_speed_raw not in ((600,750,1000) if self.fast_awake_trial else (750,1000)):
            raise ValueError('Unreviewed button glance speeds')
        self.bus.motion_speed=self.controller.motion_speed
        self.bus.yaw_speed400_trial=tracking in ((400,3,30),(600,3,30)) and self.controller.motion_speed in (200,400,600)
        self.follow_enabled=False;self.held=False;self.just_ready=False
        self.lock=threading.Lock();self.stopping=threading.Event()
        self.urgent_stop=threading.Event();self.finished=threading.Event();self.cleanup_confirmed=False
        self.bus.position_group_cancelled=lambda:(self.stopping.is_set() or self.urgent_stop.is_set()
            or getattr(self,'operator_stopped',False) or self.controller.state in ('FAULT','STOPPED','WAIT_TOF'))
        self.keys=[];self.latest_result=None;self.last_frame=self.now()
        self._view=dict(state='IDLE',ready=False,direction=None,follow=False,error='',feedback_ms=0.)
        self.behavior_trial='normal'
        self.active_goal=None;self.sleepy_trial_active=False;self.led_ring=None;self.pending_behavior=None
        self.state_leds_enabled=config.get('state_leds_enabled',False)
        self.status_path=Path(profile).with_name('last_camera_status.json');self.last_status_s=-1.;self.status_wait=[]
        self.physical_button=None;self.button_sequence=0;self.last_button_event=None
        self.physical_touch=None;self.touch_sequence=0;self.last_touch_event=None
        self.physical_distance=None;self.distance_view=None
        self.touch_required_for_happy=config.get("touch_required_for_happy",False)
        self.happy_yaw_enabled=config.get("happy_yaw_enabled",False)
        self.small_happy_trial=config.get('small_happy_trial') is True
        self.happy_expanded_trial=config.get('small_happy_expanded_trial') is True
        self.happy_taught_center_trial=config.get('happy_taught_center_trial',False)
        self.happy_taught_fast_trial=config.get('happy_taught_fast_trial',False)
        self.happy_dynamic_trial=config.get('happy_dynamic_trial',False)
        self.happy_wide_caps_trial=config.get('happy_wide_caps_trial',False)
        self.happy_taught_head_up_deg=config.get('happy_taught_head_up_deg',0)
        self.happy_height_probe_trial=config.get('happy_height_probe_trial',False)
        self.happy_height_probe_step_deg=config.get('happy_height_probe_step_deg',3)
        self.happy_height_probe_offset_ticks=0;self.happy_height_probe_events=[]
        self.afraid_pose_trial_enabled=config.get('afraid_pose_trial_enabled') is True
        self.afraid_fold_down=config.get('afraid_fold_down') is True
        self.happy_speed_raw=config.get('small_happy_speed_raw',400)
        self.happy_body_acceleration_raw=config.get('small_happy_body_acceleration_raw',1)
        self.head4_probe_enabled=config.get("head4_probe_enabled",False)
        self.head_probe_active=False
        self.operator_stopped=False;self.wake_serial=0;self.route_completion_seen=None
        self.interested_roll_due=None
        self.rhythm_driver=None
        self.afraid_rhythm_driver=None
        if config.get('afraid_cpg_enabled') is True:
            from bio_inspire.runtime.afraid_rhythm import AfraidRhythm
            self.afraid_rhythm_driver=AfraidRhythm()
        self.rhythm_normal_gaze_started=False
        if config.get('cpg_trial_enabled') is True and not self.joint_mode:
            from bio_inspire.runtime.body_rhythm import BodyRhythmDriver
            self.rhythm_driver=BodyRhythmDriver(normal_amplitude_deg=config.get('cpg_normal_amplitude_deg',1.),normal_amplitude_mode=config.get('cpg_normal_amplitude_mode','fixed'),variation_seed=config.get('cpg_variation_seed',0),interested_amplitude_deg=config.get('cpg_interested_amplitude_deg',1.),phi=config.get('cpg_phi_rad',.2),active_joint_ids=tuple(config.get('cpg_active_joint_ids',[2,3])),time_scale=config.get('cpg_time_scale',1.),sleepy_amplitude_deg=config.get('cpg_sleepy_amplitude_deg',0.),happy_amplitude_deg=config.get('cpg_happy_amplitude_deg',0.),happy_time_scale=config.get('cpg_happy_time_scale',.75),happy_body_excursion_deg=config.get('happy_body_excursion_deg'))
        if self.small_happy_trial:
            from bio_inspire.runtime.small_happy_trial import SmallHappyTrial
            self.rhythm_driver=SmallHappyTrial(time_scale=config.get('small_happy_time_scale',.5),expanded=config.get('small_happy_expanded_trial',False),roll_deg=config.get('small_happy_roll_deg',6),taught_center=self.happy_taught_center_trial,fast_trial=self.happy_taught_fast_trial,fast_period_s=config.get('happy_taught_fast_period_s',8.),head_up_deg=self.happy_taught_head_up_deg,height_probe=self.happy_height_probe_trial,probe_step_deg=self.happy_height_probe_step_deg,dynamic_trial=self.happy_dynamic_trial,wide_caps_trial=self.happy_wide_caps_trial)
        if self.all_states_cpg_enabled:
            from bio_inspire.runtime.state_rhythms import StateRhythms
            self.rhythm_driver=rhythm_owner_class(self.rhythm_driver,self.afraid_rhythm_driver,
                normal_ahm=None if normal_ahm_condition is None else NormalAHM(normal_ahm_condition),
                ahm_scope=config.get('ahm_scope','normal'))
            self.afraid_rhythm_driver=None  # Router is the only invocation path.
        self.automatic_fsm=None
        self.angry_enabled=config.get('angry_enabled') is True
        if self.automatic_fsm_enabled:
            from bio_inspire.runtime.automatic_fsm import AutomaticFSM
            self.automatic_fsm=AutomaticFSM(motion_aware=config.get('fsm_motion_aware') is True,
                                           active_timeout_s=config.get('fsm_active_timeout_s',2.),happy_timeout_s=config.get('fsm_happy_timeout_s'),
                                           sleep_after_s=config.get('fsm_sleep_after_s',6.),angry_enabled=self.angry_enabled,
                                           approach_requires_face=self.approach_requires_face,
                                           approach_scan_arrival=config.get('approach_scan_arrival',False))
        trace_samples=diagnostic_trace_capacity(config.get('diagnostic_trace_samples',40))
        self.normal_completed=False;self.fault_recorded=False;self.trace=deque(maxlen=trace_samples)
        from joint_motion_log import JointMotionLog
        self.motion_log=JointMotionLog(Path(profile).with_name('last_joint_motion.json')) if self.joint_mode else None
        from ready_hold_log import ReadyHoldLog
        self.ready_hold_log=(ReadyHoldLog(Path(profile).with_name('last_ready_hold.json'))
                             if config.get('observe_ready_hold') is True and not self.joint_mode else None)
        self.fault_path=Path(profile).with_name('last_joint_fault.json' if self.joint_mode else 'last_gaze_fault.json')
        self.stop_path=Path(profile).with_name('last_joint_stop.json' if self.joint_mode else 'last_gaze_stop.json')
        self._was_ready=False;self.watchdog=None
        self.tune_pending=None;self.tune_job=None;self.tune_status='V/A pauses incomplete Normal to tune; M retries' if self.joint_mode else 'M then READY to tune'
        self.tune_applied={};self.tune_history=[]
        self.tune_path=Path(profile).with_name('last_joint_tuning.json' if self.joint_mode else 'last_manual_tuning_ID5.json' if self.tuning_id==5 else 'last_manual_tuning.json')
        try:
            if config.get('physical_tof_enabled') is True:
                from physical_distance import PhysicalDistance
                from bio_inspire.runtime.distance_behavior import DistanceGate
                self.distance_gate=DistanceGate();self.physical_distance=PhysicalDistance()
                self.physical_distance.wait_first_sample()
            if operator_start:
                if self.joint_mode:raise ValueError('Operator M start is camera mode only')
                from startup_preflight import prepare_operator_start
                live_origin=prepare_operator_start(self.bus,config.get('startup_pid_by_id'),self.controller.normal_tolerances,self.controller.motion_speed)
                self.controller.origin=live_origin
                self.controller.windows={i:(min(live_origin[i],normal[i])-22,max(live_origin[i],normal[i])+22) for i in normal}
                print('OPERATOR_START_LIVE_POSE',live_origin,flush=True)
            if config.get('group_pid_trial') is True:
                report=apply_group_pid_trial(self.bus,Path(profile).with_name('group_pid_trial.json'))
                print('GROUP_PID',report['status'],flush=True)
            if config.get('restore_base_pid_on_start') is True:
                print('BASE_PID_START',ensure_base_pid(self.bus),flush=True)
            self.bus.tuning_id=self.tuning_id
            self.controller.active_joint_id=self.tuning_id
            if self.joint_mode and config.get('manual_connect_hold') is True:
                rows=self.bus.snapshot()
                self.controller.origin={r['id']:r['position_raw'] for r in rows}
                self.controller.windows={i:(min(self.controller.origin[i],normal[i])-22,max(self.controller.origin[i],normal[i])+22) for i in normal}
            from bio_inspire.runtime.session_recording import prepare_recorder
            self.lab07_recorder=prepare_recorder(self)
            start_kwargs={} if self.physical_distance is None else dict(pre_motion_check=self.physical_distance.require_fresh)
            self.controller.start(self.now(),hold_only=self.joint_mode and config.get('manual_connect_hold') is True,**start_kwargs)
            if config.get('physical_button_enabled') is True and not self.joint_mode:
                from physical_button import PhysicalButton
                # Same approved debounce as Lab06/07; no dependency on a ROS/lab checkout on Pi.
                if config.get('button_debounce_s',.06)!=.06:raise ValueError('Unreviewed button debounce')
                self.physical_button=PhysicalButton(.06)
                print('PHYSICAL_BUTTON GPIO27 active-low ready',flush=True)
            if config.get('physical_touch_enabled') is True and not self.joint_mode:
                from physical_touch import PhysicalTouch
                self.physical_touch=PhysicalTouch(self.touch_debounce_s)
                print('PHYSICAL_TOUCH GPIO22 active-high ready',flush=True)
            if self.tuning_enabled:self.tune_applied=read_values(self.bus,getattr(self,'tuning_id',1))
            if config.get('yaw_direction') in (-1,1):self.controller.set_direction(config['yaw_direction'])
            self.last_frame=self.now()
            self.watchdog=threading.Thread(target=self._run,name='gaze-UART-owner',daemon=False)
            self.watchdog.start()
        except BaseException:
            recorder=getattr(self,'lab07_recorder',None)
            if recorder is not None:recorder.close()
            self.stopping.set()
            if self.physical_distance is not None:
                try:self.physical_distance.close()
                except Exception as error:print('TOF_CLOSE_FAILED',str(error),flush=True)
            if self.physical_button is not None:self.physical_button.close();self.physical_button=None
            if self.physical_touch is not None:self.physical_touch.close();self.physical_touch=None
            self.controller.hold('startup interrupted',all_axes=True);self.bus.close()
            if self.watchdog is not None and self.watchdog.is_alive():self.watchdog.join(timeout=3)
            raise
    @staticmethod
    def now():return time.clock_gettime(time.CLOCK_BOOTTIME)
    def poll(self):
        with self.lock:
            self.last_frame=self.now();ready=self._view['ready']
            self.just_ready=ready and not self._was_ready;self._was_ready=ready
    def ready(self):
        with self.lock:return self._view['ready']
    def vision_ready(self):
        with self.lock:return self.normal_completed
    def fault_message(self):
        with self.lock:return self._view['error'] if self._view['state']=='FAULT' else ''
    def tuning_view(self):
        with self.lock:return dict(applied=dict(self.tune_applied),status=self.tune_status,joint_id=self.tuning_id)
    def request_tuning(self,values):
        if getattr(self,'normal_measurement',None) is not None:return False
        v=validate_values(values,getattr(self,'tuning_id',1))
        with self.lock:
            if not self.tuning_enabled:return False
            self.tune_pending=v;self.tune_pending_id=getattr(self,'tuning_id',1)
        return True
    def request_joint_tuning(self,sid,values):
        if getattr(self,'normal_measurement',None) is not None:return False
        v=validate_values(values,sid)
        with self.lock:self.tune_pending=v;self.tune_pending_id=sid
        return True
    def snapshot_view(self):
        with self.lock:return dict(self._view,route_phase=getattr(getattr(self.controller,'pose_route',None),'phase',None))
    def request_rhythm_amplitude(self,value):
        if getattr(self,'normal_measurement',None) is not None:return False
        from bio_inspire.runtime.body_rhythm import validate_manual_amplitude
        value=validate_manual_amplitude(value)
        if self.rhythm_driver is None or self.rhythm_driver.manual is None:return False
        with self.lock:self.rhythm_pending=value
        return True
    def rhythm_view(self):
        with self.lock:return dict(getattr(self,'rhythm_view_cache',{}))
    def _select_joint(self,sid):
        c=self.controller
        if sid not in (1,2,3,4,5) or c.state not in (('READY','FOLLOWING','STOPPED') if getattr(self,'joint_mode',False) else ('READY','FOLLOWING')):return
        if self.tune_job is not None or getattr(c,'pending_joint',None) is not None or any(r['speed_raw'] or r['moving_raw'] for r in c.last_rows):
            with self.lock:self.tune_status='Wait for move to finish, or H to stop before selecting'
            return
        actual=read_values(self.bus,sid)
        self.bus.tuning_id=sid;c.active_joint_id=sid;self.follow_enabled=False
        with self.lock:
            self.tuning_id=sid;self.tune_applied=actual;self.active_goal=None
            self.tune_status=f'ID{sid} selected (live readback); U/K/J or +/-/0'
    def _joint_key(self,key):
        c=self.controller
        if key==ord('m') and c.state=='STOPPED':
            if self.tune_job is not None or self.tune_pending is not None:
                with self.lock:self.tune_status='Wait for APPLIED, then M to retry Normal'
                return
            c.resume_normal(self.now())
            with self.lock:self.tune_status='Retrying Normal; H pauses, V restores selected PID'
            return
        if key in (ord('1'),ord('2'),ord('3'),ord('4'),ord('5')):
            self._select_joint(key-ord('0'));return
        if self.tune_job is not None:return
        if key in (ord('u'),ord('k'),ord('j')) and c.state in ('READY','FOLLOWING'):
            self.follow_enabled=False
            if c.probe_joint(self.tuning_id,1 if key==ord('u') else -1 if key==ord('k') else 0):
                self._refresh_goal()
                if getattr(self,'motion_log',None) is not None:
                    row=next(r for r in c.last_rows if r['id']==self.tuning_id)
                    self.motion_log.begin(self.tuning_id,row['position_raw'],self.active_goal['raw'],self.tune_applied,self.now())
                with self.lock:self.tune_status=f'SENT ID{self.tuning_id} goal={self.active_goal["raw"]} (readback OK)'
                print('JOINT_MOVE_ACK',self.tuning_id,self.active_goal['raw'],flush=True)
        elif key==ord('g'):
            with self.lock:self.tune_status='Manual only: U/K/J or +/-/0; no face following'

    def _service_tuning(self,now):
        if not self.tuning_enabled:return
        c=self.controller
        sid=getattr(self,'tuning_id',1)
        window=(c.windows[sid] if c.state=='STOPPED' else c.joint_windows[sid]) if getattr(self,'joint_mode',False) else c.pitch_window if sid==5 else c.yaw_window
        allowed_states=('READY','FOLLOWING','STOPPED') if getattr(self,'joint_mode',False) else ('READY','FOLLOWING')
        if self.stopping.is_set() or self.urgent_stop.is_set():
            self.tune_job=None;self.follow_enabled=False
            with self.lock:self.tune_pending=None;self.tune_status='CANCELLED by stop'
            return
        if self.tune_job is None:
            with self.lock:
                v=self.tune_pending;pending_id=getattr(self,'tune_pending_id',sid);self.tune_pending=None
            if v is not None and pending_id!=sid:
                with self.lock:self.tune_status='Not applied: selected joint changed; stage again'
                return
            if v is None:return
            if getattr(self,'joint_mode',False) and c.state=='NORMAL_STARTUP':
                c.state='STOPPED'
                if not c.hold('pause incomplete Normal for tuning',all_axes=True):raise RuntimeError('Startup pause unconfirmed')
            if c.state not in allowed_states:
                with self.lock:self.tune_status='Blocked: need live hold, no FAULT'
                return
            resume=self.follow_enabled;self.follow_enabled=False
            if not c.hold('pause gaze for manual tuning'):
                raise RuntimeError('Tuning hold unconfirmed')
            self.held=True;self.visual.position=None;self._reset_pitch()
            hold_goal=int.from_bytes(self.bus.read(sid,42,2),'little')
            self.tune_job=dict(values=v,resume=resume,deadline=now+5.,hold_goal=hold_goal,
                               positions=[],last_sample=None)
            with self.lock:self.tune_status=f'WAIT: ID{sid} stopping'
            return
        if c.state not in allowed_states:
            self.tune_job=None
            with self.lock:self.tune_status='Blocked by motor state'
            return
        if now>self.tune_job['deadline']:raise RuntimeError(f'ID{sid} did not settle for tuning')
        row=next(r for r in c.last_rows if r['id']==sid)
        job=self.tune_job
        if int.from_bytes(self.bus.read(sid,42,2),'little')!=job['hold_goal']:
            raise RuntimeError('Hold goal changed while waiting for tuning')
        sample=row['sampled_monotonic_s']
        if job['last_sample'] is not None and sample<=job['last_sample']:return
        job['last_sample']=sample
        if row['moving_raw'] or row['speed_raw']:
            job['positions']=[];return
        if not window[0]<=row['position_raw']<=window[1]:
            # The controller's separate feedback guard still enforces the
            # outer safety envelope. A near-edge tuning request is rejected,
            # not converted into a permanent motor fault. Never auto-recentre.
            self.tune_job=None;self.follow_enabled=False
            if c.state=='FOLLOWING':c.state='READY'
            centre='J' if sid!=1 else 'B'
            with self.lock:self.tune_status=f'Not applied: ID{sid} near edge; {centre}:centre then A'
            return
        # Standstill is measured from fresh encoder samples, not servo's
        # steady-state position error relative to its hold target.
        job['positions']=(job['positions']+[row['position_raw']])[-3:]
        if len(job['positions'])<3 or max(job['positions'])-min(job['positions'])>2:return
        job=self.tune_job
        try:
            actual=apply_values(self.bus,job['values'],lambda:self.stopping.is_set() or self.urgent_stop.is_set(),sid=sid)
        except BaseException:
            with self.lock:self.tune_status='FAILED: values unconfirmed';self.tune_applied={}
            raise
        if sid==1 and not getattr(self,'joint_mode',False):
            c.tracking_speed=actual['speed'];c.tracking_acceleration=3
            self.visual.max_speed=trajectory_speed_limit(actual['speed'])
        self.visual.position=None;self._reset_pitch();self.held=False
        self.follow_enabled=job['resume'] and not (self.stopping.is_set() or self.urgent_stop.is_set())
        self.tune_job=None
        with self.lock:
            self.tune_applied=actual;self.tune_status='APPLIED (readback OK)'
        self.tune_history=(self.tune_history+[dict(time_s=now,joint_id=sid,values=actual,trace=list(getattr(self,'trace',())))])[-40:]
        if self.tune_path is not None:
            try:self.tune_path.write_text(json.dumps(dict(history=self.tune_history),indent=2),encoding='utf-8')
            except OSError as error:print('TUNING_LOG_FAILED',str(error),flush=True)
    def apply(self,result):
        with self.lock:self.latest_result=result
    def key(self,key):
        if key==ord('f'):
            with self.lock:
                if len(self.keys)<8:self.keys.append(key)
            return
        if key not in (ord('i'),ord('s'),ord('n'),ord('d'),ord('h'),32,ord('t'),ord('y'),ord('b'),ord('1'),ord('2'),ord('g'),ord('u'),ord('j'),ord('k'),ord('c'),ord('3'),ord('4'),ord('5'),ord('m'),ord('p'),ord('o')):return
        if key in (ord('h'),32):self.urgent_stop.set()
        with self.lock:
            if key in (ord('h'),32):
                self.keys=[key];self.latest_result=None
            elif len(self.keys)<8:self.keys.append(key)
    def _refresh_goal(self):
        self.active_goal=dict(joint_id=self.tuning_id,raw=int.from_bytes(self.bus.read(self.tuning_id,42,2),'little'),read_s=self.now())
    def _observe_head_probe(self):
        recorder=getattr(self,'head_probe_recorder',None)
        if recorder is None:return
        try:
            if getattr(self,'operator_stopped',False) or not getattr(self,'head_probe_active',False):
                recorder.cancel('operator_stop_or_probe_ended')
                return
            face=(getattr(self,'latest_result',None) or {}).get('observation')
            completed=recorder.observe(self.now(),self.controller.last_rows,face,self.controller.state)
            if completed is not None:print('HEAD_PROBE_OBSERVATION',json.dumps(completed),flush=True)
        except Exception as error:
            # Diagnostics must not change goals, torque or controller state.
            self.head_probe_capture_error=str(error)
    def _publish(self,feedback_ms):
        c=self.controller
        if c.state=='FAULT' and getattr(self,'automatic_fsm',None) is not None:self.automatic_fsm.fault(self.now(),'motor_controller_fault')
        self._observe_head_probe()
        if getattr(self,'status_path',None) is not None and self.now()-self.last_status_s>=.5:
            report=motor_status(c,self.now(),getattr(self,'pending_behavior',None))
            report['physical_button_enabled']=getattr(self,'physical_button',None) is not None
            report['last_button_event']=getattr(self,'last_button_event',None)
            report['button_count']=getattr(self,'button_sequence',0)
            report['return_pose']=getattr(getattr(c,'pose_route',None),'return_pose',None)
            report['route_goals']=getattr(getattr(c,'pose_route',None),'last_sent_goals',None)
            report['route_force_normal']=getattr(getattr(c,'pose_route',None),'force_normal',False)
            report['head_tracking_during_lean']=getattr(getattr(c,'pose_route',None),'head_tracking_active',False)
            report['body_paused_for_face']=getattr(getattr(c,'pose_route',None),'paused_for_face',False)
            report['interested_face_centered']=getattr(c,'interest_face_centered',False)
            report['interested_gaze_wait_s']=getattr(getattr(c,'pose_route',None),'gaze_wait_elapsed_s',0.)
            report['behavior']=getattr(self,'behavior_trial','normal')
            route_status=getattr(getattr(c,'pose_route',None),'status',None)
            report['angry_approach']=route_status() if callable(route_status) else None
            report['pending_acceleration_restore']=dict(getattr(getattr(self.bus,'acceleration_restore',None),'pending',{}))
            report['touch_event']=getattr(self,'last_touch_event',None)
            report['touch_count']=getattr(self,'touch_sequence',0)
            report['digital_inputs']={}
            for channel in ('touch','button'):
                diagnostics=getattr(getattr(self,'physical_'+channel,None),'diagnostics',None)
                if callable(diagnostics):
                    value=diagnostics()
                    if isinstance(value,dict):report['digital_inputs'][channel]=value
            report['head4_probe_events']=getattr(self,'head_probe_events',[])
            if getattr(self,'happy_height_probe_trial',False):
                report['happy_height_probe_events']=list(getattr(self,'happy_height_probe_events',[]))
            recorder=getattr(self,'head_probe_recorder',None)
            report['head4_probe_samples']=[] if recorder is None else recorder.samples
            report['head4_probe_pending']=None if recorder is None else recorder.pending_reason
            report['head4_probe_capture_error']=getattr(self,'head_probe_capture_error',None)
            report['head_probe_active']=getattr(self,'head_probe_active',False)
            report['selected_probe_joint']=getattr(self,'head_probe_joint_id',None)
            report['probe_condition']='closed_loop_pitch_follow' if getattr(self,'body_probe_pitch_follow_enabled',False) else 'isolated_joint'
            report['follow_enabled']=self.follow_enabled
            report['distance']=getattr(self,'distance_view',None)
            # Read the existing producer cache even during operator hold;
            # telemetry only, never feed this bypass into FSM or motion.
            source=getattr(self,'physical_distance',None)
            raw_distance=None if source is None else source.latest()
            report['distance_sensor_raw']=raw_distance
            stamp=(raw_distance or {}).get('received_s')
            report['distance_sensor_age_s']=(self.now()-stamp if type(stamp) in (int,float) and math.isfinite(stamp) else None)
            report['fsm']=None if getattr(self,'automatic_fsm',None) is None else self.automatic_fsm.snapshot()
            report['crouch_progress']=getattr(getattr(c,'pose_route',None),'progress',None)
            report['face']=None if self.latest_result is None else self.latest_result.get('observation')
            report['pitch_goal_raw']=getattr(c,'last_pitch_goal',None)
            report['pitch_window']=c.active_pitch_window()
            report['pitch_search_status']=getattr(self,'pitch_search_status',None)
            report['interested_pitch_feedback_limited']=getattr(self,'interested_pitch_feedback_limited',False)
            report['native_posture_compensation']=getattr(self,'native_posture_compensation',False)
            posture=getattr(self,'interested_head_model',None)
            report['head_posture_reference_raw']=None if posture is None else posture.model.reference
            report['head_posture_uses_body_plan']=posture is not None and posture.planned_reference is not None
            rhythm=(getattr(self,'afraid_rhythm_driver',None) if getattr(self,'behavior_trial',None)=='afraid' else None) or getattr(self,'rhythm_driver',None)
            report['rhythm']=None if rhythm is None else rhythm.rhythm.status()
            self.status_wait=report['waiting'];self.last_status_s=self.now()
            try:
                temporary=self.status_path.with_suffix('.tmp')
                temporary.write_text(json.dumps(report),encoding='utf-8');temporary.replace(self.status_path)
                if getattr(self,'automatic_fsm',None) is not None:
                    self.automatic_fsm.save_csv(self.status_path.with_name('last_fsm_events.csv'),self)
            except OSError as error:print('STATUS_WRITE_FAILED',str(error),flush=True)
        if getattr(self,'joint_mode',False) and c.state in ('READY','NORMAL_STARTUP','STOPPED'):
            self._refresh_goal()
        if c.state=='FAULT':
            self.follow_enabled=False
            self._close_fault_inputs()
            if getattr(self,'led_ring',None) is not None:
                try:self.led_ring.close()
                except Exception as error:print('LED_OFF_FAILED',str(error),flush=True)
                self.led_ring=None
        with self.lock:
            if c.state in ('READY','FOLLOWING'):self.normal_completed=True
            if self.tuning_enabled and c.state=='READY' and self.tune_status=='M then READY to tune':
                self.tune_status='READY - G: follow, A: apply selected values'
            self._view=dict(behavior=getattr(self,'behavior_trial','normal'),emotion=(self.automatic_fsm.snapshot()['state'] if getattr(self,'automatic_fsm',None) is not None else getattr(self,'behavior_trial','normal')),state=c.state,ready=c.state in ('READY','FOLLOWING'),direction=c.direction,
                            follow=self.follow_enabled,error=c.last_error,feedback_ms=feedback_ms,
                            active_goal=getattr(self,'active_goal',None),distance=getattr(self,'distance_view',None),rows=[dict(r) for r in c.last_rows],joint_targets=dict(getattr(c,'last_joint_targets',{})))
            observation=None if self.latest_result is None else self.latest_result.get('observation')
        with self.lock:self._view['yaw_acquisition_scan']=dict(getattr(self,'yaw_scan_status',{}))
        gate=getattr(self,'lab07_start_gate',None)
        if gate is not None:
            status=gate.status();recorder=getattr(self,'lab07_recorder',None)
            status['elapsed_s']=0. if gate.started_s is None else max(0.,self.now()-gate.started_s)
            status['ceiling_s']=getattr(self,'lab07_recording_seconds',None)
            status['capture_finished']=bool(recorder is not None and recorder.end_seen)
            with self.lock:self._view['lab07_start_gate']=status
        trial=getattr(self,'automatic_trial',None)
        if trial is not None:
            with self.lock:self._view['automatic_trial']=trial.status(self.now())
        rhythm_cache=getattr(self,'rhythm_view_cache',{})
        self._record_trace(dict(time_s=self.now(),state=c.state,goal_raw=c.last_goal,
                               behavior=getattr(self,'behavior_trial','normal'),
                               crouch_progress=getattr(getattr(c,'pose_route',None),'progress',None),
                               happy_yaw_owner=rhythm_cache.get('yaw_owner'),
                               happy_search_remaining_s=rhythm_cache.get('search_remaining_s'),
                               happy_output_mode=rhythm_cache.get('small_happy'),
                               happy_gaze_mode=rhythm_cache.get('gaze_mode'),
                               happy_face_source_id=rhythm_cache.get('face_source_id'),
                               happy_face_status_used=rhythm_cache.get('face_status_used'),
                               happy_requested_float=rhythm_cache.get('requested_targets_float'),
                               happy_final_float=rhythm_cache.get('command_targets_float'),
                               happy_planned_motion=rhythm_cache.get('planned_motion'),
                               happy_height_probe=rhythm_cache.get('height_probe'),
                               happy_height_head=head_snapshot(self),
                               breathing_rhythm={k:rhythm_cache.get(k) for k in ('o1','o2','decoder_output_o1','decoder_phase_cycles','envelope','amplitude_deg_limit','command_offsets_deg','time_scale','dt_s','phi','normal_ahm','state_ahm')},
                               breathing_centers=dict(getattr(c,'rhythm_base_reference',{}) or {}),
                               sleepy_contraction_start_s=getattr(c,'sleepy_contraction_start_s',None),
                               sleepy_native_fold=dict(getattr(c,'sleepy_native_fold',None) or {}),
                               image_observation=observation,feedback_ms=feedback_ms,
                               distance=getattr(self,'distance_view',None),
                               trajectory_pos=self.visual.position,trajectory_vel=self.visual.velocity,follow_enabled=self.follow_enabled,
                               pitch_goal_raw=getattr(c,'last_pitch_goal',None),native_selected_goal=getattr(self,'active_goal',None),
                               joint_targets=dict(getattr(c,'last_joint_targets',{})),
                               button_event=getattr(self,'last_button_event',None),
                               rows=c.last_rows))
        recorder=getattr(self,'motion_log',None)
        if recorder is not None and recorder.active is not None:
            sid=recorder.active['joint_id'];row=next((r for r in c.last_rows if r['id']==sid),None)
            goal=getattr(self,'active_goal',None)
            if row is not None:
                recorder.sample(self.now(),row,getattr(c,'pending_joint',None)==sid,c.state,
                                goal['raw'] if goal and goal['joint_id']==sid else None)
        observer=getattr(self,'ready_hold_log',None)
        if observer is not None:
            observer.step(self.now(),c.state,self.follow_enabled or self.held,c.last_rows,
                          lambda:{i:int.from_bytes(self.bus.read(i,42,2),'little') for i in range(1,6)})
        if c.state=='FAULT' and not self.fault_recorded:
            self.fault_recorded=True
            report=dict(error=c.last_error,yaw_window=c.yaw_window,origin=c.origin,normal=c.normal,trace=list(self.trace))
            print('MOTOR_FAULT',c.last_error,flush=True)
            try:self.fault_path.write_text(json.dumps(report,indent=2),encoding='utf-8')
            except OSError as error:print('FAULT_REPORT_WRITE_FAILED',str(error),flush=True)
    def _reset_pitch(self):
        self.interested_head_model=None;self.interested_head_route=None
        self.posture_body_plan=None
        self.controller.interest_head_following_error=None
        if getattr(self,'pitch_visual',None) is not None:
            self.pitch_visual.position=None
            self.pitch_visual.low,self.pitch_visual.high=self.controller.active_pitch_window()
    def _apply_pitch(self,intent,obs,now,visible):
        if not getattr(self,'pitch_enabled',False):return
        c=self.controller
        from bio_inspire.runtime.interested_head import active,InterestedHead
        compensation=active(self)
        if compensation:
            route=getattr(c,'pose_route',None)
            if getattr(self,'interested_head_model',None) is None or getattr(self,'interested_head_route',None) is not route or self.pitch_visual.position is None:
                rows=c.last_rows;entry_pitch=getattr(route,'head_entry_pitch',None)
                if getattr(self,'behavior_trial',None)=='happy' and getattr(self,'happy_dance_only',False):
                    rows=[{**r,'position_raw':c.normal[r['id']]} if r['id'] in (2,3) else r for r in rows]
                    entry_pitch=c.normal[5]
                self.interested_head_model=InterestedHead(self.pitch_visual,rows,now,
                    entry_pitch=entry_pitch,native_posture=getattr(self,'native_posture_compensation',False))
                self.interested_head_route=route
                c.interest_head_following_error=self.interested_head_model.following_error
                c.interest_head_following_limit=getattr(self,'interested_pitch_lead_ticks',None)
        reacquire=getattr(self,'pitch_reacquire',False) and not visible
        if self.pitch_visual.position is None:
            if not visible and not reacquire:return
            actual=next(r['position_raw'] for r in c.last_rows if r['id']==5)
            self.pitch_visual.reset(max(self.pitch_visual.low,min(self.pitch_visual.high,actual)),now)
        error=self.pitch_direction*90*intent['error_xy'][1] if visible else None
        if reacquire:
            previous=getattr(self,'last_tracking_error_xy',(0.,-1.))[1]
            # Intentional bounded reacquisition, not a stale frame presented as
            # a fresh face. Preserve the last seen vertical exit direction.
            error=self.pitch_direction*90*previous
            actual=next(r['position_raw'] for r in c.last_rows if r['id']==5)
            v=self.pitch_visual
            if (error<0 and min(actual,v.position)<=v.low or
                    error>0 and max(actual,v.position)>=v.high):
                # The exit hypothesis cannot justify looking beyond reviewed
                # bounds. A fresh detected face can resume ordinary tracking.
                v.velocity=0.;v.filtered_error=0.
                self.pitch_search_status='limit_hold'
                if not compensation:v.time=now;return
                error=None
            else:self.pitch_search_status='recent_exit'
        else:self.pitch_search_status='visible' if visible else 'hold'
        measurement=(obs.get('source_id'),obs.get('captured_s'))
        if compensation:
            lead=getattr(self,'interested_pitch_lead_ticks',None)
            if lead is not None and abs(self.interested_head_model.following_error(c.last_rows))>lead:
                error=None  # Do not integrate transient error caused by body lag twice.
        body_target=None;reference_bias=0.
        if compensation and getattr(self,'native_posture_compensation',False):
            route=getattr(c,'pose_route',None)
            prediction=getattr(route,'head_compensation_target',None)
            if callable(prediction):
                body_target=prediction(c.last_rows)
                bias=getattr(route,'head_reference_bias',None)
                if callable(bias):reference_bias=bias()
            elif getattr(route,'measured_head_compensation',False):pass
            elif getattr(route,'phase',None)=='lean' and (getattr(route,'native_lean_started',False) or getattr(route,'completion_behavior',None)=='angry'):
                body_target=route.stage_target
                if getattr(c,'interested_gentle_entry',False) is True and getattr(route,'completion_behavior',None)!='angry':
                    # Match the slow arms' measured progress. Sending their
                    # whole endpoint pitches the faster head up before the
                    # body moves. Reuse the reviewed 34-tick postural lead.
                    actual={r['id']:r['position_raw'] for r in c.last_rows if r['id'] in (2,3)}
                    delta={i:body_target[i]-actual[i] for i in (2,3)}
                    remaining=sum(abs(v) for v in delta.values())
                    scale=min(1.,34/remaining) if remaining else 0.
                    body_target={i:actual[i]+math.trunc(delta[i]*scale) for i in (2,3)}
            else:
                plan=getattr(self,'posture_body_plan',None) or {}
                stamp=plan.get('time_s')
                if (plan.get('mode')==getattr(self,'behavior_trial',None) and type(stamp) in (int,float)
                        and math.isfinite(stamp) and 0<=now-stamp<=self.pitch_visual.max_dt):
                    body_target=plan.get('goals')
                    if plan.get('mode')=='happy' and getattr(self,'happy_taught_head_up_deg',0)==5:
                        reference_bias=plan.get('head_bias_ticks',0.)
        goal=(self.interested_head_model.step(c.last_rows,error,now,measurement,body_target=body_target,reference_bias_ticks=reference_bias) if compensation
              else round(self.pitch_visual.step(error,now,measurement)))
        self.interested_pitch_feedback_limited=False
        lead=getattr(self,'interested_pitch_lead_ticks',None)
        if lead is not None and not (compensation and getattr(self,'native_posture_compensation',False)) and getattr(self,'behavior_trial',None) in ('button_look','interested_transition','interested','angry_transition','angry'):
            v=self.pitch_visual;actual=next(r['position_raw'] for r in c.last_rows if r['id']==5)
            # Never obstruct a return from Sleepy's droop outside awake bounds.
            # Within awake bounds, prevent the image integrator running far
            # ahead of the measured head while the native servo catches up.
            if v.low<=actual<=v.high:
                bounded=max(max(v.low,actual-lead),min(min(v.high,actual+lead),goal))
                if bounded!=goal:
                    if compensation:self.interested_head_model.limit_feedback(bounded)
                    else:
                        v.position=float(bounded)
                        if v.velocity*(goal-bounded)>0:v.velocity=0.
                    goal=bounded;self.interested_pitch_feedback_limited=True
        if not (self.stopping.is_set() or self.urgent_stop.is_set()):
            commit=getattr(getattr(c,'pose_route',None),'commit_pending_head',None)
            if callable(commit) and commit(goal) is not None:return
            c.goal_pitch(goal)

    def _hold(self,reason,all_axes=False):
        self.pending_behavior=None
        self.last_tracking_seen_s=None
        self.controller.hold(reason,all_axes=all_axes);self.held=True;self.visual.position=None;self._reset_pitch()
    def _service_behavior_request(self):
        c=self.controller
        if getattr(self,'pending_behavior',None) is None:return
        if c.state in ('FAULT','STOPPED'):self.pending_behavior=None;return
        if c.state in ('READY','FOLLOWING'):
            if getattr(self,'automatic_fsm_enabled',False):
                from bio_inspire.runtime.three_state_behavior import handle_state_key
                expected={'normal':ord('n'),'interested':ord('i'),'happy':ord('d'),'sleepy':ord('s')}.get(self.automatic_fsm.fsm.state)
                if self.pending_behavior==expected:handle_state_key(self,self.pending_behavior)
                else:self.pending_behavior=None
            else:self._key(self.pending_behavior)
    def _close_fault_inputs(self):
        # Detach before close: the next owner tick must not poll a dead device
        # or overwrite the original fault with a cleanup exception.
        for name in ('physical_touch','physical_button'):
            device=getattr(self,name,None)
            if device is None:continue
            setattr(self,name,None)
            try:device.close()
            except Exception as error:print(name.upper()+'_CLOSE_FAILED',str(error),flush=True)

    def _poll_physical_touch(self,now,suppress=False):
        if self.controller.state=='FAULT':return False
        touch=getattr(self,'physical_touch',None)
        if touch is None or not touch.poll(now):return False
        self.touch_sequence+=1
        c=self.controller
        reason=('ignored_distance_priority' if suppress else
                'ignored_head_probe' if getattr(self,'head_probe_active',False) else
                'ignored_operator_stop' if getattr(self,'operator_stopped',False) else
                'ignored_afraid_until_clear' if getattr(self,'behavior_trial',None)=='afraid' else
                'ignored_not_ready' if c.state not in ('READY','FOLLOWING') else 'requested')
        self.last_touch_event=dict(source_id=f'touch_{self.touch_sequence:06d}',recognized_s=now,status=reason)
        print('PHYSICAL_TOUCH',json.dumps(self.last_touch_event),flush=True)
        if reason!='requested':return True
        self.pending_happy_from_touch=True;self.touch_dispatch_active=True
        try:self._key(ord('d'))
        finally:self.touch_dispatch_active=False
        return True
    def _poll_physical_button(self,now,suppress=False):
        if self.controller.state=='FAULT':return
        button=getattr(self,'physical_button',None)
        if button is None or not button.poll(now):return
        self.button_sequence+=1
        route=getattr(self.controller,'pose_route',None)
        reason=('ignored_head_probe' if getattr(self,'head_probe_active',False) else
                'ignored_touch_priority' if suppress else
                'ignored_operator_stop' if getattr(self,'operator_stopped',False) else
                'ignored_fault' if self.controller.state in ('FAULT','STOPPED') else
                'ignored_route_busy' if route is not None and route.phase in ('look','return','lean','tilt') else 'requested')
        self.last_button_event=dict(source_id=f'button_{self.button_sequence:06d}',recognized_s=now,status=reason)
        print('PHYSICAL_BUTTON',json.dumps(self.last_button_event),flush=True)
        if reason=='requested':self._key(ord('i'))
    def _finish_button_route(self):
        route=getattr(self.controller,'pose_route',None)
        if route is None or route.phase!='complete' or getattr(self,'route_completion_seen',None) is route:return
        self.route_completion_seen=route
        if getattr(route,'safety_hold',False):
            self.behavior_trial='angry';self.sleepy_trial_active=False;self.interested_roll_due=None
            self.follow_enabled=False;self.held=True;return
        if getattr(route,'force_normal',False):
            self.interested_roll_due=None
            self.rhythm_normal_gaze_started=False
            self.controller.state='READY'
            self.behavior_trial='normal';self.sleepy_trial_active=False;self.follow_enabled=False;self.held=True
            self.controller.behavior_pitch_window=None;self.controller.sleepy_return_pending=False
            if self.led_ring is not None and not getattr(self,'state_leds_enabled',False):self.led_ring.close();self.led_ring=None
            return
        self.behavior_trial=getattr(route,'completion_behavior','interested');self.sleepy_trial_active=False
        self.interested_roll_due=None if self.behavior_trial=='angry' else self.now()+2.
        restore=getattr(route,'angry_pitch_restore_window',None)
        if self.behavior_trial=='angry' and restore is not None:
            old=self.controller.active_pitch_window()
            self.controller.interest_pitch_window=restore
            self.controller.behavior_pitch_window=(min(old[0],restore[0]),max(old[1],restore[1]))
            self.controller.sleepy_return_pending=True
            route.head_entry_pitch=None  # Rebase from current pose inside the restored command window.
            self._reset_pitch()
        else:
            self.controller.behavior_pitch_window=None;self.controller.sleepy_return_pending=False
        self.controller.player_view_reference=None
        continuing=getattr(self,'follow_enabled',False) and getattr(route,'head_tracking_active',False)
        if not continuing:self.visual.position=None;self._reset_pitch()
        self.follow_enabled=continuing;self.held=not continuing
        if getattr(self,'gaze_enabled',True) and getattr(self,'pitch_enabled',False):
            if not continuing:self.controller.configure_tracking(yaw=getattr(self,'yaw_follow_enabled',True))
            self.follow_enabled=True;self.held=False
        print('BUTTON_LOOK returned to saved player view; gaze',self.follow_enabled,flush=True)
    def _service_body_rhythm(self):
        driver=getattr(self,'rhythm_driver',None)
        afraid=getattr(self,'afraid_rhythm_driver',None)
        if afraid is not None:
            afraid.step(self,self.now())
            if getattr(self,'behavior_trial',None)=='afraid':
                if driver is not None:driver.step(self,self.now())
                with self.lock:self.rhythm_view_cache=afraid.rhythm.status()
                return
        if driver is None:return
        with self.lock:
            pending=getattr(self,'rhythm_pending',None);self.rhythm_pending=None
        if pending is not None:driver.request_amplitude(pending,self.now())
        c=self.controller
        result=getattr(self,'latest_result',None) or {}
        obs=result.get('observation') or {};intent=result.get('intent') or {}
        stamp=obs.get('captured_s');now=self.now()
        missing_for_scan=(getattr(self,'yaw_face_scan_enabled',False) is True
                          and obs.get('status') in ('LOST','WAITING') and intent.get('mode')=='SEARCH'
                          and type(stamp) in (int,float) and math.isfinite(stamp) and 0<=now-stamp<=.5)
        if (not getattr(self,'rhythm_normal_gaze_started',False) and c.state in ('READY','FOLLOWING')
                and not getattr(self,'head_probe_active',False)
                and getattr(self,'behavior_trial','normal')=='normal' and (getattr(c,'face_ready_for_interest',False) or missing_for_scan)
                and getattr(self,'gaze_enabled',True) and getattr(self,'yaw_clearance_confirmed',True) and getattr(self,'pitch_clearance_confirmed',True) and not getattr(self,'operator_stopped',False)
                and not any(e is not None and e.is_set() for e in (getattr(self,'stopping',None),getattr(self,'urgent_stop',None)))):
            c.configure_tracking(yaw=getattr(self,'yaw_follow_enabled',True))
            self.visual.position=None;self._reset_pitch();self.follow_enabled=True;self.held=False
            self.rhythm_normal_gaze_started=True
        driver.step(self,self.now())
        with self.lock:self.rhythm_view_cache=driver.rhythm.status()
    def _reset_normal_ahm(self):
        driver=getattr(self,'rhythm_driver',None)
        reset=getattr(driver,'reset_normal_ahm',None)
        if callable(reset):
            reset(self.now())
            with self.lock:self.rhythm_view_cache=driver.rhythm.status()
    def _service_interested_roll(self):
        due=getattr(self,'interested_roll_due',None)
        if due is None:return
        c=self.controller
        if getattr(self,'behavior_trial','normal')!='interested' or c.state in ('FAULT','STOPPED'):
            self.interested_roll_due=None;return
        if self.now()<due:return
        low,high=c.behavior_joint_windows.get(4,(c.normal[4],c.normal[4]))
        c.behavior_joint_windows[4]=(min(low,c.normal[4]-22),max(high,c.normal[4]+22))
        c.behavior_joint_allowances[4]=0;self.bus.windows[4]=c.behavior_joint_windows[4]
        self.bus.write(4,46,c.motion_speed.to_bytes(2,'little'))
        self.bus.write(4,42,c.normal[4].to_bytes(2,'little'))
        c.current_roll_goal=c.normal[4]
        self.interested_roll_due=None
        route=getattr(c,'pose_route',None)
        if route is not None and route.phase=='complete':route.interested_upright_requested=True
        print('INTERESTED_ROLL returned upright; body and gaze preserved',flush=True)
    def _service_interested_gaze(self):
        route=getattr(self.controller,'pose_route',None)
        if (route is not None and route.phase=='lean' and getattr(route,'head_tracking_active',False)
                and getattr(self,'gaze_enabled',True) and not self.follow_enabled):
            self.controller.configure_tracking(yaw=getattr(self,'yaw_follow_enabled',True))
            self.visual.position=None;self._reset_pitch()
            yaw=getattr(route,'head_entry_yaw',None)
            if getattr(route,'completion_behavior',None)=='angry' and type(yaw)is int:
                self.visual.reset(max(self.visual.low,min(self.visual.high,yaw)),self.now())
                self.controller.goal_yaw(round(self.visual.position))
            self.follow_enabled=True;self.held=False
    def _key(self,key):
        if getattr(self,'automatic_trial',None) is not None:
            # A stopped/completed trial must be reopened with a fresh recorder.
            if key not in (ord('h'),ord(' '),ord('m')):return
            if key==ord('m') and self.automatic_trial.state!='waiting':
                self.tune_status='Reopen experiment for a new trial';return
        if getattr(self,'normal_measurement',None) is not None and key not in (ord('h'),ord(' '),ord('m')):return
        from bio_inspire.runtime.happy_height_probe import handle_key
        if handle_key(self,key):return
        if getattr(self,'automatic_fsm_enabled',False) and key in map(ord,'nisdf'):
            self.tune_status='AUTO FSM: use physical inputs';return
        if key in (ord('n'),ord('i'),ord('s'),ord('d'),ord('f')) and getattr(self,'physical_distance',None) is not None:
            from bio_inspire.runtime.distance_behavior import poll_distance
            handled=poll_distance(self,self.now())
            if handled or self.distance_gate.near or self.controller.state in ('FAULT','STOPPED'):return
            if key==ord('f'):return  # Automatic near is the entry authority.
        if key==ord('f'):
            from bio_inspire.runtime.afraid_pose import enter_afraid
            enter_afraid(self);return
        c=self.controller
        if (getattr(self,'small_happy_trial',False) and key in (ord('i'),ord('s'),ord('t'),ord('y'),ord('b'),ord('u'),ord('j'),ord('k'))
                and not (getattr(self,'all_states_cpg_enabled',False) and key in (ord('i'),ord('s')))):
            self.tune_status='Small Happy trial: Touch / Normal / Stop only';return
        from bio_inspire.runtime.head_roll_probe import handle_probe_key
        if handle_probe_key(self,key):return
        if getattr(self,'head_probe_active',False):
            if key not in (ord('n'),ord('h'),32):return
            self.head_probe_active=False
        if not getattr(self,'joint_mode',False) and key in (ord('n'),ord('i'),ord('s'),ord('d')):
            from bio_inspire.runtime.three_state_behavior import handle_state_key
            handle_state_key(self,key);return
        if getattr(self,'sleepy_trial_active',False) and key not in (ord('h'),32):return
        if key in (ord('h'),32):
            from bio_inspire.runtime.sleepy_trial import finish_sleepy_native_fold
            finish_sleepy_native_fold(self.controller)
            self.pending_behavior=None;self.pending_happy_from_touch=False;self.sleepy_entry_prepared=False
            self.interested_roll_due=None
            self.operator_stopped=True
            if getattr(self,'led_ring',None) is not None:self.led_ring.close();self.led_ring=None
            self.tune_job=None
            with self.lock:self.tune_pending=None;self.tune_status='STOPPED'
            if getattr(self,'joint_mode',False) and c.state=='NORMAL_STARTUP':c.state='STOPPED'
            self.follow_enabled=False;self._hold('operator stop',True)
            if c.state=='NORMAL_STARTUP':c.state='STOPPED'
        elif getattr(self,'joint_mode',False):self._joint_key(key)
        elif self.tune_job is not None:return
        elif getattr(self,'tuning_id',1)==5 and key in (ord('t'),ord('y'),ord('b'),ord('1'),ord('2')):
            self.tune_status='ID5 only: base probes disabled';return
        elif key==ord('c') and c.state in ('READY','FOLLOWING'):
            if not getattr(self,'yaw_clearance_confirmed',True):
                if getattr(self,'yaw_probe_requested',set())=={-1,1}:
                    self.yaw_clearance_confirmed=True;self.tune_status='ID1 paths operator-confirmed; G follows'
                else:self.tune_status='Inspect T/B/Y/B paths before C'
                return
            if getattr(self,'pitch_probe_requested',set())=={-1,1}:
                self.pitch_clearance_confirmed=True
                self.tune_status='Paths operator-confirmed; G: pitch follow'
            else:self.tune_status='Probe U and K, return J, inspect paths, then C'
        elif key in (ord('u'),ord('j'),ord('k')) and c.state in ('READY','FOLLOWING'):
            self.follow_enabled=False;self._hold('pause yaw for ID5 probe')
            if c.probe_pitch('negative' if key==ord('k') else key==ord('u')):
                if key in (ord('u'),ord('k')):self.pitch_probe_requested.add(1 if key==ord('u') else -1)
        elif key in (ord('t'),ord('y'),ord('b')) and c.state in ('READY','FOLLOWING'):
            self.follow_enabled=False
            if getattr(self,'pitch_enabled',False):self._hold('pause head for yaw probe')
            c.probe('negative' if key==ord('y') else key==ord('t'));self.visual.position=None;self._reset_pitch()
            if key in (ord('t'),ord('y')):self.yaw_probe_requested.add(1 if key==ord('t') else -1)
            if self.tuning_enabled:
                actual=read_values(self.bus,getattr(self,'tuning_id',1))
                with self.lock:self.tune_applied=actual
        elif key in (ord('1'),ord('2')) and c.state in ('READY','FOLLOWING'):
            self.follow_enabled=False;self._hold('pause before direction change')
            c.set_direction(1 if key==ord('1') else -1)
        elif key==ord('g') and c.state in ('READY','FOLLOWING') and c.direction is not None:
            if not getattr(self,'yaw_clearance_confirmed',True):
                self.tune_status='Inspect T/B/Y/B, then C before following';return
            if not getattr(self,'gaze_enabled',True):
                self.follow_enabled=False;self.tune_status='Gestures only: face following paused';return
            if not getattr(self,'pitch_clearance_confirmed',True):
                self.tune_status='Blocked: U / J / K / J inspect wires, then C';return
            if not self.follow_enabled:
                c.configure_tracking(yaw=getattr(self,'yaw_follow_enabled',True))
                if self.tuning_enabled:
                    actual=read_values(self.bus,getattr(self,'tuning_id',1))
                    with self.lock:self.tune_applied=actual
            self.follow_enabled=not self.follow_enabled;self.held=False;self.visual.position=None;self._reset_pitch()
            if not self.follow_enabled:self._hold('operator paused gaze')
    def _face_exit_memory(self,obs,intent,now,visible):
        # A short continuation hypothesis, never a synthetic face observation.
        # User-approved search memory and camera freshness both remain 0.5s.
        if visible:
            xy=intent.get('error_xy');stamp=obs.get('captured_s')
            if (isinstance(xy,(list,tuple)) and len(xy)==2
                    and all(type(v) in (int,float) and math.isfinite(v) and -1<=v<=1 for v in xy)
                    and type(stamp) in (int,float) and math.isfinite(stamp) and 0<=now-stamp<=.5):
                self.last_tracking_error_xy=tuple(xy);self.last_tracking_seen_s=stamp
            return False
        stamp=getattr(self,'last_tracking_seen_s',None)
        return (obs.get('status') in ('LOST','WAITING') and intent.get('mode')=='SEARCH'
                and type(stamp) in (int,float) and 0<=now-stamp<=.5
                and type(obs.get('captured_s')) in (int,float)
                and 0<=now-obs['captured_s']<=.5)
    def _apply_body_probe_pitch(self,result,now):
        # This supervised trial reuses the reviewed ID5 visual controller only.
        # It does not enable general gaze/CPG or apply an extrapolated Jacobian.
        enabled=(getattr(self,'body_probe_pitch_follow_enabled',False)
                 and getattr(self,'body_probe_selection_enabled',False)
                 and getattr(self,'head_probe_active',False)
                 and getattr(self,'head_probe_joint_id',None) in (2,3))
        if not enabled:return False
        c=self.controller
        if (getattr(self,'operator_stopped',False) or self.stopping.is_set() or self.urgent_stop.is_set()
                or c.state not in ('READY','FOLLOWING') or getattr(self,'behavior_trial','normal')!='normal'):return True
        obs=(result or {}).get('observation') or {};intent=(result or {}).get('intent') or {}
        captured=obs.get('captured_s');xy=intent.get('error_xy')
        visible=(obs.get('status') in ('TRACKING','ACQUIRED') and intent.get('mode')=='FOLLOW'
                 and type(captured) in (int,float) and math.isfinite(captured) and 0<=now-captured<=.5
                 and isinstance(xy,(tuple,list)) and len(xy)==2
                 and all(type(v) in (int,float) and math.isfinite(v) and -1<=v<=1 for v in xy))
        self.pitch_reacquire=self._face_exit_memory(obs,intent,now,visible)
        if not visible and not self.pitch_reacquire:
            self._reset_pitch()
            return True
        if not getattr(self,'pitch_enabled',False) or getattr(self,'pitch_visual',None) is None:return True
        self.pitch_visual.low,self.pitch_visual.high=c.active_pitch_window()
        self._apply_pitch(intent,obs,now,visible)
        return True
    def _record_trace(self,row):
        if getattr(getattr(self,'bus',None),'presentation_all_state_sync_positions',False) is True:
            row['last_position_group']=dict(getattr(self.bus,'last_position_group_report',{}))
        if getattr(self,'presentation_led_breathing',False) is True:
            row['presentation_led']=dict(getattr(self,'presentation_led_output',{}))
        route=getattr(getattr(self,'controller',None),'pose_route',None)
        if getattr(route,'coordinated_return',False):
            row['coordinated_pose']=dict(phase=route.phase,progress=route.return_progress,
                duration_s=getattr(route,'return_duration',None),start=getattr(route,'return_start',None),
                target=getattr(route,'motion_target',None))
        if getattr(route,'button_dynamic',False) and getattr(route,'phase',None) in ('look','return'):
            if getattr(self,'button_trace_route',None) is not route:
                self.button_trace_route=route
                self.button_look_trace=deque(maxlen=180);self.button_return_trace=deque(maxlen=180)
            row['button_glance_phase']=route.phase
            (self.button_look_trace if route.phase=='look' else self.button_return_trace).append(row)
        status=getattr(getattr(self.controller,'pose_route',None),'status',None) if hasattr(self,'controller') else None
        if callable(status):
            row['angry_approach']=status()
            if not hasattr(self,'angry_approach_trace'):self.angry_approach_trace=deque(maxlen=180)
            self.angry_approach_trace.append(row)
        start=row.get('sleepy_contraction_start_s')
        if row.get('behavior')=='sleepy' and type(start) in (int,float) and 0<=row['time_s']-start<=12.:
            if getattr(self,'sleepy_entry_epoch',None)!=start:
                self.sleepy_entry_epoch=start;self.sleepy_entry_trace=deque(maxlen=300)
            self.sleepy_entry_trace.append(row)
        row['yaw_acquisition_scan']=dict(getattr(self,'yaw_scan_status',{}))
        self.trace.append(row)
        if getattr(self,'lab07_recording_seconds',None) is not None:
            try:
                from bio_inspire.runtime.session_recording import record_owner
                record_owner(self,row)
            except Exception as error:
                self.lab07_recording_error=str(error);self.lab07_recording_seconds=None
                trial=getattr(self,'automatic_trial',None)
                if trial is not None:trial.abort(self,'record_owner_failed:'+str(error))
                print('LAB07_RECORDING_FAILED',str(error),flush=True)
        progress=row.get('crouch_progress')
        body_moving=any(r.get('speed_raw') or r.get('moving_raw') for r in row.get('rows',[]) if r.get('id') in (2,3,4))
        if (row.get('behavior')=='afraid' and row.get('state') in ('READY','FOLLOWING')
                and (type(progress) in (int,float) and progress<1. or body_moving)):
            if not hasattr(self,'afraid_motion_trace'):self.afraid_motion_trace=deque(maxlen=180)
            self.afraid_motion_trace.append(row)
        if (getattr(self,'small_happy_trial',False) and row.get('happy_output_mode')=='running'
                and row.get('state') in ('READY','FOLLOWING')):
            if not hasattr(self,'happy_motion_trace'):self.happy_motion_trace=deque(maxlen=180)
            self.happy_motion_trace.append(row)

    def _apply_small_happy_head(self,result,now):
        # SmallHappyTrial is the sole yaw producer, including during face loss.
        # Legacy hold(all_axes=False) also holds yaw and must not run here.
        if self.stopping.is_set() or self.urgent_stop.is_set() or getattr(self,'operator_stopped',False):return
        wake_goal=getattr(self,'happy_head_wake_goal',None)
        if wake_goal is not None:
            c=self.controller
            row=next((r for r in c.last_rows if r['id']==5),None)
            arrived=(row is not None and c.pitch_window[0]<=row['position_raw']<=c.pitch_window[1]
                     and abs(row['position_raw']-wake_goal)<=c.normal_tolerances[5]
                     and not row['speed_raw'] and not row['moving_raw'])
            if not arrived:
                c.goal_pitch(wake_goal);self.small_head_held=False;return
            self.happy_head_wake_goal=None;self._reset_pitch()
        if getattr(self,'happy_dance_only',False) and getattr(self,'native_posture_compensation',False):
            self.pitch_reacquire=False
            self._apply_pitch(dict(mode='HOLD',error_xy=None),(result or {}).get('observation') or {},now,False)
            return
        obs=(result or {}).get('observation') or {};intent=(result or {}).get('intent') or {}
        xy=intent.get('error_xy');stamp=obs.get('captured_s')
        visible=(obs.get('status') in ('TRACKING','ACQUIRED') and intent.get('mode')=='FOLLOW'
                 and type(stamp) in (int,float) and math.isfinite(stamp) and 0<=now-stamp<=.5
                 and isinstance(xy,(list,tuple)) and len(xy)==2
                 and all(type(x) in (int,float) and math.isfinite(x) and -1<=x<=1 for x in xy))
        self.pitch_reacquire=self._face_exit_memory(obs,intent,now,visible)
        if visible or self.pitch_reacquire:
            self._apply_pitch(intent,obs,now,visible);self.small_head_held=False
        else:
            if not getattr(self,'small_head_held',False):
                if self.stopping.is_set() or self.urgent_stop.is_set():return
                self.bus.hold_actual(5);self.controller.last_pitch_goal=None;self.small_head_held=True
            self._reset_pitch()

    def _apply(self,result,now):
        c=self.controller
        self.interested_pitch_feedback_limited=False
        from bio_inspire.runtime.yaw_face_scan import service as service_yaw_scan
        if service_yaw_scan(self,result,now):
            from bio_inspire.runtime.interested_head import active
            if active(self):
                self.pitch_reacquire=False
                self._apply_pitch(dict(mode='HOLD',error_xy=None),(result or {}).get('observation') or {},now,False)
            return
        if self._apply_body_probe_pitch(result,now):return
        if not getattr(self,'gaze_enabled',True):return
        if getattr(self,'joint_mode',False) or getattr(self,'head_probe_active',False):return
        if not self.follow_enabled or c.state not in ('READY','FOLLOWING'):return
        from bio_inspire.runtime.interested_head import active as interested_head_active,apply_gaze as apply_interested_gaze
        if interested_head_active(self):
            apply_interested_gaze(self,result,now);return
        if getattr(self,'afraid_pose_trial_enabled',False) and getattr(self,'behavior_trial','normal')=='afraid':
            from bio_inspire.runtime.afraid_pose import apply_afraid_gaze
            apply_afraid_gaze(self,result,now);return
        if (getattr(self,'small_happy_trial',False) and getattr(self,'behavior_trial','normal')!='afraid'
                and (not getattr(self,'all_states_cpg_enabled',False) or getattr(self,'behavior_trial',None)=='happy')):
            self._apply_small_happy_head(result,now);return
        if getattr(self,'behavior_trial','normal')=='sleepy':
            from bio_inspire.runtime.three_state_behavior import apply_sleepy_yaw
            apply_sleepy_yaw(self,result,now);return
        route=getattr(c,'pose_route',None)
        if route is not None and route.phase in ('look','return','lean','tilt') and not getattr(route,'head_tracking_active',False):return
        intent=None if result is None else result['intent']
        obs=None if result is None else result['observation']
        fresh=(obs is not None and 0<=now-obs['captured_s']<=.5)
        awake=fresh and result['state'] in ('normal','interested','happy','afraid')
        visible=awake and intent['mode']=='FOLLOW'
        lost=awake and intent['mode']=='SEARCH' and obs.get('status') in ('LOST','WAITING')
        self.pitch_reacquire=awake and self._face_exit_memory(obs,intent,now,visible)
        if visible or lost:
            if not getattr(self,'yaw_follow_enabled',True):
                self._apply_pitch(intent,obs,now,visible)
                if c.state!='FAULT':c.state='FOLLOWING'
                self.held=False;return
            if self.visual.position is None:
                if lost and not self.pitch_reacquire:return
                actual=next(r['position_raw'] for r in c.last_rows if r['id']==1)
                self.visual.reset(max(self.visual.low,min(self.visual.high,actual)),now)
            error=c.direction*160*intent['error_xy'][0] if visible else (c.direction*160*self.last_tracking_error_xy[0] if self.pitch_reacquire else None)
            measurement=(obs.get('source_id'),obs['captured_s'])
            goal=round(self.visual.step(error,now,measurement))
            goal=max(c.yaw_window[0],min(c.yaw_window[1],goal))
            if self.stopping.is_set() or self.urgent_stop.is_set():return
            if getattr(self,'behavior_trial',None)=='happy' and getattr(self,'happy_yaw_enabled',False):
                self.happy_yaw_base=goal
                c.state='FOLLOWING';self._apply_pitch(intent,obs,now,visible)
            elif c.goal_yaw(goal):
                c.state='FOLLOWING';self._apply_pitch(intent,obs,now,visible)
            self.held=False
        elif not self.held:
            if route is not None and route.phase=='lean' and getattr(route,'head_tracking_active',False):
                for sid in (1,5):c.bus.hold_actual(sid)
                self.held=True;self.visual.position=None;self._reset_pitch()
            else:self._hold('no fresh awake-state face')
    def _run(self):
        deadline=self.now()
        try:
            while not self.stopping.is_set():
                now=self.now()
                with self.lock:
                    frame=self.last_frame;keys=self.keys;self.keys=[];result=self.latest_result
                if now-frame>.5 and self.controller.state not in (('FAULT',) if getattr(self,'joint_mode',False) else ('FAULT','STOPPED')):
                    self.follow_enabled=False;self._hold('manual UI stalled >0.5s' if getattr(self,'joint_mode',False) else 'camera processing stalled >0.5s',True)
                    self.controller.state='FAULT'
                for key in keys:self._key(key)
                obs=None if result is None else result.get('observation')
                self.controller.control_now_s=self.now()
                self.controller.interest_face_stamp=None if obs is None else obs.get('captured_s')
                self.controller.face_ready_for_interest=(obs is not None and obs.get('status') in ('ACQUIRED','TRACKING') and 0<=self.now()-obs.get('captured_s',-1)<=.5)
                xy=None if obs is None else obs.get('error_xy')
                self.controller.interest_vertical_error_px=None if not isinstance(xy,(tuple,list)) or len(xy)!=2 else abs(xy[1]*90)
                self.controller.interest_deadband_px=self.deadband_px
                self.controller.interest_face_centered=(self.controller.face_ready_for_interest
                    and ((result or {}).get('intent') or {}).get('mode')=='FOLLOW'
                    and isinstance(xy,(tuple,list)) and len(xy)==2 and abs(xy[1]*90)<=self.deadband_px
                    and obs['captured_s']>=getattr(self.controller,'lean_started_s',0.))
                t=time.perf_counter();self.controller.tick(self.now())
                feedback_ms=(time.perf_counter()-t)*1000
                if self.stopping.is_set():break
                with self.lock:
                    more_keys=self.keys;self.keys=[];result=self.latest_result
                if self.urgent_stop.is_set():
                    self._key(ord('h'));self.urgent_stop.clear();more_keys=[]
                for key in more_keys:self._key(key)
                self._service_tuning(self.now())
                if getattr(self,'park_only',False):
                    if getattr(self,'automatic_fsm',None) is not None:self.automatic_fsm.discard_inputs(self,'boot_normal_park')
                    self._publish(feedback_ms)
                    deadline=next_control_deadline(deadline,self.now())
                    self.stopping.wait(max(0,deadline-self.now()))
                    continue
                gate=getattr(self,'lab07_start_gate',None)
                if gate is not None and not gate.started:
                    from bio_inspire.runtime.distance_behavior import poll_distance
                    poll_distance(self,self.now(),dispatch=False)
                    route=getattr(self.controller,'pose_route',None)
                    if (self.distance_gate.near and getattr(route,'force_normal',False)
                            and getattr(route,'phase',None) in ('look','return','lean','tilt')):
                        self._hold('Lab07 waiting: clear nearby object',all_axes=True)
                        self.behavior_trial='distance_wait'
                    if (self.behavior_trial=='distance_wait' and self.controller.state in ('READY','FOLLOWING')
                            and not self.distance_gate.near
                            and not self.operator_stopped and not self.stopping.is_set() and not self.urgent_stop.is_set()):
                        from bio_inspire.runtime.three_state_behavior import handle_state_key
                        handle_state_key(self,ord('n'))
                    self._finish_button_route()
                    from bio_inspire.runtime.lab07_start_gate import begin_measurement
                    gate.observe(self,self.now())
                    if gate.started:begin_measurement(self,self.now())
                    from bio_inspire.runtime.three_state_behavior import service_state_outputs
                    service_state_outputs(self)
                    self._publish(feedback_ms)
                    deadline=next_control_deadline(deadline,self.now())
                    self.stopping.wait(max(0,deadline-self.now()))
                    continue
                if not self.stopping.is_set() and not self.urgent_stop.is_set():
                    if getattr(self,'normal_measurement',None) is not None:self.normal_measurement.service(self,self.now())
                    elif getattr(self,'automatic_fsm',None) is not None:self.automatic_fsm.service(self,self.now())
                    else:
                        from bio_inspire.runtime.distance_behavior import poll_distance
                        distance_event=poll_distance(self,self.now())
                        touch_event=self._poll_physical_touch(self.now(),suppress=distance_event)
                        self._poll_physical_button(self.now(),suppress=touch_event or distance_event)
                self._service_behavior_request()
                from bio_inspire.runtime.awake_motion import prepare_awake
                prepare_awake(self)
                self._service_interested_gaze()
                self._finish_button_route()
                self._service_interested_roll()
                if self.native_posture_compensation:self._service_body_rhythm()
                self._apply(result,self.now())
                if not self.native_posture_compensation:self._service_body_rhythm()
                from bio_inspire.runtime.three_state_behavior import service_state_outputs
                if not getattr(self,'joint_mode',False):service_state_outputs(self)
                self._publish(feedback_ms)
                if getattr(self,'normal_measurement',None) is not None:self.normal_measurement.record(self,self.now())
                deadline=next_control_deadline(deadline,self.now())
                self.stopping.wait(max(0,deadline-self.now()))
        except BaseException as error:
            trial=getattr(self,'automatic_trial',None)
            if trial is not None:trial.abort(self,'worker_exception:'+str(error),hold=False)
            if getattr(self,'normal_measurement',None) is not None:self.normal_measurement.worker_failed()
            self.controller.hold(str(error),all_axes=True);self.controller.state='FAULT'
            self._reset_normal_ahm()
            self.follow_enabled=False;self._publish(0.)
        finally:
            trial=getattr(self,'automatic_trial',None)
            if trial is not None and trial.state=='running':trial.abort(self,'Q_or_worker_exit_before_complete',hold=False)
            recorder=getattr(self,'lab07_recorder',None)
            if recorder is not None:
                try:recorder.close()
                except Exception as error:print('LAB07_RECORDING_CLOSE_FAILED',str(error),flush=True)
            if getattr(self,'normal_measurement',None) is not None:
                try:self.normal_measurement.close('operator_q_or_worker_exit')
                except Exception as error:print('NORMAL_MEASUREMENT_SAVE_FAILED',str(error),flush=True)
            self._reset_normal_ahm()
            from bio_inspire.runtime.sleepy_trial import finish_sleepy_native_fold
            try:finish_sleepy_native_fold(self.controller)
            except Exception as error:print('SLEEPY_SPEED_RESTORE_UNCONFIRMED',str(error),flush=True)
            closing_trace=list(self.trace)
            if getattr(self,'physical_distance',None) is not None:
                try:self.physical_distance.close()
                except Exception as error:print('TOF_CLOSE_FAILED',str(error),flush=True)
            if getattr(self,'physical_button',None) is not None:
                try:self.physical_button.close()
                except Exception as error:print('BUTTON_CLOSE_FAILED',str(error),flush=True)
            if getattr(self,'physical_touch',None) is not None:
                try:self.physical_touch.close()
                except Exception as error:print('TOUCH_CLOSE_FAILED',str(error),flush=True)
            if getattr(self,'led_ring',None) is not None:
                try:self.led_ring.close()
                except Exception as error:print('LED_OFF_FAILED',str(error),flush=True)
            observer=getattr(self,'ready_hold_log',None)
            if observer is not None:observer.finish('closed')
            try:self.cleanup_confirmed=self.controller.hold('motor worker stopped',all_axes=True)
            finally:
                try:self.bus.close()
                finally:
                    try:
                        if getattr(self,'stop_path',None) is not None:
                            self.stop_path.write_text(json.dumps(dict(trace=closing_trace,
                                sleepy_entry_trace=list(getattr(self,'sleepy_entry_trace',())),
                                happy_motion_trace=list(getattr(self,'happy_motion_trace',())),
                                afraid_motion_trace=list(getattr(self,'afraid_motion_trace',())),
                                angry_approach_trace=list(getattr(self,'angry_approach_trace',())),
                                button_look_trace=list(getattr(self,'button_look_trace',())),
                                button_return_trace=list(getattr(self,'button_return_trace',())),
                                cleanup_confirmed=self.cleanup_confirmed),indent=2),encoding='utf-8')
                    except OSError as error:print('STOP_REPORT_FAILED',str(error),flush=True)
                    finally:self.finished.set()
    def disconnect_for_retry(self):
        """No release: worker closes UART in finally even if power loss denied hold ACK."""
        self.stopping.set()
        if self.watchdog is not None:self.watchdog.join(timeout=10)
        if (self.watchdog is not None and self.watchdog.is_alive()) or not self.finished.is_set():
            raise RuntimeError('Old motor connection still closing; wait then retry M')

    def close(self):
        self.stopping.set()
        if self.watchdog is not None:
            self.watchdog.join(timeout=10)
            if self.watchdog.is_alive() or not self.finished.is_set() or not self.cleanup_confirmed:
                raise RuntimeError('Motor hold/close unconfirmed; support lamp and use physical power switch if needed')
    def label(self):
        with self.lock:v=dict(self._view)
        measurement=getattr(self,'normal_measurement',None)
        if measurement is not None:
            elapsed=0. if measurement.replay.started is None else max(0.,self.now()-measurement.replay.started)
            duration=measurement.replay.duration_s
            gate=getattr(self,'lab07_start_gate',None)
            start_info=(' buttons '+str(gate.count)+'/5' if gate is not None and not gate.started else '')
            return f"{v['state']} | MEASURE {measurement.replay.condition} {measurement.state}{start_info} {min(duration,elapsed):.0f}/{duration:.0f}s | H:stop Q:exit"
        route=getattr(self.controller,'pose_route',None)
        extra=(' button:'+route.phase) if route is not None else ''
        if getattr(self,'happy_height_probe_trial',False):
            return f"{v['state']} | HAPPY HEIGHT PROBE | Touch:start O:base P:ID2+{self.happy_height_probe_step_deg} H:stop Q:exit"
        if getattr(self,'small_happy_trial',False):extra+=' | SMALL HAPPY +/-3deg Touch:start H:stop N:normal'
        if getattr(self,'head4_probe_enabled',False):
            extra+=f' | O:centre P:ID{getattr(self,"head_probe_joint_id",4)}+3 N:exit'
            if getattr(self,'body_probe_selection_enabled',False):extra+=' 2/3:select'
            if getattr(self,'body_probe_pitch_follow_enabled',False):extra+=' ID5:pitch-follow'
        if getattr(self,'pending_behavior',None) is not None:extra+=' queued:'+{ord('i'):'INTERESTED',ord('s'):'SLEEPY',ord('n'):'NORMAL',ord('d'):'HAPPY'}.get(self.pending_behavior,'behavior')
        if v['state']=='NORMAL_STARTUP' and getattr(self,'status_wait',[]):extra+=' wait:'+self.status_wait[0]
        return f"{v['state']} follow={v['follow']} UART={v['feedback_ms']:.0f}ms"+extra
