"""Three supervised behaviors on the existing UART owner; not the course FSM."""

def handle_state_key(m,key):
    if key not in (ord('n'),ord('i'),ord('s'),ord('d')):return False
    c=m.controller
    if key!=ord('d'):m.pending_happy_from_touch=False
    if key==ord('d') and getattr(m,'touch_required_for_happy',False) and not (getattr(m,'touch_dispatch_active',False) or getattr(m,'pending_happy_from_touch',False)):
        m.tune_status='Happy: touch the physical sensor';return True
    if c.state in ('FAULT','STOPPED'):
        m.tune_status='Support lamp; M reconnects before behavior requests';return True
    if getattr(m,'operator_stopped',False) and key!=ord('n'):
        m.tune_status='Stopped: NORMAL explicitly resumes';return True
    if c.state=='NORMAL_STARTUP':m.pending_behavior=key;return True
    if c.state not in ('READY','FOLLOWING'):return True
    if key==ord('d'):
        return enter_happy(m)
    if key==ord('n'):
        from bio_inspire.runtime.sleepy_trial import finish_sleepy_native_fold
        finish_sleepy_native_fold(c)
        coordinate_return=(getattr(c,'coordinated_pose_transitions',False) is True or getattr(m,'happy_wide_caps_trial',False) is True)
        if getattr(m,'small_happy_trial',False):_small_happy_speed(m,False)
        if getattr(m,'afraid_pose_trial_enabled',False):m.yaw_follow_enabled=getattr(m,'all_states_cpg_enabled',False)
        from pose_route import PoseRoute
        m.pending_behavior=None;m.operator_stopped=False;m.sleepy_entry_prepared=False
        from bio_inspire.runtime.awake_motion import prepare_awake
        prepare_awake(m,'normal')
        m.interested_roll_due=None;m.sleepy_yaw_started=False
        m.follow_enabled=False;m.held=True;m.visual.position=None;m._reset_pitch()
        previous=getattr(c,'pose_route',None)
        if previous is not None:previous.cancel()
        c.pose_route=PoseRoute(c,c.normal,c.normal,normal_only=True,coordinated_return=coordinate_return)
        m.route_completion_seen=None;m.behavior_trial='normal_transition'
        m.sleepy_trial_active=True;c.last_error='';return True
    if key in (ord('i'),ord('s')) and getattr(m,'behavior_trial',None)=='happy' and getattr(m,'small_happy_trial',False):_small_happy_speed(m,False)
    if key==ord('i'):
        if not getattr(m,'yaw_clearance_confirmed',True):
            m.tune_status='Inspect T/B/Y/B, then C before Interested';return True
        if not getattr(m,'pitch_clearance_confirmed',True):
            m.tune_status='Inspect U/J/K/J, then C before Interested';return True
        route=getattr(c,'pose_route',None)
        if route is not None and route.phase in ('look','return','lean','tilt'):return True
        from bio_inspire.runtime.awake_motion import prepare_awake
        prepare_awake(m,'interested')
        from bio_inspire.runtime.sleepy_trial import finish_sleepy_native_fold
        finish_sleepy_native_fold(c)
        from bio_inspire.runtime.button_look import begin_button_look
        retry_reference=getattr(m,'interested_return_reference',None)
        if retry_reference is not None:
            c.player_view_reference=retry_reference;m.interested_return_reference=None
        elif getattr(m,'behavior_trial','normal')!='sleepy':c.player_view_reference=None
        glance=getattr(m,'fsm_input_kind',None)!='approach'
        begin_button_look(c,look_at_button=glance)
        m.pending_behavior=None;m.sleepy_entry_prepared=False;m.interested_roll_due=None
        m.sleepy_yaw_started=False
        if getattr(m,'behavior_trial','normal')=='sleepy':m.wake_serial=getattr(m,'wake_serial',0)+1
        m.follow_enabled=False;m.held=True;m.visual.position=None;m._reset_pitch()
        m.behavior_trial='button_look' if glance else 'interested_transition';m.sleepy_trial_active=True;c.last_error=''
        _color(m,'interested');return True
    if getattr(m,'behavior_trial','normal')=='sleepy':return True
    if not getattr(m,'sleepy_entry_prepared',False):
        fast_sleep=getattr(m,'fast_awake_trial',False) is True
        if fast_sleep:
            from bio_inspire.runtime.awake_motion import prepare_sleep
            prepare_sleep(m)
        route=getattr(c,'pose_route',None)
        busy=route is not None and route.phase in ('look','return','lean','tilt')
        player=(dict(route.return_pose) if busy else
                {i:int.from_bytes(c.bus.read(i,42,2),'little') for i in c.normal})
        m.sleepy_from_taught_happy=(getattr(m,'behavior_trial',None)=='happy' and getattr(m,'happy_taught_center_trial',False) is True)
        stable_body=({2:c.normal[2],3:c.normal[3]} if getattr(m,'behavior_trial',None)=='happy' and getattr(m,'small_happy_trial',False) else getattr(c,'rhythm_base_reference',None))
        if not busy:player.update(stable_body or {})
        c.player_view_reference=player
        m.follow_enabled=False;m.interested_roll_due=None
        m._hold('switch directly to sleepy',all_axes=busy or m.sleepy_from_taught_happy or fast_sleep)
        if c.state=='FAULT':return True
        c.sleepy_body_reference=({i:int.from_bytes(c.bus.read(i,42,2),'little') for i in (2,3)} if busy else
                                dict(stable_body or {i:int.from_bytes(c.bus.read(i,42,2),'little') for i in (2,3)}))
        m.sleepy_interrupt_wait=busy or m.sleepy_from_taught_happy or fast_sleep;m.sleepy_entry_prepared=True
        m.behavior_trial='sleepy_transition';m.visual.position=None;m._reset_pitch()
        if m.sleepy_from_taught_happy:
            low,high=c.feedback_window(4);q=c.normal[4];tol=c.normal_tolerances[4]
            c.behavior_joint_windows={**getattr(c,'behavior_joint_windows',{}),4:(min(low,q-tol),max(high,q+tol))}
            c.behavior_joint_allowances={**getattr(c,'behavior_joint_allowances',{}),4:0}
            c.bus.windows[4]=c.behavior_joint_windows[4]
            c.bus.write(4,42,q.to_bytes(2,'little'));c.current_roll_goal=q
    if m.sleepy_interrupt_wait:
        rows=c.bus.snapshot()
        if any(r['speed_raw'] or r['moving_raw'] for r in rows):m.pending_behavior=key;return True
        if getattr(m,'fast_awake_trial',False):
            from bio_inspire.runtime.awake_motion import sleep_ready
            if not sleep_ready(m):m.pending_behavior=key;return True
        if getattr(m,'sleepy_from_taught_happy',False):
            roll=next(r for r in rows if r['id']==4)
            if abs(roll['position_raw']-c.normal[4])>c.normal_tolerances[4]:
                m.pending_behavior=key;m.tune_status='Returning wrist upright before Sleepy';return True
            q=c.normal[4];tol=c.normal_tolerances[4]
            c.behavior_joint_windows[4]=(q-tol,q+tol)
            c.bus.windows[4]=c.behavior_joint_windows[4]
    from bio_inspire.runtime.sleepy_trial import set_sleepy_trial
    try:set_sleepy_trial(c,True)
    except RuntimeError as error:
        m.pending_behavior=key;m.tune_status=str(error);return True
    if m.sleepy_interrupt_wait and not getattr(m,'sleepy_from_taught_happy',False):
        # A cancelled route never installs its final pose windows. Preserve
        # the actual held body/roll references before dropping its path guard.
        held={**c.sleepy_body_reference,4:int.from_bytes(c.bus.read(4,42,2),'little')}
        c.behavior_joint_windows={**getattr(c,'behavior_joint_windows',{}),
                                  **{i:(goal-c.normal_tolerances[i],goal+c.normal_tolerances[i]) for i,goal in held.items()}}
        c.behavior_joint_allowances={**getattr(c,'behavior_joint_allowances',{}),**{i:0 for i in held}}
        c.bus.windows.update(c.behavior_joint_windows)
        c.current_roll_goal=held[4]
    c.pose_route_windows=None
    c.bus.windows[1]=c.yaw_window
    m.pending_behavior=None;m.sleepy_entry_prepared=False;m.sleepy_yaw_started=False
    m.behavior_trial='sleepy';m.sleepy_trial_active=True;m.held=True;c.last_error=''
    if getattr(c,'sleepy_deep_rest_enabled',False):
        c.sleepy_native_fold=None
        c.sleepy_contraction_start_s=m.now()
        c.sleepy_entry_positions={r['id']:r['position_raw'] for r in c.last_rows}
        if getattr(c,'sleepy_native_fold_enabled',False) and getattr(c,'sleepy_native_fold_degrees',6)==12:
            # A larger Happy center is not permission to add another12deg
            # beyond it. Retarget directly to the old Sleepy absolute endpoint.
            c.sleepy_body_reference[3]=(c.normal[3] if getattr(m,'sleepy_from_taught_happy',False)
                                       else c.sleepy_entry_positions[3])
        m.follow_enabled=False;m.sleepy_yaw_started=False
    _color(m,'sleepy');return True


