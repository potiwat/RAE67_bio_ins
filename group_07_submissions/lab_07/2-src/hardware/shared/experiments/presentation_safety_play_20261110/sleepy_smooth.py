"""Process-local Sleepy ID2 handoff; no new bus access, caps or PID writes."""
from unittest.mock import patch


def smooth_driver(base):
 class SmoothSleepy(base):
  def __init__(self,*args,**kw):
   super().__init__(*args,**kw)
   self.sleepy_handoff_epoch=None;self.sleepy_handoff_source=None

  def step(self,m,now):
   c=m.controller
   enabled=(getattr(m,'behavior_trial',None)=='sleepy'
            and getattr(c,'sleepy_native_fold_enabled',False)
            and getattr(c,'sleepy_deep_rest_enabled',False))
   if not enabled:
    self.sleepy_handoff_epoch=None;self.sleepy_handoff_source=None
    return super().step(m,now)
   # Capture the previous command, not the sagged encoder or a new offset.
   epoch=c.sleepy_contraction_start_s
   if epoch!=self.sleepy_handoff_epoch:
    row=next(r for r in c.last_rows if r['id']==2)
    self.sleepy_handoff_source=row['goal_raw'];self.sleepy_handoff_epoch=epoch
   import motion_composer
   original=motion_composer.compose_goals
   def compose(base_pose,bounds,**kw):
    if kw.get('state')not in('READY','FOLLOWING')or not kw.get('cpg_enabled'):
     return original(base_pose,bounds,**kw)
    u=min(1.,max(0.,(now-epoch)/2.));blend=u*u*u*(10+u*(-15+6*u))
    target=c.sleepy_body_reference[2]
    source=self.sleepy_handoff_source
    pose={**base_pose,2:source+(target-source)*blend}
    fold=getattr(c,'sleepy_native_fold',None)or{}
    v=(min(1.,max(0.,(now-fold['breathing_started_s'])/2.))
       if fold.get('phase')=='breathing'else 0.)
    weight=v*v*(3-2*v)
    offsets=dict(kw.get('cpg')or{});offsets[2]=offsets.get(2,0.)*weight
    status=dict(getattr(self.rhythm,'modulation_status',{}))
    status['sleepy_handoff']=dict(
     source_goal=source,target_center=target,blend=blend,cpg_weight=weight,
     pid_changed=False,hardware_profile_changed=False)
    self.rhythm.modulation_status=status
    return original(pose,bounds,**{**kw,'cpg':offsets})
   # Existing single motor owner calls the composer synchronously. Restore
   # the module function even if a Safety/Stop exception interrupts this tick.
   with patch.object(motion_composer,'compose_goals',compose):
    return super().step(m,now)
 return SmoothSleepy
