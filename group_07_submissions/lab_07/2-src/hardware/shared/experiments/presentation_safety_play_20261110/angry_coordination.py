"""Opt-in bounded common Angry arm command path; native guards remain owners.

Same native Speed25/ACC1 and endpoints. No change to ToF stop, collision
detector, entry budget, PID, or emergency/hold methods.
"""
from coordinated_positions import write_positions


def coordinated_route(base):
    class CoordinatedAngry(base):
        def __init__(self,*a,**kw):
            super().__init__(*a,**kw)
            self.trial_arm_start=None;self.trial_arm_source=None;self.trial_arm_last=None
            self.trial_arm_fallback=None

        def trial_arm_goals(self,now):
            u=max(0.,min(1.,(now-self.trial_arm_start)/4.))
            blend=u*u*u*(10+u*(-15+6*u))
            return {i:round(q+(self.endpoints[i]-q)*blend)
                    for i,q in self.trial_arm_source.items()}

        def commit_pending_head(self,goal):
            if self.pending_sync_goals is not None:
                now=self.m.now()
                if getattr(self,'started_s',now)+12.-now<4.5:
                    self.trial_arm_start=None;self.trial_arm_source=None
                    self.trial_arm_fallback='retained_native_route_entry_budget_too_short'
                    return super().commit_pending_head(goal)
                self.trial_arm_start=now
                self.trial_arm_source={r['id']:r['goal_raw']for r in self.c.last_rows
                                       if r['id']in(2,3)}
                if set(self.trial_arm_source)!={2,3}:
                    raise RuntimeError('Fresh commanded arm goals required for trajectory')
                self.pending_sync_goals=self.trial_arm_goals(self.trial_arm_start)
                self.trial_arm_last=None
            return super().commit_pending_head(goal)

        def step(self,rows):
            super().step(rows)
            if (self.trial_arm_start is None or self.pending_sync_goals is not None
                    or self.phase!='lean' or self.range_phase!='advance'
                    or self.safety_hold or self._cancelled()):return
            goals=self.trial_arm_goals(self.m.now())
            if goals==self.trial_arm_last:return
            if write_positions(self.c.bus,goals,self._cancelled,
                               source='trial_angry_common_arm_path')is None:return
            self.c.last_joint_targets.update(goals);self.trial_arm_last=goals

        def status(self):
            return {**super().status(),'trial_arm_coordination':dict(
                duration_s=4.,active=self.trial_arm_start is not None,
                fallback=self.trial_arm_fallback,hardware_profiles_changed=False)}
    return CoordinatedAngry
