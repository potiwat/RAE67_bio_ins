"""Observe the first READY hold using the existing UART owner; never write motors."""
import json
from pathlib import Path


class ReadyHoldLog:
    def __init__(self,path):
        self.path=Path(path);self.started=None;self.done=False;self.samples=[]
        self.goals={};self.goals_read_s=None

    def step(self,now,state,activity,rows,read_goals):
        if self.done:return
        if self.started is None:
            if state!='READY' or activity:return
            self.started=now
        if state!='READY' or activity:
            self.finish('fault' if state=='FAULT' else 'interrupted');return
        try:
            if self.goals_read_s is None or now-self.goals_read_s>=.5:
                self.goals=dict(read_goals());self.goals_read_s=now
                if set(self.goals)!=set(range(1,6)):raise ValueError('Incomplete hold goals')
        except Exception as error:
            self.finish('goal_read_error: '+str(error));return
        self.samples.append(dict(t_s=now-self.started,goals_read_s=self.goals_read_s,
                                 goals=dict(self.goals),rows=[dict(r) for r in rows]))
        if now-self.started>=25 or len(self.samples)>=500:self.finish('complete')

    def finish(self,reason):
        if self.done or self.started is None:return
        self.done=True;summary={}
        for sid in range(1,6):
            positions=[r['position_raw'] for s in self.samples for r in s['rows'] if r['id']==sid]
            if positions:
                summary[str(sid)]=dict(first_raw=positions[0],last_raw=positions[-1],
                    min_raw=min(positions),max_raw=max(positions),span_ticks=max(positions)-min(positions),
                    goal_values=sorted({s['goals'][sid] for s in self.samples}))
        report=dict(reason=reason,start_s=self.started,samples=self.samples,summary=summary,
                    note='Goals read at most every0.5s; encoder timestamps per row. Diagnostic only; no smoothness certification.')
        try:
            temp=self.path.with_suffix('.tmp');temp.write_text(json.dumps(report,indent=2),encoding='utf-8');temp.replace(self.path)
            print('READY_HOLD_OBSERVATION',reason,'samples',len(self.samples),flush=True)
        except OSError as error:print('READY_HOLD_LOG_FAILED',str(error),flush=True)
