"""Authorized isolated Sleepy3.5s / ID3=50,1 / ID5=100,2 trial only."""
import inspect,textwrap,types,time,json
from .sleepy_phase_sync import phase_driver,phase_ready


def bus_write(original):
    source=textwrap.dedent(inspect.getsource(original))
    anchor="sleepy_speed=(sid==5 and address==46 and value==25 and getattr(self,'sleepy_trial',False))"
    if source.count(anchor)!=1:raise RuntimeError('Retained bus validator changed')
    replacement=anchor+" or (getattr(self,'sleepy_matched_native_trial',False) is True and (sid,address,value)in((3,46,50),(5,46,100),(5,41,2)))"
    scope=dict(original.__globals__)
    exec(compile(source.replace(anchor,replacement,1),__file__,'exec'),scope)
    return scope[original.__name__]


def open_factory(original):
    def open_bus():
        b=original()
        try:
            b.write=types.MethodType(bus_write(type(b).write),b)
            b.sleepy_matched_native_trial=False
            return b
        except BaseException:
            b.close();raise
    return open_bus


def setter(original):
    source=textwrap.dedent(inspect.getsource(original))
    for before,after in (("(25 if sleepy else c.motion_speed)","(100 if sleepy else c.motion_speed)"),
                         ("c.bus.write(5,41,b'\\1')","c.bus.write(5,41,bytes((2 if sleepy else 1,)))")):
        if source.count(before)!=1:raise RuntimeError('Retained Sleepy setter changed: '+before)
        source=source.replace(before,after,1)
    scope=dict(original.__globals__);exec(compile(source,__file__,'exec'),scope)
    changed=scope[original.__name__]
    def set_sleepy(c,sleepy):
        prior=getattr(c.bus,'sleepy_matched_native_trial',False)
        c.bus.sleepy_matched_native_trial=True
        if sleepy:c.sleepy_phase_fold_nominal_s=3.5
        try:return changed(c,sleepy)
        finally:c.bus.sleepy_matched_native_trial=prior
    return set_sleepy


def fold_weight(original):
    source=textwrap.dedent(inspect.getsource(original))
    before="fold=dict(phase='folding',started_s=now,restore_required=True,target=c.sleepy_body_reference[3]+ticks,native_speed_raw=speed)"
    if source.count(before)!=1:raise RuntimeError('Retained Sleepy initialization changed')
    source=source.replace(before,"speed=50\n        "+before,1)
    before="if fold['phase']=='folding' and now-fold['started_s']>=8.:"
    if source.count(before)!=1:raise RuntimeError('Retained Sleepy handoff changed')
    source=source.replace(before,"if fold['phase']=='folding' and now-fold['started_s']>=8. and _phase_ready(c):",1)
    scope=dict(original.__globals__,_phase_ready=phase_ready)
    exec(compile(source,__file__,'exec'),scope)
    return scope[original.__name__]


def matched_driver(base):
    class MatchedSleepy(phase_driver(base)):
        def step(self,m,now):
            c=m.controller;b=c.bus;prior=getattr(b,'sleepy_matched_native_trial',False)
            b.sleepy_matched_native_trial=True
            try:
                result=super().step(m,now)
                if (m.behavior_trial=='sleepy'and not getattr(m,'operator_stopped',False)
                        and c.state in('READY','FOLLOWING')and not m.stopping.is_set()and not m.urgent_stop.is_set()
                        and(getattr(c,'sleepy_native_fold',None)or{}).get('phase')=='breathing'
                        and phase_ready(c)and getattr(self,'matched_restored_epoch',None)!=c.sleepy_contraction_start_s):
                    old=getattr(b,'sleepy_trial',False);b.sleepy_trial=True
                    try:
                        b.write(5,46,(25).to_bytes(2,'little'));b.write(5,41,b'\1')
                        if b.read(5,46,2)!=(25).to_bytes(2,'little')or b.read(5,41,1)!=b'\1':
                            raise RuntimeError('Sleepy source head profile restoration unconfirmed')
                        self.matched_restored_epoch=c.sleepy_contraction_start_s
                    finally:b.sleepy_trial=old
                return result
            finally:b.sleepy_matched_native_trial=prior
    return MatchedSleepy


def cleanup(original_open):
    """After GUI/motor owner closes: read-only proof, then conditional RAM restore."""
    b=original_open();b.motion_speed=600;deadline=time.monotonic()+2.;history=[]
    try:
        while time.monotonic()<deadline:
            blocks={i:b.read(i,33,38)for i in range(1,6)};now=time.monotonic()
            healthy=all(raw[0]==0 and raw[7]==1 and raw[32]==0 and raw[33]==0
                        and raw[25:27]==bytes(2)and raw[9:11]==raw[34:36]
                        and int.from_bytes(raw[15:17],'little')==1000 for raw in blocks.values())
            if healthy:
                key=tuple((i,raw[7:17])for i,raw in blocks.items())
                if history and history[-1][1]!=key:history=[]
                history.append((now,key,{i:int.from_bytes(raw[23:25],'little')for i,raw in blocks.items()}))
                if (len(history)>=4 and now-history[0][0]>=.15
                        and all(max(x[2][i]for x in history)-min(x[2][i]for x in history)<=2 for i in range(1,6))):break
            else:history=[]
            time.sleep(.02)
        else:raise RuntimeError('Sleepy trial cleanup support not verified; no profile write')
        changes=[]
        for i,address,count,trial_value,restore in ((3,46,2,50,600),(5,46,2,100,25),(5,41,1,2,1)):
            if int.from_bytes(b.read(i,address,count),'little')!=trial_value:continue
            old=getattr(b,'sleepy_trial',False);b.sleepy_trial=True
            try:b.write(i,address,restore.to_bytes(count,'little'))
            finally:b.sleepy_trial=old
            if int.from_bytes(b.read(i,address,count),'little')!=restore:raise RuntimeError('Cleanup readback differs')
            changes.append(dict(id=i,address=address,restored=restore))
        print('SLEEPY_MATCHED_CLEANUP '+json.dumps(dict(restored=True,changes=changes,no_pid_or_goal_writes=True)),flush=True)
    finally:b.close()


def cleanup_sessions(original_open,sessions):
    """Never claim a second UART until every started worker proved hold/close."""
    if not sessions:return
    if any(s.owner is None or not s.closing or not s.owner.finished.is_set()
           or not s.owner.cleanup_confirmed for s in sessions):
        raise RuntimeError('Sleepy profile cleanup requires all motor owners closed with confirmed hold')
    cleanup(original_open)