def _color(m,state):
    if m.led_ring is None:
        from led_ring import LedRing
        m.led_ring=LedRing()
    getattr(m.led_ring,state)();m.last_led_behavior=state


def service_state_outputs(m):
    c=m.controller
    gate=getattr(m,'lab07_start_gate',None)
    if c.state in ('FAULT','STOPPED') or getattr(m,'operator_stopped',False) or gate is not None and not gate.started:
        if m.led_ring is not None:m.led_ring.close();m.led_ring=None
        m.last_led_behavior=None;return
    state=getattr(m,'behavior_trial','normal')
    if c.state not in ('READY','FOLLOWING') or state not in ('normal','interested','sleepy','happy','angry'):return
    if getattr(m,'state_leds_enabled',False) and (m.led_ring is None or getattr(m,'last_led_behavior',None)!=state):_color(m,state)
    if (state=='sleepy' and not getattr(c,'sleepy_deep_rest_enabled',False) and getattr(m,'gaze_enabled',True) and getattr(m,'yaw_follow_enabled',True)
            and not getattr(m,'sleepy_yaw_started',False) and getattr(m,'yaw_clearance_confirmed',True)):
        c.configure_tracking(yaw=True,pitch=False)
        m.follow_enabled=True;m.held=False;m.visual.position=None;m.sleepy_yaw_started=True


