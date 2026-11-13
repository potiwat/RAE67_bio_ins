"""Afraid-only SO(2) breathing, owned by the existing UART worker."""
import math
from bio_inspire.runtime.body_rhythm import BodyRhythm,decoder_reference_peak
from bounded_motion import BoundedMotion,MotionLimits
from manual_tuning import trajectory_speed_limit


class AfraidRhythm:
    def __init__(self):
        self.rhythm=BodyRhythm(amplitude_deg=2.,phi=.1,time_scale=.5)
        self.rhythm.active_joint_ids=(2,3)
        self.motion={};self.last_sent={};self.route=None
        self.rhythm.modulation_status=dict(condition='afraid_one_sided_breathing',active=False)

    def step(self,m,now):
        c=m.controller;route=getattr(c,'pose_route',None)
        cancelled=lambda:(m.stopping.is_set() or m.urgent_stop.is_set() or getattr(m,'operator_stopped',False))
        active=(not cancelled() and c.state in ('READY','FOLLOWING')
                and getattr(m,'behavior_trial',None)=='afraid'
                and getattr(route,'phase',None)=='held' and getattr(route,'taught',None) is not None)
        self.rhythm.advance(now,active,exclusive=not active)
        if not active:
            self.motion={};self.last_sent={};self.route=None
            self.rhythm.modulation_status=dict(condition='afraid_one_sided_breathing',active=False)
            return
        # Integer command span never exceeds the approved two degrees.
        span=math.floor(self.rhythm.amplitude_ticks)
        if self.route is not route:
            self.route=route;self.rhythm.envelope=0.
            self.motion={i:BoundedMotion(route.target[i],now,MotionLimits(
                route.target[i]-span,route.target[i],trajectory_speed_limit(c.motion_speed),8.7*4096/360,.5)) for i in (2,3)}
            self.last_sent=dict(route.target)
        unit=max(-1.,min(1.,getattr(self.rhythm,'interpolated_o1',self.rhythm.o1)/decoder_reference_peak(self.rhythm.alpha,self.rhythm.phi)))
        offset=-span*self.rhythm.envelope*(unit+1.)/2.
        goals={i:round(self.motion[i].step(route.target[i]+offset,now)) for i in (2,3)}
        windows={i:(route.target[i]-span-c.normal_tolerances[i],route.target[i]+c.normal_tolerances[i]) for i in (2,3)}
        c.behavior_joint_windows={**getattr(c,'behavior_joint_windows',{}),**windows}
        c.behavior_joint_allowances={**getattr(c,'behavior_joint_allowances',{}),2:0,3:0}
        c.bus.windows.update(windows)
        for i,goal in goals.items():
            if not route.target[i]-span<=goal<=route.target[i]:raise RuntimeError('Afraid CPG command outside taught cap')
        from coordinated_positions import write_positions
        outgoing={i:q for i,q in goals.items() if self.last_sent.get(i)!=q}
        if outgoing and write_positions(c.bus,outgoing,cancelled,source='afraid_cpg') is None:return
        self.last_sent.update(outgoing);c.last_joint_targets.update(outgoing)
        self.rhythm.modulation_status=dict(condition='afraid_one_sided_breathing',active=True,
            excursion_deg_limit=2.,command_offsets_deg={i:(goals[i]-route.target[i])*360/4096 for i in (2,3)},
            command_targets_raw=goals,taught_caps_raw={i:route.target[i] for i in (2,3)})
