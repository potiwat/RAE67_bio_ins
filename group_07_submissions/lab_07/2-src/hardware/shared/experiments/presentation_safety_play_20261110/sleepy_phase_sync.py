"""Isolated normalized encoder-phase coordination for Sleepy folding only.

Reuses the accepted Angry PhasePlan without editing it or servo profiles.
Real fold completion gates the existing CPG fade, never an input/Stop handler.
"""
import inspect,math,textwrap
from unittest.mock import patch
from .angry_phase_sync import PhasePlan
from .sleepy_smooth import smooth_driver


class SleepyPlan:
    def __init__(self,c,source2,now):
        from bio_inspire.runtime.sleepy_trial import sleepy_fold_ticks
        head=c.sleepy_coordinated_head
        self.source={2:source2,3:c.sleepy_entry_positions[3],5:head['source']}
        self.actual={i:c.sleepy_entry_positions[i]for i in(3,5)}
        self.target={2:c.sleepy_body_reference[2],3:c.sleepy_body_reference[3]+sleepy_fold_ticks(c),5:head['target']}
        self.length={i:abs(self.target[i]-self.source[i])for i in(3,5)}
        self.sign={i:1 if self.target[i]>=self.source[i]else -1 for i in(3,5)}
        self.unit=max(1,self.length[3]);self.real_time=now;self.virtual_time=0.
        nominal=getattr(c,'sleepy_phase_fold_nominal_s',8.)
        if nominal not in(3.5,8.):raise ValueError('Unreviewed Sleepy fold timing')
        self.scale=min(1.,(self.unit/60.+.5)/nominal)
        self.pair=PhasePlan({2:1000,3:1000},{2:1000,3:1000},
                            {2:1000+self.unit,3:1000+self.unit},0.)
        self.goals=dict(self.source);self.commands_done=False

    def step(self,rows,now):
        dt=now-self.real_time
        if not math.isfinite(dt)or dt<0:raise ValueError('Sleepy phase clock regressed')
        self.real_time=now;self.virtual_time+=min(dt,.08)*self.scale
        actual={r['id']:r['position_raw']for r in rows}
        progress={i:(actual[i]-self.actual[i])*self.sign[i]/max(1,self.length[i])for i in(3,5)}
        if not self.length[5]:progress[5]=progress[3]
        self.pair.step({2:1000+progress[3]*self.unit,3:1000+progress[5]*self.unit},self.virtual_time)
        fraction={3:self.pair.progress[2]/self.unit,5:self.pair.progress[3]/self.unit}
        for sid in(3,5):
            delta=math.floor(self.length[sid]*fraction[sid]+.5+1e-9)
            self.goals[sid]=self.source[sid]+self.sign[sid]*delta
        weight=min(fraction.values());delta=self.target[2]-self.source[2]
        self.goals[2]=self.source[2]+(1 if delta>=0 else -1)*math.floor(abs(delta)*weight+.5+1e-9)
        self.commands_done=self.goals==self.target
        return dict(self.goals)


def phase_ready(c):
    plan=getattr(c,'sleepy_phase_sync_plan',None)
    if plan is None:return True
    if not plan.commands_done:return False
    head=next((r for r in c.last_rows if r['id']==5),None)
    return (head is not None and not head['speed_raw']and not head['moving_raw']
            and abs(head['position_raw']-plan.target[5])<=c.normal_tolerances[5])


def fold_weight(original):
    source=textwrap.dedent(inspect.getsource(original))
    anchor="if fold['phase']=='folding' and now-fold['started_s']>=8.:"
    if source.count(anchor)!=1:raise RuntimeError('Retained Sleepy native fold changed')
    source=source.replace(anchor,"if fold['phase']=='folding' and now-fold['started_s']>=8. and _phase_ready(c):",1)
    scope=dict(original.__globals__,_phase_ready=phase_ready)
    exec(compile(source,__file__,'exec'),scope)
    return scope[original.__name__]


def phase_driver(base):
    class PhaseSleepy(smooth_driver(base)):
        def __init__(self,*a,**kw):
            super().__init__(*a,**kw);self.phase_epoch=None

        def step(self,m,now):
            c=m.controller
            if (m.behavior_trial!='sleepy' or not getattr(c,'sleepy_coordinated_head',None)
                    or not getattr(c,'sleepy_native_fold_enabled',False)
                    or c.state not in('READY','FOLLOWING')or getattr(m,'operator_stopped',False)
                    or m.stopping.is_set()or m.urgent_stop.is_set()):
                return super().step(m,now)
            if self.phase_epoch!=c.sleepy_contraction_start_s:
                source=next(r['goal_raw']for r in c.last_rows if r['id']==2)
                c.sleepy_phase_sync_plan=SleepyPlan(c,source,now)
                self.phase_epoch=c.sleepy_contraction_start_s
            plan=c.sleepy_phase_sync_plan
            goals=plan.step(c.last_rows,now)
            import motion_composer
            original=motion_composer.compose_goals
            def compose(pose,bounds,**kw):
                if kw.get('state')not in('READY','FOLLOWING')or not kw.get('cpg_enabled'):
                    return original(pose,bounds,**kw)
                return original({**pose,**goals},bounds,**kw)
            old=self.active_joint_ids;self.active_joint_ids=tuple(sorted(set(old)|{5}))
            try:
                with patch.object(motion_composer,'compose_goals',compose):result=super().step(m,now)
                if 5 in self.last_sent:c.last_pitch_goal=self.last_sent[5]
                recorder=getattr(getattr(c.bus,'central_feedback',None),'recorder',None)
                if recorder is not None and(getattr(c,'sleepy_native_fold',None)or{}).get('phase')!='breathing':
                    recorder.event('SLEEPY_PHASE_SYNC',goals=goals,source=plan.source,target=plan.target,
                                   commands_done=plan.commands_done,pair=plan.pair.status)
                return result
            finally:self.active_joint_ids=old
    return PhaseSleepy
