"""Explicitly authorized ACC3 Angry-only clear-path experiment; PID untouched."""


def acceleration_route(base):
    class TrialAngryAcceleration(base):
        def __init__(self,*a,**kw):
            super().__init__(*a,**kw);self.trial_acc_active=False;self.trial_acc_ids=set()

        def commit_pending_head(self,goal):
            if (self.pending_sync_goals is not None and not self._cancelled()
                    and not self.safety_hold and self.range_phase=='advance'):
                b=self.c.bus;restore=getattr(b,'acceleration_restore',None)
                if restore is None:raise RuntimeError('Native acceleration restoration required')
                b.interested_body_acc3_trial=True
                try:
                    for sid in (2,3):
                        if self._cancelled():return False
                        restore.pin(sid,3,self.c.normal_tolerances[sid])
                        self.trial_acc_ids.add(sid);self.trial_acc_active=True
                        b.write(sid,41,b'\3')
                        if b.read(sid,41,1)!=b'\3':raise RuntimeError('ACC3 readback unconfirmed')
                finally:b.interested_body_acc3_trial=False
            return super().commit_pending_head(goal)

        def request_restore(self):
            if not self.trial_acc_ids:return
            restore=self.c.bus.acceleration_restore
            for sid in self.trial_acc_ids:restore.unpin(sid,1)
            self.trial_acc_active=False;self.trial_acc_ids.clear()

        def step(self,rows):
            try:return super().step(rows)
            finally:
                if self.range_phase not in ('advance','acquire','return')or self._cancelled():
                    self.request_restore()

        def cancel(self):
            try:return super().cancel()
            finally:self.request_restore()

        def status(self):
            return {**super().status(),'trial_acc3':dict(active=self.trial_acc_active,
                ids=[2,3],during_forward=3,restore_after_stationary=1,pid_changed=False)}
    return TrialAngryAcceleration
