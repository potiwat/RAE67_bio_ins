"""Bounded encoder observations only; no device writes or smoothness verdict."""
import json
from pathlib import Path


class JointMotionLog:
    def __init__(self,path):
        self.path=Path(path);self.active=None;self.history=[]

    def begin(self,sid,start,goal,pid,now):
        if self.active is not None:self.finish('replaced')
        self.active=dict(joint_id=sid,start_raw=start,goal_raw=goal,pid=dict(pid),
                         start_s=now,samples=[],still_since=None)

    def sample(self,now,row,pending,state,goal):
        a=self.active
        if a is None:return
        a['samples'].append(dict(t_s=now-a['start_s'],position_raw=row['position_raw'],
                                 speed_raw=row['speed_raw'],moving_raw=row['moving_raw']))
        if state=='FAULT':self.finish('fault');return
        if goal!=a['goal_raw']:self.finish('target_changed');return
        if not pending and not row['speed_raw'] and not row['moving_raw']:
            if a['still_since'] is None:a['still_since']=now
            if now-a['still_since']>=8.:self.finish('stationary');return
        else:a['still_since']=None
        if now-a['start_s']>=25 or len(a['samples'])>=500:self.finish('observation_limit')

    def finish(self,reason):
        a=self.active
        if a is None:return
        self.active=None;a.pop('still_since',None);a['reason']=reason
        points=[s['position_raw'] for s in a['samples']];goal=a['goal_raw']
        direction=1 if goal>a['start_raw'] else -1 if goal<a['start_raw'] else 0
        a['overshoot_ticks']=max([0]+[(p-goal)*direction for p in points]) if direction else None
        a['final_error_ticks']=points[-1]-goal if points else None
        self.history=(self.history+[a])[-6:]
        try:
            temp=self.path.with_suffix('.tmp')
            temp.write_text(json.dumps(dict(history=self.history),indent=2),encoding='utf-8')
            temp.replace(self.path)
        except OSError as error:print('MOTION_LOG_FAILED',str(error),flush=True)
