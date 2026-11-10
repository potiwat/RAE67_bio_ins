"""Opt-in Lab07 boundary; no device ownership or motion commands."""

def validate_gate(config):
    value=config.get('lab07_start_button_presses')
    if value is None:return False
    if (type(value)is not int or value!=5 or config.get('lab07_recording_seconds') is None
            or config.get('physical_button_enabled') is not True or config.get('automatic_fsm_enabled') is not True):
        raise ValueError('Lab07 button start requires recorded automatic mode and five presses')
    return True

class ButtonStartGate:
    def __init__(self):
        self.count=0;self.sequence=None;self.pending=False
        self.started=False;self.started_s=None;self.release_s=None
    def status(self):
        return dict(started=self.started,presses=self.count,required=5,started_s=self.started_s,source_release_s=self.release_s)
    def observe(self,m,now):
        if self.started:return
        views={name:getattr(m,'physical_'+name).diagnostics() for name in ('button','touch')}
        # The FSM must never see preparation presses or touch bursts.
        for name in views:getattr(m,'physical_'+name).discard_pending()
        button=views['button'];sequence=button['stable_sequence']
        blocked=(m.stopping.is_set() or m.urgent_stop.is_set() or getattr(m,'operator_stopped',False)
                 or m.controller.state not in ('READY','FOLLOWING') or m.behavior_trial!='normal'
                 or getattr(getattr(m,'distance_gate',None),'near',False))
        if blocked:
            self.sequence=sequence;self.pending=False;self.count=0;return
        if any(v.get('sampler_error') for v in views.values()):raise RuntimeError('Lab07 start: input sampler error')
        if self.sequence is None:self.sequence=sequence;return
        edges=[e for e in button['stable_edges'] if e['sequence']>self.sequence]
        if sequence-self.sequence!=len(edges):raise RuntimeError('Lab07 start: lost button history')
        for e in edges:
            if e['pressed']:self.pending=True
            elif self.pending:
                self.pending=False;self.count=min(5,self.count+1);self.release_s=e['time_s']
        self.sequence=sequence
        if self.count==5 and all(v.get('stable_pressed') is False for v in views.values()):
            self.started=True;self.started_s=now

def begin_measurement(m,now):
    """Arm an untouched bank, not a reset of an already moving oscillator."""
    gate=m.lab07_start_gate;driver=m.rhythm_driver
    bank=driver.bank
    if driver.normal_ahm.h!=0. or any(r.updates!=0 or r.origin is not None for r in bank.values()):
        raise RuntimeError('Lab07 start requires untouched hormone/CPG initialization')
    from bio_inspire.runtime.angry_fsm import AngryFSM
    from bio_inspire.runtime.lab_fsm import LabFSM
    a=m.automatic_fsm;factory=AngryFSM if a.angry_enabled else LabFSM
    a.discard_inputs(m,'lab07_start_boundary')
    a.fsm=factory(now,active_timeout_s=a.active_timeout_s,sleep_after_s=a.sleep_after_s,
                  motion_aware=a.motion_aware,happy_timeout_s=a.happy_timeout_s)
    a.applied='normal';a.faulted=False;a.recovering_approach=True;a.approach=False
    m.last_button_event=None;m.last_touch_event=None;m.lab07_fsm_serial=0
    m.lab07_start_marker={**gate.status(), 'initial_h':driver.normal_ahm.h,
        'initial_oscillator_bank':{name:r.status() for name,r in bank.items()},
        'digital_counter_baseline':{name:getattr(m,'physical_'+name).diagnostics()['accepted_presses'] for name in ('button','touch')}}
    trial=getattr(m,'automatic_trial',None)
    if trial is not None:
        trial.start(now)
        driver.normal_ahm=trial.replay
        m.lab07_start_marker['experimental_inputs']=trial.status(now)
    m._service_body_rhythm()
    print('LAB07_START',gate.started_s,'button releases',gate.count,flush=True)
