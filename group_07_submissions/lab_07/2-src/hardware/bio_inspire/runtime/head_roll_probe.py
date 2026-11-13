"""Supervised joint probes on the current UART owner; no automatic cycling."""
def _cancelled(m):
    return getattr(m,'operator_stopped',False) or any(
        flag is not None and flag.is_set() for flag in
        (getattr(m,'urgent_stop',None),getattr(m,'stopping',None)))

def handle_probe_key(m,key):
    if not getattr(m,'head4_probe_enabled',False):return False
    c=m.controller
    body_enabled=getattr(m,'body_probe_selection_enabled',False)
    selecting=key in (ord('2'),ord('3')) and body_enabled
    if not selecting and key not in (ord('p'),ord('o')):return False
    if c.state not in ('READY','FOLLOWING') or _cancelled(m):return True
    if selecting:
        if getattr(m,'behavior_trial','normal')!='normal':m.tune_status='Normal first for body probe';return True
        if getattr(m,'head_probe_active',False):
            sid=m.head_probe_joint_id
            row=next((r for r in c.last_rows if r['id']==sid),None)
            if getattr(m,'head_probe_last_offset',0)!=0:
                m.tune_status='Press O and wait before selecting next joint';return True
            checked=[r for r in c.last_rows if not (getattr(m,'body_probe_pitch_follow_enabled',False) and r['id']==5)]
            if (row is None or any(r['speed_raw'] or r['moving_raw'] for r in checked)
                    or abs(row['position_raw']-m.head_probe_base)>c.normal_tolerances[sid]):
                m.tune_status='Wait for O return to settle';return True
        recorder=getattr(m,'head_probe_recorder',None)
        if recorder is not None:recorder.cancel('probe_joint_selection_changed')
        m.head_probe_joint_id=int(chr(key));m.head_probe_active=False
        m.tune_status=f'ID{m.head_probe_joint_id} selected; O baseline / P +3deg'
        return True
    sid=getattr(m,'head_probe_joint_id',4)
    if type(sid)is not int or sid not in (2,3,4,5) or sid in (2,3) and not body_enabled:
        m.tune_status='Invalid probe ID/profile';return True
    if getattr(m,'behavior_trial','normal')!='normal':m.tune_status=f'Normal first for ID{sid} probe';return True
    obs=(getattr(m,'latest_result',None) or {}).get('observation',{})
    if key==ord('p') and (obs.get('status') not in ('TRACKING','ACQUIRED') or not 0<=m.now()-obs.get('captured_s',-1)<=.5):
        m.tune_status=f'ID{sid} probe waits for a fresh visible face';return True
    if not getattr(m,'head_probe_active',False):
        if sid in (2,3):
            active=int.from_bytes(c.bus.read(sid,42,2),'little')
            row=next((r for r in c.last_rows if r['id']==sid),None)
            if (c.normal_tolerances[sid]!=34 or abs(active-c.normal[sid])>34 or row is None
                    or abs(row['position_raw']-c.normal[sid])>34
                    or row['speed_raw'] or row['moving_raw']):
                m.tune_status='Body probe requires reviewed Normal context';return True
            # Already stationary with native holding goals: do not rebase loaded
            # joints via an all-axis hold before validating the requested probe.
            base=active
        else:
            m.follow_enabled=False;m._hold(f'freeze current pose for ID{sid} measurement',all_axes=True)
            if c.state=='FAULT':return True
            base=int.from_bytes(c.bus.read(sid,42,2),'little')
    else:base=m.head_probe_base
    goal=base+(34 if key==ord('p') else 0)
    if sid in (2,3):
        normal=c.normal[sid];window=(normal-34,normal+34)
        if not window[0]<=base<=window[1] or not window[0]<=goal<=window[1]:
            m.tune_status='Body probe outside reviewed command range';return True
        c.behavior_joint_windows={**getattr(c,'behavior_joint_windows',{}),sid:(normal-68,normal+68)}
        c.behavior_joint_allowances={**getattr(c,'behavior_joint_allowances',{}),sid:0}
    elif sid==5:
        window=c.active_pitch_window()
        if not window[0]<=goal<=window[1]:m.tune_status='ID5 relative probe outside reviewed range';return True
    else:
        old=getattr(c,'behavior_joint_windows',{}).get(4,(base-22,base+22))
        window=(min(old[0],base-22),max(old[1],base+34+22))
        c.behavior_joint_windows={**getattr(c,'behavior_joint_windows',{}),4:window}
        c.behavior_joint_allowances={**getattr(c,'behavior_joint_allowances',{}),4:0}
    c.bus.windows[sid]=window
    if not getattr(m,'head_probe_active',False):
        m.follow_enabled=False;m.held=True;m.visual.position=None;m._reset_pitch()
    for address,data in ((46,c.motion_speed.to_bytes(2,'little')),(41,b'\1'),(42,goal.to_bytes(2,'little'))):
        if _cancelled(m):return True
        c.bus.write(sid,address,data)
    # Enable any opt-in pitch feedback only after the position request succeeds.
    m.head_probe_base=base;m.head_probe_active=True
    if sid==4:c.current_roll_goal=goal
    elif sid==5:c.last_pitch_goal=goal
    else:c.last_joint_targets[sid]=goal
    m.head_probe_last_offset=goal-base
    event=dict(time_s=m.now(),joint_id=sid,target_raw=goal,base_raw=base,observation=dict(obs),
               condition='closed_loop_pitch_follow' if sid in (2,3) and getattr(m,'body_probe_pitch_follow_enabled',False) else 'isolated_joint')
    m.head_probe_events=(getattr(m,'head_probe_events',[])+[event])[-8:]
    if getattr(m,'head_probe_recorder',None) is None:
        from probe_observation import ProbeObservation
        m.head_probe_recorder=ProbeObservation()
    m.head_probe_recorder.request(event)
    m.tune_status=f'ID{sid} +3deg' if key==ord('p') else f'ID{sid} baseline / other axes frozen'
    print('HEAD_PROBE',event,flush=True)
    return True