def apply_sleepy_yaw(m,result,now):
    """Head droop owns ID5; visible-player yaw owns ID1 only."""
    c=m.controller
    if getattr(c,'sleepy_deep_rest_enabled',False):return
    if result is None or not m.follow_enabled:return
    obs=result.get('observation',{});intent=result.get('intent',{})
    fresh=0<=now-obs.get('captured_s',-1)<=.5
    visible=fresh and obs.get('status') in ('ACQUIRED','TRACKING') and intent.get('mode') in ('FOLLOW','FOLLOW_DROOP')
    if m.visual.position is None:
        if not visible:return
        actual=next(r['position_raw'] for r in c.last_rows if r['id']==1)
        m.visual.reset(max(m.visual.low,min(m.visual.high,actual)),now)
    error=c.direction*160*intent['error_xy'][0] if visible else None
    goal=round(m.visual.step(error,now,(obs.get('source_id'),obs.get('captured_s'))))
    if m.stopping.is_set() or m.urgent_stop.is_set():return
    if c.goal_yaw(goal):c.state='FOLLOWING'


def enter_happy(m):
    """Dance around current body center; head feedback remains separate."""
    c=m.controller
    automatic=getattr(m,'automatic_fsm_enabled',False)
    if not getattr(m,'yaw_clearance_confirmed',True) or not getattr(m,'pitch_clearance_confirmed',True):
        m.tune_status='Inspect head paths before Happy';return True
    route=getattr(c,'pose_route',None)
    if route is not None and route.phase in ('look','return','lean','tilt') and not automatic:
        m.pending_behavior=ord('d');return True
    if getattr(m,'behavior_trial',None)=='happy':return True
    from bio_inspire.runtime.awake_motion import prepare_awake
    prepare_awake(m,'happy')
    if getattr(m,'happy_height_probe_trial',False) is True:m.happy_height_probe_offset_ticks=0
    source=getattr(m,'behavior_trial','normal')
    if getattr(m,'small_happy_trial',False) and source!='normal' and not automatic:
        m.tune_status='Small Happy trial: start from Normal only';return True
    if route is not None and route.phase=='complete':
        source='normal' if getattr(route,'force_normal',False) else 'interested'
    centers=({2:c.normal[2],3:c.normal[3]} if source=='normal' else
             {2:c.normal[2]-102,3:c.normal[3]+102} if source=='interested' else
             dict(getattr(c,'sleepy_body_reference',None) or {i:int.from_bytes(c.bus.read(i,42,2),'little') for i in (2,3)}) if source=='sleepy' else
             {i:int.from_bytes(c.bus.read(i,42,2),'little') for i in (2,3)})
    from bio_inspire.runtime.sleepy_trial import finish_sleepy_native_fold
    finish_sleepy_native_fold(c)
    previous_feedback={i:c.feedback_window(i) for i in c.normal} if automatic else {}
    m._hold('switch directly to happy')
    if c.state=='FAULT':return True
    if automatic:
        c.happy_entry_targets={i:int.from_bytes(c.bus.read(i,42,2),'little') for i in (2,3)}
        c.happy_entry_feedback=previous_feedback
        for i in (2,3,4):
            lo,hi=previous_feedback[i];margin=(34 if i in (2,3) else 0)+c.normal_tolerances[i]
            c.behavior_joint_windows={**getattr(c,'behavior_joint_windows',{}),i:(min(lo,c.normal[i]-margin),max(hi,c.normal[i]+margin))}
            c.behavior_joint_allowances={**getattr(c,'behavior_joint_allowances',{}),i:0}
        c.bus.windows.update(c.behavior_joint_windows);c.pose_route_windows=None
        c.behavior_joint_returns={*getattr(c,'behavior_joint_returns',set()),4}
        if not getattr(m,'happy_expanded_trial',False):
            c.bus.write(4,42,c.normal[4].to_bytes(2,'little'));c.current_roll_goal=c.normal[4]
    c.happy_roll_entry_raw=next(r['position_raw'] for r in c.bus.snapshot() if r['id']==4)
    if getattr(m,'happy_expanded_trial',False):c.current_roll_goal=c.happy_roll_entry_raw
    c.happy_body_reference=centers
    for sid in ((1,2,3) if getattr(m,'small_happy_trial',False) else (2,3)):
        c.bus.write(sid,46,c.motion_speed.to_bytes(2,"little"));c.bus.write(sid,41,bytes([3 if sid==1 else 1]))
    from bio_inspire.runtime.taught_happy import PITCH_WINDOW
    taught=getattr(m,'happy_taught_center_trial',False) is True
    c.interest_pitch_window=PITCH_WINDOW if taught else None
    c.happy_taught_active=taught
    current=next(r['position_raw'] for r in c.bus.snapshot() if r['id']==5)
    # Previously reviewed sleepy-to-awake path, not a larger gaze range.
    c.behavior_pitch_window=(min(c.active_pitch_window()[0],current),max(c.active_pitch_window()[1],current))
    if automatic:
        c.behavior_pitch_window=(min(c.behavior_pitch_window[0],previous_feedback[5][0]+6),max(c.behavior_pitch_window[1],previous_feedback[5][1]-6))
    c.sleepy_return_pending=True
    c.configure_tracking(yaw=getattr(m,'yaw_follow_enabled',True))
    wake=getattr(m,'small_happy_trial',False) and (source=='sleepy' or not c.pitch_window[0]<=current<=c.pitch_window[1])
    m.happy_head_wake_goal=c.normal[5] if wake else None
    c.goal_pitch(m.happy_head_wake_goal if m.happy_head_wake_goal is not None else max(c.pitch_window[0],min(c.pitch_window[1],current)))
    if getattr(m,'small_happy_trial',False):_small_happy_speed(m,True)
    m.pending_behavior=None;m.pending_happy_from_touch=False;m.sleepy_entry_prepared=False;m.sleepy_trial_active=False
    m.sleepy_yaw_started=False;m.behavior_trial='happy'
    m.happy_yaw_base=int.from_bytes(c.bus.read(1,42,2),'little')
    m.interested_roll_due=None
    m.visual.position=None;m._reset_pitch();m.follow_enabled=True;m.held=False
    if not getattr(m,'small_happy_trial',False) or getattr(m,'state_leds_enabled',False):_color(m,'happy')
    return True


