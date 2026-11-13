"""Isolated encoder-phase coordination trial. Never edits servo PID/profile.

Only the leading joint is slowed. A blocked/lagging joint's reference keeps
advancing, so this does not follow a blockage or suppress contact evidence.
All existing route/ToF/entry-budget/central Safety checks run first.
"""
import math
from coordinated_positions import write_positions


class PhasePlan:
    def __init__(self,source,actual,target,now):
        self.source=dict(source);self.anchor=dict(actual);self.target=dict(target)
        if any(set(x)!={2,3}for x in(source,actual,target)):
            raise ValueError('Exactly two arm joints required')
        if any(type(v)is not int or not 0<=v<=4095 for x in(source,actual,target)for v in x.values()):
            raise ValueError('Integer bounded joint commands required')
        self.length={i:abs(target[i]-source[i])for i in(2,3)}
        self.sign={i:1 if target[i]>=source[i]else -1 for i in(2,3)}
        self.progress={2:0.,3:0.};self.velocity={2:0.,3:0.}
        self.time=now;self.skew=0.;self.status={}

    def step(self,actual,now):
        dt=now-self.time
        if not math.isfinite(dt)or dt<0:raise ValueError('Phase clock regressed')
        self.time=now;dt=min(dt,.08)
        distance=max(self.length.values())
        measured={i:(actual[i]-self.anchor[i])*self.sign[i]/max(1,self.length[i])for i in(2,3)}
        skew=(measured[2]-measured[3])*distance
        self.skew+=(-math.expm1(-dt/.12))*(skew-self.skew)
        for i in(2,3):
            lead=max(0.,self.skew*(1 if i==2 else -1))
            scale=max(.4,1./(1.+(lead/12.)**2))
            remaining=max(0.,self.length[i]-self.progress[i])
            desired=min(60.*scale,math.sqrt(2.*120.*remaining))
            self.velocity[i]+=max(-120.*dt,min(120.*dt,desired-self.velocity[i]))
            self.progress[i]=min(self.length[i],self.progress[i]+self.velocity[i]*dt)
        # Consistent half-up quantization avoids 2/4-tick alternation from
        # banker's rounding at an otherwise constant3-tick control interval.
        goals={i:self.source[i]+self.sign[i]*math.floor(self.progress[i]+.5+1e-9)for i in(2,3)}
        self.status=dict(actual_phase_skew_ticks=skew,filtered_skew_ticks=self.skew,
                         command_progress=dict(self.progress),command_velocity=dict(self.velocity),
                         source=dict(self.source),target=dict(self.target))
        return goals


def coordinated_route(base):
    class PhaseCoordinatedAngry(base):
        def __init__(self,*a,**kw):
            super().__init__(*a,**kw);self.trial_phase_plan=None
            self.trial_phase_last=None;self.trial_phase_fallback=None

        def commit_pending_head(self,goal):
            if self.pending_sync_goals is not None:
                now=self.m.now()
                if getattr(self,'started_s',now)+12.-now<6.:
                    self.trial_phase_plan=None
                    self.trial_phase_fallback='retained_native_path_short_entry_budget'
                    return super().commit_pending_head(goal)
                rows={r['id']:r for r in self.c.last_rows}
                self.trial_phase_plan=PhasePlan(
                    {i:rows[i]['goal_raw']for i in(2,3)},
                    {i:rows[i]['position_raw']for i in(2,3)},self.endpoints,now)
                self.pending_sync_goals=dict(self.trial_phase_plan.source)
                self.trial_phase_last=None
            return super().commit_pending_head(goal)

        def step(self,rows):
            super().step(rows)
            plan=self.trial_phase_plan
            if (plan is None or self.pending_sync_goals is not None
                    or self.phase!='lean'or self.range_phase!='advance'
                    or self.safety_hold or self._cancelled()):return
            actual={r['id']:r['position_raw']for r in rows if r['id']in(2,3)}
            goals=plan.step(actual,self.m.now())
            if goals==self.trial_phase_last:return
            if write_positions(self.c.bus,goals,self._cancelled,source='trial_angry_encoder_phase')is None:return
            self.c.last_joint_targets.update(goals);self.trial_phase_last=goals
            recorder=getattr(getattr(self.c.bus,'central_feedback',None),'recorder',None)
            if recorder is not None:recorder.event('ANGRY_PHASE_SYNC',**plan.status)

        def status(self):
            return {**super().status(),'trial_phase_sync':dict(
                active=self.trial_phase_plan is not None,fallback=self.trial_phase_fallback,
                encoder_feedback=True,hardware_profiles_changed=False,
                plan=None if self.trial_phase_plan is None else self.trial_phase_plan.status)}
    return PhaseCoordinatedAngry
