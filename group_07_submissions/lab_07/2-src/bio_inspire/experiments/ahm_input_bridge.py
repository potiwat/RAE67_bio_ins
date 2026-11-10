"""Logical lamp inputs -> shared stimulus and symbolic FSM; no device access.

Debounce/hysteresis follow Lab06/07; explicit no-target handling follows the
accepted physical-input contract. Near-only stimulus v2 was approved 2026-11-04;
approach remains an FSM input, with legacy hormone mapping explicitly selectable.
"""
from dataclasses import asdict, dataclass
import math
import random

from bio_inspire.runtime.angry_fsm import AngryFSM, TouchBurst


@dataclass(frozen=True)
class InputFrame:
    time_s: float
    sample_s: float
    button: bool
    touch: bool
    distance_kind: str
    distance_m: float | None
    source_id: str
    button_sample_s: float | None = None
    touch_sample_s: float | None = None
    distance_sample_s: float | None = None
    digital_predebounced: bool = False
    button_events: tuple = ()
    touch_events: tuple = ()


class InputAdapter:
    def __init__(self,stimulus_policy='near_only_v2'):
        if stimulus_policy not in ('near_only_v2','approach_or_near_v1'):raise ValueError('unknown stimulus policy')
        self.stimulus_policy=stimulus_policy
        self.last_time=None
        self.digital={k:dict(raw=False,stable=False,since=0.,source_s=0.,source_id='') for k in ('button','touch')}
        self.near=False
        self.approach=False
        self.no_target_since=None
        self.faulted=False
        self.last_accepted={'button':None,'touch':None}

    def step(self, frame):
        now=frame.time_s
        if type(now) not in (int,float) or not math.isfinite(now) or now<0 or self.last_time is not None and now<=self.last_time:
            raise ValueError('nonnegative strictly increasing snapshot times required')
        self.last_time=now
        stamps={k:getattr(frame,k+'_sample_s') if getattr(frame,k+'_sample_s') is not None else frame.sample_s
                for k in ('button','touch','distance')}
        valid=(type(frame.sample_s) in (int,float) and math.isfinite(frame.sample_s)
               and frame.sample_s>=0
               and -1e-9<=now-frame.sample_s<=.12+1e-9
               and all(type(t) in (int,float) and math.isfinite(t) and t>=0 and -1e-9<=now-t<=.12+1e-9 for t in stamps.values())
               and type(frame.button) is bool and type(frame.touch) is bool
               and isinstance(frame.source_id,str) and bool(frame.source_id)
               and (frame.distance_kind=='no_target' and frame.distance_m is None
                    or frame.distance_kind=='range' and type(frame.distance_m) in (int,float)
                    and math.isfinite(frame.distance_m) and 0.<=frame.distance_m<=4.))
        events=[]
        def event(kind, stamp=None, source_id=None):
            source=stamps['distance'] if valid else now
            events.append(dict(kind=kind,source_s=source if stamp is None else stamp,source_id=source_id or frame.source_id))
        if not valid:
            if not self.faulted:event('fault')
            self.faulted=True;self.near=False;self.approach=False;self.no_target_since=None
            for values in self.digital.values():values.update(raw=False,stable=False,since=now,source_id='')
            return dict(time_s=now,source_id=frame.source_id,sample_s=frame.sample_s,
                        distance_kind=frame.distance_kind,distance_m=frame.distance_m,
                        button_stable=False,touch_stable=False,held=False,near=False,approach=False,
                        stimulus=None,fault=True,events=events)
        self.faulted=False
        if type(frame.digital_predebounced) is not bool:raise ValueError('invalid digital sampler mode')
        for channel, values in self.digital.items():
            raw=getattr(frame,channel)
            accepted=getattr(frame,channel+'_events')
            if frame.digital_predebounced:
                if not isinstance(accepted,(tuple,list)) or len(accepted)>180:raise ValueError('invalid bounded input events')
                previous=self.last_accepted[channel]
                for stamp in accepted:
                    if (type(stamp) not in (int,float) or not math.isfinite(stamp) or not 0<=now-stamp<=2.
                            or previous is not None and stamp<=previous):raise ValueError('invalid or replayed input event')
                    previous=stamp
                self.last_accepted[channel]=previous
                values.update(raw=raw,stable=raw)
                for stamp in accepted:event(channel,stamp,frame.source_id+'_'+channel+'_edge_'+str(stamp))
            else:
                if accepted:raise ValueError('buffered events require predebounced mode')
                if raw!=values['raw']:
                    values.update(raw=raw,since=now,source_s=stamps[channel],source_id=frame.source_id)
                if raw!=values['stable'] and now-values['since']>=.06-1e-9:
                    values['stable']=raw
                    if raw:event(channel,values['source_s'],values['source_id'])
        old_near,old_approach=self.near,self.approach
        if frame.distance_kind=='range':
            self.no_target_since=None
            distance=frame.distance_m
            self.near=distance<.28 if old_near else distance<=.20
            self.approach=distance<.95 if old_approach else distance<=.80
        else:
            if self.no_target_since is None:self.no_target_since=now
            if now-self.no_target_since>=.5-1e-9:self.near=False;self.approach=False
        if self.near and not old_near:event('near')
        if old_near and not self.near or old_approach and not self.approach:event('clear')
        if self.approach and not old_approach and not self.near:event('approach')
        held=any(v['stable'] for v in self.digital.values())
        return dict(time_s=now,source_id=frame.source_id,sample_s=frame.sample_s,
                    distance_kind=frame.distance_kind,distance_m=frame.distance_m,
                    button_stable=self.digital['button']['stable'],touch_stable=self.digital['touch']['stable'],
                    held=held,near=self.near,approach=self.approach,
                    stimulus=float(held or self.near or self.approach and self.stimulus_policy=='approach_or_near_v1'),fault=False,events=events)


