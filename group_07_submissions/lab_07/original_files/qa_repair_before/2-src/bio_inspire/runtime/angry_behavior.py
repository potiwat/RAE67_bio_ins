"""Approved Angry pose variants and red LED; same sole motor owner."""
import math

def validate_profile(config):
    """Check shared FSM dependencies before opening UART or creating inputs.

    Interested's native speed is independent of AngryApproachRoute's fixed17.
    """
    if config.get('angry_enabled') is not True:return
    allowed=(17,600) if config.get('fast_awake_trial') is True else (17,)
    native=config.get('interest_native_body_speed_raw')
    if (any(config.get(k) is not True for k in ('automatic_fsm_enabled','all_states_cpg_enabled',
            'interest_body_pitch_compensation','physical_touch_enabled','physical_tof_enabled'))
            or type(native)is not int or native not in allowed):
        raise ValueError('Angry requires automatic FSM, accepted native lean/head compensation and state CPG')

def enter_angry(m):
    c=m.controller
    if (not getattr(m,'angry_enabled',False) or c.state not in ('READY','FOLLOWING')
            or m.stopping.is_set() or m.urgent_stop.is_set() or getattr(m,'operator_stopped',False)):return False
    if not getattr(m,'yaw_clearance_confirmed',True) or not getattr(m,'pitch_clearance_confirmed',True):return False
    from bio_inspire.runtime.three_state_behavior import _small_happy_speed,_color
    from bio_inspire.runtime.button_look import begin_button_look
    source=getattr(m,'behavior_trial','normal')
    actual_pitch=next(r['position_raw'] for r in c.last_rows if r['id']==5)
    low,high=c.active_pitch_window()
    waking=(source=='sleepy' or getattr(m,'happy_head_wake_goal',None) is not None or not low<=actual_pitch<=high)
    view=getattr(m,'rhythm_view_cache',{}) or {}
    yaw=view.get('gaze_center_raw');stamp=view.get('control_now_s')
    player_yaw=(round(yaw) if source=='happy' and type(yaw) in (int,float) and math.isfinite(yaw)
                and type(stamp) in (int,float) and math.isfinite(stamp) and 0<=m.now()-stamp<=.5
                and c.yaw_window[0]<=yaw<=c.yaw_window[1] else None)
    m._hold('switch directly to angry',all_axes=True)
    if c.state=='FAULT':return False
    from bio_inspire.runtime.sleepy_trial import finish_sleepy_native_fold
    finish_sleepy_native_fold(c)
    from bio_inspire.runtime.awake_motion import prepare_awake
    prepare_awake(m,'angry_transition')
    if getattr(m,'small_happy_trial',False):_small_happy_speed(m,False)
    if source=='sleepy':m.wake_serial=getattr(m,'wake_serial',0)+1
    c.player_view_reference=None
    if getattr(m,'angry_normal_level',False):
        from pose_route import PoseRoute
        yaw=player_yaw if player_yaw is not None else next(r['position_raw'] for r in c.last_rows if r['id']==1)
        yaw=max(c.yaw_window[0],min(c.yaw_window[1],yaw))
        target={**c.normal,1:yaw}
        windows={i:(c.normal[i]-c.normal_tolerances[i],c.normal[i]+c.normal_tolerances[i]) for i in (2,3,4)}
        windows[5]=c.pitch_window
        if getattr(m,'angry_face_approach',False):
            from bio_inspire.runtime.angry_approach import AngryApproachRoute
            c.pose_route=AngryApproachRoute(m,target)
        else:
            c.pose_route=PoseRoute(c,target,target,final_windows=windows,level_only=True)
        c.pose_route.angry_level_started_s=m.now()
        c.pose_route.completion_behavior='angry'
    else:
        begin_button_look(c,look_at_button=False,neck_tilt=False)
        c.pose_route.completion_behavior='angry'
        c.pose_route.head_entry_yaw=player_yaw
        # Do not replace Happy's unfinished wake with a new reference anchored to
        # the sleeping head. Only the head reference wakes; no Normal body stage.
        c.pose_route.head_entry_pitch=c.normal[5] if waking else None
        if source=='happy' and not waking:
            # Preserve the already reviewed Happy aim while the high body folds
            # into the ordinary Angry lean; clamping it first loses the player.
            awake=c.active_pitch_window()
            c.pose_route.angry_pitch_restore_window=awake
            c.interest_pitch_window=(min(low,awake[0]),max(high,awake[1]))
            c.bus.windows[5]=c.interest_pitch_window
            c.pose_route.head_entry_pitch=actual_pitch
    m.pending_behavior=None;m.pending_happy_from_touch=False;m.sleepy_entry_prepared=False
    m.happy_head_wake_goal=None;m.interested_roll_due=None;m.sleepy_yaw_started=False
    m.behavior_trial='angry_transition';m.sleepy_trial_active=True;m.route_completion_seen=None
    m.visual.position=None;m._reset_pitch();m.follow_enabled=False;m.held=True
    c.last_error='';_color(m,'angry');return True
