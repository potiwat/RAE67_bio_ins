"""Operator-triggered first sleepy pose, not the final emotion FSM/gaze mixer."""
def set_sleepy_trial(controller,sleepy):
    c=controller
    if c.state not in ('READY','FOLLOWING') or not c.pitch_probe_enabled or c.pitch_ticks!=68:
        raise RuntimeError('Sleepy needs Normal ready and reviewed pitch +/-6deg')
    rows=c.bus.snapshot()
    if len(rows)!=5 or any(r['status_raw'] or r['mode'] or r['torque_raw']!=1 or (r['id']==5 and (r['speed_raw'] or r['moving_raw'])) for r in rows):
        raise RuntimeError('Wait for head to stop before changing droop')
    if getattr(c,'interest_body_acceleration_raw',1)==3:
        for sid in (2,3):c.bus.write(sid,41,b'\1')
    if getattr(c,'interest_native_body_speed_raw',None) is not None:
        for sid in (2,3):c.bus.write(sid,46,c.motion_speed.to_bytes(2,'little'))
    offset=273 if getattr(c,'sleepy_deep_rest_enabled',False) else 205
    goal=c.normal[5]+(offset if sleepy else 0)
    # Approved +18deg is only a sleepy pose/path, not a wider gaze range.
    current_pitch=next(r['position_raw'] for r in rows if r['id']==5)
    c.behavior_pitch_window=(min(c.pitch_window[0],current_pitch),max(c.normal[5]+offset,current_pitch))
    c.interest_pitch_window=None
    c.sleepy_return_pending=not sleepy
    c.bus.windows[5]=c.behavior_pitch_window
    c.bus.sleepy_trial=True
    try:
        c.bus.write(5,46,(25 if sleepy else c.motion_speed).to_bytes(2,'little'))
        c.bus.write(5,41,b'\1')
        c.bus.write(5,42,goal.to_bytes(2,'little'))
    finally:c.bus.sleepy_trial=False
    c.last_pitch_goal=goal;c.state='READY'

def set_interested_trial(controller,interested):
    c=controller
    if c.state not in ('READY','FOLLOWING'):raise RuntimeError('Normal must be ready first')
    rows=c.bus.snapshot()
    if len(rows)!=5 or any(r['status_raw'] or r['mode'] or r['torque_raw']!=1 or (interested and (r['speed_raw'] or r['moving_raw'])) for r in rows):
        raise RuntimeError('Wait for all motors to stop before changing behavior')
    c.behavior_sweep=None
    c.behavior_joint_windows={4:(c.normal[4]-57,c.normal[4]+57)}
    c.behavior_joint_allowances={}
    c.behavior_joint_returns={4} if not interested else set()
    c.bus.windows[4]=c.behavior_joint_windows[4]
    c.bus.interested_trial=True
    try:
        c.bus.write(4,46,(100).to_bytes(2,'little'))
        c.bus.write(4,41,b'\1')
        c.bus.write(4,42,(c.normal[4]+(57 if interested else 0)).to_bytes(2,'little'))
    finally:c.bus.interested_trial=False
    if interested:c.behavior_sweep=dict(sid=4,center=c.normal[4],offset=57,direction=1,stable=0)
    c.state='READY'


def finish_sleepy_native_fold(c,preserve_goal=False):
    """Restore only the temporary native speed; never release torque."""
    fold=getattr(c,'sleepy_native_fold',None)
    if not fold or not fold.get('restore_required'):return
    if fold['phase']=='folding' and not preserve_goal:
        # Do not raise the speed cap while an old fold target is still active.
        if hasattr(c.bus,'hold_actual'):c.bus.hold_actual(3)
        else:
            actual=next(r['position_raw'] for r in c.bus.snapshot() if r['id']==3)
            c.bus.write(3,42,actual.to_bytes(2,'little'))
    c.bus.write(3,46,c.motion_speed.to_bytes(2,'little'))
    if int.from_bytes(c.bus.read(3,46,2),'little')!=c.motion_speed:raise RuntimeError('Sleepy ID3 speed restore unconfirmed')
    fold['restore_required']=False
    if fold['phase']=='folding':fold['phase']='cancelled'


def sleepy_native_fold_weight(c,now,cancelled):
    """One endpoint during native fold, then fade in the existing CPG."""
    if cancelled():return 0.
    fold=getattr(c,'sleepy_native_fold',None)
    if fold is None:
        ticks,speed=sleepy_fold_values(getattr(c,'sleepy_native_fold_degrees',6),getattr(c,'sleepy_native_fold_speed_raw',9))
        fold=dict(phase='folding',started_s=now,restore_required=True,target=c.sleepy_body_reference[3]+ticks,native_speed_raw=speed)
        c.sleepy_native_fold=fold
        c.bus.sleepy_native_fold_trial=True
        try:
            if cancelled():finish_sleepy_native_fold(c);return 0.
            c.bus.write(3,46,speed.to_bytes(2,'little'))
            if int.from_bytes(c.bus.read(3,46,2),'little')!=speed:raise RuntimeError('Sleepy ID3 speed unconfirmed')
        finally:c.bus.sleepy_native_fold_trial=False
    if fold['phase']=='folding' and now-fold['started_s']>=8.:
        row=next((r for r in c.last_rows if r['id']==3),None)
        if (row is not None and not row['speed_raw'] and not row['moving_raw']
                and abs(row['position_raw']-fold['target'])<=c.normal_tolerances[3]):
            finish_sleepy_native_fold(c,preserve_goal=True);fold.update(phase='breathing',breathing_started_s=now)
    if fold['phase']!='breathing':return 0.
    u=min(1.,max(0.,(now-fold['breathing_started_s'])/2.))
    return u*u*(3.-2.*u)


def sleepy_fold_values(degrees=6,speed=9):
    """Only the two explicitly approved native fold trials."""
    if type(degrees)is not int or type(speed)is not int or (degrees,speed) not in ((6,9),(12,1)):
        raise ValueError('Unreviewed Sleepy native fold values')
    return round(degrees*4096/360),speed


def sleepy_fold_ticks(c):
    return sleepy_fold_values(getattr(c,'sleepy_native_fold_degrees',6),getattr(c,'sleepy_native_fold_speed_raw',9))[0]