class EmotionAdapter:
    """Reuse accepted six-state policy; entry motions are not simulated."""
    def __init__(self):
        self.fsm=AngryFSM(0.,active_timeout_s=5.,sleep_after_s=10.,happy_timeout_s=7.,motion_aware=True)
        self.burst=TouchBurst()

    def step(self, sample):
        now=sample['time_s'];candidates=list(sample['events'])
        if sample['fault']:
            self.fsm.near_active=False
        blocked=sample['near'] or self.fsm.state in ('afraid','angry') or sample['fault']
        if blocked:self.burst.clear()
        for event in sample['events']:
            if event['kind']=='touch' and not blocked and self.burst.press(event['source_s'],now):
                candidates.append(dict(kind='touch_burst',source_s=event['source_s'],source_id=event['source_id']+'_burst'))
        # Mirror retained Near/Clear admission for level already active when
        # Angry ends. No new hardware policy is introduced here.
        if sample['near'] and self.fsm.state!='afraid' and not any(e['kind']=='near' for e in candidates):
            candidates.append(dict(kind='near',source_s=now,source_id=sample['source_id']+'_near_level'))
        if not sample['near'] and self.fsm.state=='afraid' and not sample['fault'] and not any(e['kind']=='clear' for e in candidates):
            candidates.append(dict(kind='clear',source_s=now,source_id=sample['source_id']+'_clear_level'))
        winner=self.fsm.step(now,candidates,ready=not sample['fault'],held=sample['held'])
        return dict(**sample,emotion=self.fsm.state,interaction=None if winner is None else winner['kind'],
                    symbolic_ready=True,physical_motion_measured=False)


def process_inputs(frames,stimulus_policy='near_only_v2'):
    adapter,emotion=InputAdapter(stimulus_policy),EmotionAdapter()
    return [emotion.step(adapter.step(frame)) for frame in frames]


def scenario(seed):
    """600s synthetic interaction, paired seeds; not observations of a person."""
    if type(seed) is not int:raise ValueError('integer seed required')
    rng=random.Random(seed)
    result=[]
    for k in range(12000):
        t=k*.05
        button=any(a<=t<a+.3 for a in (20.,90.,560.))
        touch=any(a<=t<a+.2 for a in (130.,150.,155.,155.4,155.8,170.,580.))
        near=any(a<=t<b for a,b in ((260.,280.),(320.,350.),(390.,400.)))
        distance=(.15 if near else .60 if 190<=t<230 else 1.2)+rng.uniform(-.01,.01)
        no_target=280<=t<285
        result.append(InputFrame(t,t,button,touch,'no_target' if no_target else 'range',
                                 None if no_target else distance,f'seed{seed}_sample{k:05d}'))
    return result


def raw_rows(frames):
    return [asdict(frame) for frame in frames]
