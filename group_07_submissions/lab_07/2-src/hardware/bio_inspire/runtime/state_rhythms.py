"""Single-owner routing of previously approved five-state CPG decoders."""
from bio_inspire.runtime.body_rhythm import BodyRhythmDriver
import math


def apply_bank_phi(bank,phi):
    """Install one bounded command after advancing the prior interval."""
    if (type(phi) not in (int,float) or not math.isfinite(phi) or not .1<=phi<=.13
            or not bank or any(not callable(getattr(r,'set_ahm_phi',None))
                               or r.dt_s!=.05 or r.alpha!=1.1 for r in bank.values())):
        raise ValueError('Expected bounded phi and existing SO2 rhythm bank')
    for rhythm in bank.values():rhythm.set_ahm_phi(phi)

class StateRhythms:
    def __init__(self,happy,afraid,normal_ahm=None,ahm_scope='normal'):
        if ahm_scope not in ('normal','all_states'):raise ValueError('Unknown AHM scope')
        if happy is None or afraid is None:raise ValueError('Five-state CPG requires Happy and taught Afraid drivers')
        self.happy=happy;self.afraid=afraid
        self.breathing=BodyRhythmDriver(normal_amplitude_deg=2.,normal_amplitude_mode='manual_1_3',
            interested_amplitude_deg=1.9,sleepy_amplitude_deg=2.,phi=.1,time_scale=.5)
        self.mode='normal';self.active=self.breathing;self.normal_ahm=normal_ahm;self.ahm_scope=ahm_scope
    @property
    def bank(self):return dict(body=self.breathing.rhythm,happy=self.happy.rhythm,afraid=self.afraid.rhythm)
    @property
    def rhythm(self):return self.active.rhythm
    @property
    def manual(self):return self.breathing.manual if self.mode=='normal' else None
    def request_amplitude(self,value,now):
        if self.mode=='normal':self.breathing.request_amplitude(value,now)
    def reset_normal_ahm(self,now):
        if self.normal_ahm is None:return
        value=self.normal_ahm.step(now,None,enabled=False)
        self.breathing.rhythm.set_normal_ahm_phi(.1)
        if self.ahm_scope=='all_states':
            apply_bank_phi(self.bank,.1)
            for rhythm in self.bank.values():
                rhythm.modulation_status={**getattr(rhythm,'modulation_status',{}),
                    'state_ahm':dict(**value,scope='all_states',state=self.mode,applied=False)}
        self.rhythm.modulation_status={**getattr(self.rhythm,'modulation_status',{}),
            'normal_ahm':dict(**value,applied_to_normal=False,effective_phi_next_interval=.1)}
    def step(self,m,now):
        self.mode=getattr(m,'behavior_trial','normal')
        ahm=None
        if self.normal_ahm is not None:
            from bio_inspire.runtime.normal_ahm import update_from_owner
            ahm=update_from_owner(self.normal_ahm,m,now)
            if self.ahm_scope=='normal' and self.mode!='normal':self.breathing.rhythm.set_normal_ahm_phi(.1)
        # Their own strict mode predicates keep inactive specialized decoders
        # phase-continuous without writing goals. Never run the base body
        # decoder in Happy/Afraid where a different decoder owns those joints.
        self.happy.step(m,now);self.afraid.step(m,now)
        if self.mode in ('normal','interested','sleepy','angry'):
            self.active=self.breathing;self.breathing.step(m,now)
        else:
            self.breathing.pause(now)
            self.active=self.afraid if self.mode=='afraid' else self.happy
        if ahm is not None:
            enabled=((self.ahm_scope=='all_states' or self.mode=='normal') and m.controller.state in ('READY','FOLLOWING')
                     and not getattr(m,'operator_stopped',False)
                     and not any(e is not None and e.is_set() for e in
                                 (getattr(m,'stopping',None),getattr(m,'urgent_stop',None))))
            # Advance the prior interval with its prior phi, then install the
            # command for the next interval. Oscillator state is never reset.
            if self.ahm_scope=='all_states':
                apply_bank_phi(self.bank,ahm['phi'] if enabled else .1)
                for rhythm in self.bank.values():
                    rhythm.modulation_status={**getattr(rhythm,'modulation_status',{}),
                        'state_ahm':dict(ahm,scope='all_states',state=self.mode,applied=enabled,
                            mapping='hardware_all_states_phi_010_013_development',phi_next=rhythm.phi)}
            else:self.breathing.rhythm.set_normal_ahm_phi(ahm['phi'] if enabled else .1)
            self.rhythm.modulation_status={**getattr(self.rhythm,'modulation_status',{}),
                'normal_ahm':dict(**ahm,applied_to_normal=enabled and self.mode=='normal',
                                  effective_phi_next_interval=self.breathing.rhythm.phi)}