def _small_happy_speed(m,active):
    """Approved Happy-only RAM speed/body acceleration with write readback."""
    if not active:
        from bio_inspire.runtime.taught_happy import restore_pitch
        restore_pitch(m)
    c=m.controller
    speed=getattr(m,'happy_speed_raw',400) if active else c.motion_speed
    if type(speed)is not int or speed not in (400,600,750,1000):raise ValueError('Unreviewed Happy speed')
    body_acc=getattr(m,'happy_body_acceleration_raw',1) if active else 1
    if type(body_acc)is not int or body_acc not in (1,3):raise ValueError('Unreviewed Happy body acceleration')
    c.bus.happy_speed750_trial=active and speed==750
    c.bus.happy_speed1000_trial=active and speed==1000
    c.bus.happy_body_acc3_trial=active and body_acc==3
    fast=getattr(m,'happy_taught_fast_trial',False) is True
    c.bus.happy_fast_acceleration_trial=active and fast
    dynamic=getattr(m,'happy_dynamic_trial',False) is True
    c.bus.happy_dynamic_trial=active and dynamic
    wide=getattr(m,'happy_wide_caps_trial',False) is True
    c.bus.happy_wide_caps_trial=active and wide
    if dynamic and getattr(m,'pitch_visual',None) is not None:
        v=m.pitch_visual
        if active:
            if not hasattr(m,'happy_pitch_limits_before'):m.happy_pitch_limits_before=(v.max_speed,v.max_acceleration)
            v.max_speed=800.;v.max_acceleration=6*8.7*4096/360
        elif hasattr(m,'happy_pitch_limits_before'):
            v.max_speed,v.max_acceleration=m.happy_pitch_limits_before;del m.happy_pitch_limits_before
    if active and dynamic:body_acc=16 if wide else 8
    extra=({4:12,5:6} if dynamic else {4:6,5:3}) if active else {4:1,5:1}
    if wide:extra.update({1:8,4:24} if active else {1:3})
    if active and fast:
        from acceleration_restore import AccelerationRestore
        if not hasattr(c.bus,'acceleration_restore'):c.bus.acceleration_restore=AccelerationRestore()
        for sid,value in {2:body_acc,3:body_acc,**extra}.items():c.bus.acceleration_restore.protect(sid,value,c.normal_tolerances[sid])
    for sid in range(1,6):
        if m.stopping.is_set() or m.urgent_stop.is_set():raise RuntimeError('Happy speed change cancelled')
        if int.from_bytes(c.bus.read(sid,46,2),'little')!=speed:
            c.bus.write(sid,46,speed.to_bytes(2,'little'))
        if sid in (2,3) and c.bus.read(sid,41,1)!=bytes((body_acc,)):
            if m.stopping.is_set() or m.urgent_stop.is_set():raise RuntimeError('Happy acceleration change cancelled')
            c.bus.write(sid,41,bytes((body_acc,)))
        if fast and sid in extra and c.bus.read(sid,41,1)!=bytes((extra[sid],)):
            if m.stopping.is_set() or m.urgent_stop.is_set():raise RuntimeError('Happy acceleration change cancelled')
            c.bus.write(sid,41,bytes((extra[sid],)))
