"""Opt-in Normal hardware mapping, independent of motor/ROS/GPIO drivers.

AHM: retained Lab05 hormone_step, R=H, rates (.8,.6,.2), dt=.05.
Hardware adaptation: phi=.10+.03R, unlike Lab05 research phi=.20+.20R.
The existing UART owner calls this; no extra input reader or output owner.
"""
import math
from itertools import groupby


def validate_trial_config(config):
    condition=config.get('normal_ahm_condition')
    scope=config.get('ahm_scope','normal')
    if scope not in ('normal','all_states') or scope=='all_states' and condition is None:
        raise ValueError('Explicit C0/C1 required for all-state AHM scope')
    if condition is None:return None
    if condition not in ('C0','C1') or any(config.get(k) is not True for k in
            ('all_states_cpg_enabled','automatic_fsm_enabled','physical_button_enabled',
             'physical_touch_enabled','physical_tof_enabled')):
        raise ValueError('Normal AHM requires C0/C1 and existing FSM/input/rhythm owner')
    return condition


def read_stimulus(m,now,details=None):
    """Read cached stable levels; never consume FSM event queues or read I2C."""
    from physical_distance import distance_input_kind
    distance=getattr(m,'physical_distance',None)
    sample=distance.latest() if distance is not None else getattr(m,'distance_view',None)
    views=[]
    for channel in ('button','touch'):
        source=getattr(m,'physical_'+channel,None)
        if source is None:return None
        views.append(source.diagnostics())
    # Samplers may publish after the caller's timestamp; compare only after
    # taking their snapshots, matching the existing distance owner's policy.
    now=max(now,getattr(m,'now',lambda:now)())
    kind=distance_input_kind(sample,now)
    if kind=='fault':return None
    held=False
    for view in views:
        stamp=view.get('last_sample_s')
        if (view.get('sampler_error') or type(view.get('stable_pressed')) is not bool
                or type(stamp) not in (int,float) or not math.isfinite(stamp)
                or not 0<=now-stamp<=.12+1e-9):return None
        held=held or view['stable_pressed']
    gate=getattr(m,'distance_gate',None)
    near=bool(getattr(gate,'near',False))
    # Use latest quality and latest proximity together, without changing the
    # FSM's gate. A fresh Clear must not inherit an older Near latch.
    if kind=='no_target':near=False
    elif kind=='range':near=sample['distance_cm']<28. if near else sample['distance_cm']<=20.
    elif near:
        confirmed=getattr(gate,'last_confirmed_near_s',None)
        if confirmed is not None and now-confirmed>=.5-1e-9:near=False
    if details is not None:details.update(views=views,near=near)
    return float(held or near)


