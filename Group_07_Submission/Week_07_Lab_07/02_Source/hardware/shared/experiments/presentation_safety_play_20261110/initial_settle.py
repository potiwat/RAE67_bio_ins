"""Read-only initial-start standstill proof; original validator still runs."""


class StandstillReads:
    def __init__(self,read,now,wait,cancelled):
        self.read,self.now,self.wait,self.cancelled=read,now,wait,cancelled
        self.pins=None

    def __call__(self):
        started=self.now();history=[]
        while True:
            if self.cancelled():raise RuntimeError('Initial standstill check cancelled')
            rows=self.read();stamp=self.now()
            if [r['id']for r in rows]!=list(range(1,6)):
                raise RuntimeError('Initial standstill feedback incomplete')
            torques={r['torque_raw']for r in rows}
            if torques not in({0},{1})or any(r['mode']or r['status_raw']for r in rows):
                raise RuntimeError('Initial native mode/torque/status fault')
            if self.pins is None:
                self.pins={r['id']:(r['position_raw'],r['goal_raw'],r['torque_raw'])for r in rows}
            for r in rows:
                q,goal,torque=self.pins[r['id']]
                if (abs(r['position_raw']-q)>2 or r['goal_raw']!=goal or r['torque_raw']!=torque
                        or(torque==1 and abs(r['internal_target_raw']-goal)>2)):
                    raise RuntimeError('Initial held pose/goal changed ID'+str(r['id']))
            if self.cancelled():raise RuntimeError('Initial standstill check cancelled after read')
            if stamp-started>.25:raise RuntimeError('Initial standstill not confirmed within0.25s')
            if all(not r['speed_raw']and not r['moving_raw']for r in rows):
                history.append(stamp)
                if len(history)>=3 and stamp-history[0]>=.02-1e-9:return rows
            else:history=[]
            left=.25-(self.now()-started)
            if left<=1e-9:raise RuntimeError('Initial standstill not confirmed within0.25s')
            self.wait(min(.01,left))


def wrap_preflight(original,now,wait,cancelled):
    def prepare(bus,*args,**kwargs):
        read=bus.snapshot;settle=StandstillReads(read,now,wait,cancelled)
        bus.snapshot=settle
        try:
            result=original(bus,*args,**kwargs)
        finally:
            bus.snapshot=read
        if all(p[2]==1 for p in settle.pins.values()):
            bus.initial_standstill_goals={i:p[1]for i,p in settle.pins.items()}
        return result
    return prepare
