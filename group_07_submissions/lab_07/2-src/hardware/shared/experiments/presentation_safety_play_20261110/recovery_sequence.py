"""Model reset at owner stop acceptance; verified Normal may resume play.

This policy never grants obstacle clearance. The separate bounded probe must
provide evidence for the current stop epoch before any Normal return begins.
"""
def immediate_reset_supervisor(base):
 class ImmediateReset(base):
  def _start_hold(self,reset):
   super()._start_hold(reset)
   if not reset or not self.allow_return:return
   self.a.blackout_detection()
   self.a.reset();self.reset_done=True
   self.record('MODELS_RESET',timing='owner_stop_acceptance_before_native_hold')
 return ImmediateReset

def ready_for_automatic_resume(a):
 c=a.core;m=a.m
 return (c.phase=='NORMAL_PARKED'and c.allow_return and c.error is None and c.pending is None
         and not m.stopping.is_set()and not m.urgent_stop.is_set()
         and a.healthy()and a.stopped()and a.id1_contact_released())

def arm_automatic_resume(a):
 if a.restart_claimed or a.restart_request is not None or not ready_for_automatic_resume(a):return False
 rows=a.m.controller.last_rows
 if {r['id']for r in rows}!=set(range(1,6)):return False
 a.restart_hold_goals={r['id']:r['goal_raw']for r in rows}
 a.restart_request=(a.core.serial,a.core.hold_epoch)
 a.core.record('AUTO_PLAY_RESUME_READY',button_required=False)
 return True
