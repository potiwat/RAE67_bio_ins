"""Preflight for an explicit, operator-supported M start from the live pose."""
from manual_tuning import validate_values


def prepare_operator_start(bus,pids,normal_tolerances=None,motion_speed=100):
    if type(motion_speed)is not int or motion_speed not in (1,100,200,400,600):raise ValueError('Unreviewed startup speed')
    limits={i:22 for i in range(1,6)}
    if normal_tolerances is not None:
        if normal_tolerances not in (limits,{**limits,3:34},{**limits,3:34,5:34},{**limits,2:34,3:34,5:34}):
            raise ValueError('Unreviewed Normal hold tolerances')
        limits=dict(normal_tolerances)
    if not isinstance(pids,dict) or set(pids)!=set(map(str,range(1,6))):
        raise ValueError('Explicit startup PID for all five motors required')
    desired={}
    for key,p in pids.items():
        if not isinstance(p,dict) or set(p)!={'p','i','d'}:raise ValueError('Startup P/I/D required')
        v=validate_values(dict(p,speed=1),int(key));desired[int(key)]=bytes([v['p'],v['d'],v['i']])
    def healthy(rows):
        return ([r['id'] for r in rows]==list(range(1,6)) and
                all(not r['mode'] and not r['status_raw'] and not r['speed_raw'] and not r['moving_raw'] for r in rows))
    rows=bus.snapshot()
    if not healthy(rows):raise RuntimeError('Operator start requires healthy stationary feedback')
    torques={r['torque_raw'] for r in rows}
    if torques not in ({0},{1}):raise RuntimeError('Mixed torque; inspect before starting')
    before={i:bus.read(i,21,3) for i in range(1,6)}
    if any(bus.read(i,55,1)!=b'\1' for i in range(1,6)):
        raise RuntimeError('Volatile lock1 required; EEPROM unchanged')
    if torques=={1}:
        for r in rows:
            error=abs(int.from_bytes(bus.read(r['id'],42,2),'little')-r['position_raw'])
            if error>limits[r['id']]:
                raise RuntimeError(f"ID{r['id']} hold error {error} exceeds {limits[r['id']]} ticks")
    old_manual=getattr(bus,'manual_tuning',False);old_id=getattr(bus,'tuning_id',1)
    try:
        bus.manual_tuning=True
        for sid in range(1,6):
            bus.tuning_id=sid
            if before[sid]!=desired[sid]:bus.write(sid,21,desired[sid])
            if bus.read(sid,21,3)!=desired[sid] or bus.read(sid,55,1)!=b'\1':
                raise RuntimeError(f'ID{sid} startup PID readback differs')
        if torques=={1}:
            # Explicit supported M: normalize RAM limits without releasing or rebasing goals.
            old_speed=getattr(bus,'motion_speed',1)
            try:
                bus.motion_speed=motion_speed
                for sid in range(1,6):
                    if bus.read(sid,46,2)!=motion_speed.to_bytes(2,'little'):bus.write(sid,46,motion_speed.to_bytes(2,'little'))
                    if bus.read(sid,41,1)!=b'\1':bus.write(sid,41,b'\1')
            finally:bus.motion_speed=old_speed
    finally:bus.manual_tuning=old_manual;bus.tuning_id=old_id
    fresh=bus.snapshot()
    if not healthy(fresh) or {r['torque_raw'] for r in fresh}!=torques:
        raise RuntimeError('Motor state changed during preflight')
    if any(abs(a['position_raw']-b['position_raw'])>2 for a,b in zip(rows,fresh)):
        raise RuntimeError('Pose moving during preflight; support and retry')
    return {r['id']:r['position_raw'] for r in fresh}