class NormalAHM:
    dt_s=.05
    def __init__(self,condition):
        if condition not in ('C0','C1'):raise ValueError('Expected C0 or C1')
        self.condition=condition;self.h=0.;self.last_time=None
        self.elapsed=0.;self.previous_s=0.;self.interval_s=0.;self.tick_s=None;self.updates=0
        self.input_snapshot=None

    def observe(self,now,stimulus,details,enabled=True):
        """Integrate confirmed GPIO levels at source times, without draining FSM.

        ToF remains a current cache observation, never backdated to GPIO edges.
        History is bounded; overflow or owner gaps reset rather than invent S.
        """
        views=details.get('views',[])
        supported=(len(views)==2 and all(type(v.get('stable_sequence')) is int
                   and isinstance(v.get('stable_edges'),list) for v in views))
        previous=self.input_snapshot
        owner_gap=0. if self.last_time is None else now-self.last_time
        self.input_snapshot=None
        valid=enabled and stimulus is not None and supported
        replayed=0;overflow=False
        if valid and previous is not None and self.last_time is not None and 0<=now-self.last_time<=1.+1e-9:
            levels=list(previous['levels']);events=[]
            for channel,view in enumerate(views):
                edges=[e for e in view['stable_edges'] if e['sequence']>previous['sequences'][channel]]
                if view['stable_sequence']-previous['sequences'][channel]!=len(edges):
                    overflow=True;break
                events.extend((e['time_s'],channel,e['pressed']) for e in edges)
            if not overflow:
                for stamp,group in groupby(sorted(events),key=lambda e:e[0]):
                    changes=list(group)
                    for _,channel,level in changes:levels[channel]=level
                    if stamp<=self.last_time: # simultaneous edges still update the composite level
                        continue
                    if stamp>now:continue
                    self.step(stamp,float(any(levels) or previous['near']))
                    replayed+=len(changes)
        if overflow:
            result=self.step(now,None,enabled=enabled)
            result['reason']='input_history_overflow'
        else:result=self.step(now,stimulus,enabled=enabled)
        if valid:
            self.input_snapshot=dict(levels=[v['stable_pressed'] for v in views],
                sequences=[v['stable_sequence'] for v in views],near=details['near'])
        result['replayed_stable_edges']=replayed
        result['callback_gap_s']=owner_gap
        return result

    def step(self,now,stimulus,enabled=True):
        if (type(now) not in (int,float) or not math.isfinite(now)
                or self.last_time is not None and now<self.last_time):
            raise ValueError('Invalid AHM clock')
        gap=0. if self.last_time is None else now-self.last_time
        valid=type(stimulus) in (int,float) and math.isfinite(stimulus) and 0<=stimulus<=1
        reason=('disabled' if not enabled else 'input_fault' if not valid else 'history_gap' if gap>1.+1e-9 else 'tracking')
        if self.last_time is None:
            self.tick_s=now;self.interval_s=float(stimulus) if valid and enabled else 0.
        if reason!='tracking':
            self.input_snapshot=None
            self.h=0.;self.elapsed=0.;self.tick_s=now
            self.previous_s=self.interval_s=float(stimulus) if valid and enabled else 0.
        else:
            self.elapsed+=gap
            count=int((self.elapsed+1e-9)/self.dt_s)
            for _ in range(count):
                # Lab05: all rates consume old H/R; bound after Euler step.
                old=self.h
                self.h=max(0.,min(1.,old+self.dt_s*(.8*self.interval_s-.6*old-.2*old)))
                self.tick_s+=self.dt_s
                # Preserve the input sampled at the *start* of the open
                # Euler interval, even when calls arrive between grid ticks.
                self.interval_s=float(stimulus) if self.tick_s>=now-1e-9 else self.previous_s
            self.updates+=count;self.elapsed=max(0.,self.elapsed-count*self.dt_s)
            self.previous_s=float(stimulus)
        self.last_time=now
        r=(self.h if self.condition=='C1' else float(stimulus)) if reason=='tracking' else 0.
        return dict(condition=self.condition,stimulus=float(stimulus) if valid else None,h=self.h,
                    r_used=r,phi=.1+.03*r,reason=reason,hormone_dt_s=self.dt_s,
                    hormone_updates=self.updates,stimulus_policy='near_only_v2',
                    callback_gap_s=gap,max_history_gap_s=1.,
                    mapping='hardware_normal_phi_010_013',clock='owner_boottime_fixed_50ms')


def update_from_owner(modulator,m,now):
    # WAIT_TOF is a recoverable output hold, not automatically a sensor
    # fault now: validate the worker cache again. Never authorizes motion.
    enabled=(getattr(m.controller,'state',None) in ('READY','FOLLOWING','WAIT_TOF')
             and not getattr(m,'operator_stopped',False)
             and not any(e is not None and e.is_set() for e in
                         (getattr(m,'stopping',None),getattr(m,'urgent_stop',None))))
    details={}
    stimulus=read_stimulus(m,now,details) if enabled else None
    now=max(now,getattr(m,'now',lambda:now)())
    if isinstance(modulator,NormalAHM):return modulator.observe(now,stimulus,details,enabled=enabled)
    return modulator.step(now,stimulus,enabled=enabled)
