"""Operator-approved ID1 volatile tuning. Called only by the UART owner."""
BOUNDS={'p':(8,32),'i':(0,2),'d':(16,48),'speed':(1,100)}
DEFAULTS={'p':16,'i':0,'d':32,'speed':4}
PITCH_BOUNDS={'p':(1,64),'i':(0,8),'d':(0,64),'speed':(1,1)}
PITCH_DEFAULTS={'p':32,'i':0,'d':32,'speed':1}

def bounds_for(sid):
    if sid not in (1,2,3,4,5):raise ValueError('Unknown tuning joint')
    return PITCH_BOUNDS if sid!=1 else BOUNDS

def defaults_for(sid):
    bounds_for(sid)
    return dict(PITCH_DEFAULTS if sid!=1 else DEFAULTS)

def trajectory_speed_limit(raw_speed):
    # Separate host trajectory from the servo raw register's phase-dependent
    # unit. Keep the previously trialled host ceiling; do not scale it x100.
    return min(raw_speed,8)*.732*6*4096/360

def validate_values(values,sid=1):
    bounds=bounds_for(sid)
    if not isinstance(values,dict) or set(values)!=set(bounds):raise ValueError('Expected P I D Speed')
    for k,(low,high) in bounds.items():
        if type(values[k]) is not int or not low<=values[k]<=high:raise ValueError(f'{k} outside {low}..{high}')
    return dict(values)

def read_values(bus,sid=1):
    bounds_for(sid)
    pid=bus.read(sid,21,3)
    return dict(p=pid[0],d=pid[1],i=pid[2],speed=int.from_bytes(bus.read(sid,46,2),'little'))

def apply_values(bus,values,cancelled=lambda:False,sid=1):
    v=validate_values(values,sid)
    acceleration=1 if sid!=1 or getattr(bus,'manual_joint_mode',False) else 3
    if bus.read(sid,55,1)!=b'\1':raise RuntimeError('Lock must remain1; no persistent tuning')
    pid=bytes((v['p'],v['d'],v['i']))
    if cancelled():raise RuntimeError('Tuning cancelled')
    if bus.read(sid,21,3)!=pid:bus.write(sid,21,pid)
    if cancelled():raise RuntimeError('Tuning cancelled after PID; values unconfirmed')
    if bus.read(sid,46,2)!=v['speed'].to_bytes(2,'little'):
        bus.write(sid,46,v['speed'].to_bytes(2,'little'))
    if cancelled():raise RuntimeError('Tuning cancelled after speed; values unconfirmed')
    if bus.read(sid,41,1)!=bytes((acceleration,)):bus.write(sid,41,bytes((acceleration,)))
    actual=read_values(bus,sid)
    if actual!=v or bus.read(sid,55,1)!=b'\1' or bus.read(sid,41,1)!=bytes((acceleration,)):raise RuntimeError('Tuning readback mismatch')
    return actual


def apply_group_pid_trial(bus, report_path=None):
    """Exact operator-approved P8/I1/D16; cold joints only, no motion writes."""
    import json
    rows=bus.snapshot()
    if [r['id'] for r in rows]!=list(range(1,6)):
        raise RuntimeError('Incomplete group PID feedback')
    if any(r['mode'] or r['status_raw'] or r['moving_raw'] or r['speed_raw'] for r in rows):
        raise RuntimeError('Group PID requires healthy stationary joints')
    before={str(i):list(bus.read(i,21,3)) for i in range(1,6)}
    if any(bus.read(i,55,1)!=b'\1' for i in range(1,6)):
        raise RuntimeError('Group PID requires lock1 on all joints')
    desired=bytes((8,16,1))
    # Reopening the already configured session must not rebase or retune loaded joints.
    if all(bytes(v)==desired for v in before.values()):
        return dict(before=before,after=before,status='already applied')
    if any(r['torque_raw']!=0 for r in rows):
        raise RuntimeError('Group PID change requires torque OFF; do not release loaded joints automatically')
    report=dict(before=before,requested_PDI=list(desired),after={},status='pending')
    def save():
        if report_path is not None:report_path.write_text(json.dumps(report,indent=2),encoding='utf-8')
    save()  # Preserve original values before the first write; never silently lose backup.
    bus.group_pid_trial=True
    try:
        for i in range(1,6):
            if bytes(before[str(i)])!=desired:bus.write(i,21,desired)
            actual=bus.read(i,21,3)
            if actual!=desired or bus.read(i,55,1)!=b'\1':raise RuntimeError(f'ID{i} group PID readback differs')
            report['after'][str(i)]=list(actual)
        report['status']='applied, readback verified'
        return report
    except BaseException:
        report['status']='incomplete; inspect per-joint readback before motion'
        raise
    finally:
        bus.group_pid_trial=False
        save()


def ensure_base_pid(bus):
    """Restore the approved base candidate only before cold arming, never loaded."""
    rows=bus.snapshot()
    if [r['id'] for r in rows]!=list(range(1,6)) or any(
            r['mode'] or r['status_raw'] or r['speed_raw'] or r['moving_raw'] for r in rows):
        raise RuntimeError('Base PID preflight requires healthy stationary five-joint feedback')
    before=bus.read(1,21,3);desired=bytes((8,16,1))
    if bus.read(1,55,1)!=b'\1':raise RuntimeError('Base PID requires volatile lock1')
    if before!=desired:
        if any(r['torque_raw']!=0 for r in rows):
            raise RuntimeError('Support lamp and cycle servo power before restoring base PID; no automatic torque release')
        bus.write(1,21,desired)
    after=bus.read(1,21,3)
    if after!=desired or bus.read(1,55,1)!=b'\1':raise RuntimeError('Base PID startup readback mismatch')
    return dict(before_PDI=list(before),after_PDI=list(after))
