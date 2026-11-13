"""Opt-in shared Sleepy command timeline; unchanged endpoints and RAM profiles.

This is a separate clear-path experiment, not installed in the Desktop hooks.
"""
from unittest.mock import patch
from .sleepy_smooth import smooth_driver


def sleepy_setter(original):
    def set_sleepy(c,sleepy):
        if not sleepy:return original(c,sleepy)
        source=getattr(c,'last_pitch_goal',None)
        if type(source)is not int:
            source=int.from_bytes(c.bus.read(5,42,2),'little')
        write=c.bus.write;head={}
        def guarded(sid,address,data):
            if sid==5 and address==42:
                head.update(source=source,target=int.from_bytes(data,'little'))
                data=source.to_bytes(2,'little')
            return write(sid,address,data)
        with patch.object(c.bus,'write',guarded):result=original(c,sleepy)
        if head:
            c.sleepy_coordinated_head=head;c.last_pitch_goal=source
        return result
    return set_sleepy


def coordinated_driver(base):
    class CoordinatedSleepy(smooth_driver(base)):
        def step(self,m,now):
            c=m.controller;head=getattr(c,'sleepy_coordinated_head',None)
            if (m.behavior_trial!='sleepy' or not head
                    or not getattr(c,'sleepy_native_fold_enabled',False)):
                return super().step(m,now)
            import motion_composer
            from bio_inspire.runtime.sleepy_trial import sleepy_fold_ticks
            original=motion_composer.compose_goals
            def compose(pose,bounds,**kw):
                if kw.get('state')not in ('READY','FOLLOWING')or not kw.get('cpg_enabled'):
                    return original(pose,bounds,**kw)
                u=max(0.,min(1.,(now-c.sleepy_contraction_start_s)/8.))
                blend=u*u*u*(10+u*(-15+6*u))
                start=c.sleepy_entry_positions
                source2=self.sleepy_handoff_source
                target3=c.sleepy_body_reference[3]+sleepy_fold_ticks(c)
                updated={**pose,
                         2:source2+(c.sleepy_body_reference[2]-source2)*blend,
                         3:start[3]+(target3-start[3])*blend,
                         5:head['source']+(head['target']-head['source'])*blend}
                return original(updated,bounds,**kw)
            old=self.active_joint_ids;self.active_joint_ids=tuple(sorted(set(old)|{5}))
            try:
                with patch.object(motion_composer,'compose_goals',compose):
                    result=super().step(m,now)
                if 5 in self.last_sent:c.last_pitch_goal=self.last_sent[5]
                return result
            finally:self.active_joint_ids=old
    return CoordinatedSleepy
