"""Explicit demonstration-only tempo; no hardware I/O or hormone mutation."""
from bio_inspire.runtime.state_rhythms import StateRhythms


def owner_class(config):
    flag=config.get('presentation_happy_hold_tempo',False)
    period=config.get('presentation_happy_period_s')
    entry_yaw=config.get('presentation_happy_entry_yaw',False)
    preserve_yaw=config.get('presentation_normal_preserve_yaw',False)
    roll=config.get('presentation_angry_roll_deg',6)
    if type(roll)is not int or roll not in (6,12,15):raise ValueError('Only reviewed Angry roll6or12or15degrees')
    extra=[config.get(k,False) for k in ('presentation_angry_smooth','presentation_led_breathing','presentation_startup_tof_recovery','presentation_angry_sync_positions','presentation_all_state_sync_positions','presentation_angry_constant_speed25')]
    if any(type(v)is not bool for v in extra):raise ValueError('Presentation Angry/LED flags must be boolean')
    if extra[3] and (not extra[0] or config.get('small_happy_sync_position_trial') is not True
                    or config.get('native_posture_compensation') is not True):
        raise ValueError('Angry Sync requires presentation smooth approach and existing checked Sync transport/head compensation')
    if extra[4] and not extra[3]:raise ValueError('All-state Sync requires the reviewed presentation Angry Sync trial')
    if extra[5] and not extra[4]:raise ValueError('Constant25 Angry trial requires the reviewed all-state presentation profile')
    if roll!=6 and not extra[5]:raise ValueError('Angry increased roll requires accepted presentation constant25 profile')
    if extra[0] and (config.get('angry_face_approach') is not True or config.get('angry_approach_degrees')!=18):
        raise ValueError('Presentation Angry requires existing ToF18degree approach')
    if type(preserve_yaw)is not bool:raise ValueError('Presentation Normal yaw flag must be boolean')
    if type(entry_yaw)is not bool:raise ValueError('Presentation entry yaw must be boolean')
    if type(flag)is not bool:
        raise ValueError('Presentation tempo flag must be boolean')
    if not flag:
        if period is not None or entry_yaw or preserve_yaw or any(extra):raise ValueError('Presentation options require presentation tempo opt-in')
        return StateRhythms
    if period is not None and (type(period) not in (int,float) or period!=2.5):
        raise ValueError('Only approved presentation Happy target 2.5s')
    if (config.get('presentation_mode') is not True
            or config.get('normal_ahm_condition')!='C1'
            or config.get('ahm_scope')!='all_states'
            or config.get('all_states_cpg_enabled') is not True
            or config.get('happy_dance_only') is not True
            or config.get('happy_wide_caps_trial') is not True
            or config.get('happy_taught_fast_period_s')!=3.8
            or config.get('small_happy_speed_raw')!=1000
            or any(config.get(k) is not None for k in
                   ('normal_measurement_source','lab07_recording_seconds','lab07_start_button_presses'))
            or config.get('lab07_automatic_script',False) is not False):
        raise ValueError('Presentation tempo requires live C1 Happy; measurement/replay forbidden')
    if period is not None or entry_yaw:
        from functools import partial
        return partial(PresentationRhythms,happy_period_s=period,entry_yaw=entry_yaw)
    return PresentationRhythms


class PresentationRhythms(StateRhythms):
    def __init__(self,*args,happy_period_s=None,entry_yaw=False,**kwargs):
        super().__init__(*args,**kwargs)
        if type(entry_yaw)is not bool:raise ValueError('Presentation entry yaw must be boolean')
        if entry_yaw:self.happy.presentation_entry_yaw=True
        self.presentation_target_period_s=happy_period_s
        if happy_period_s is not None:
            if type(happy_period_s) not in (int,float) or happy_period_s!=2.5:
                raise ValueError('Unapproved presentation period')
            # Existing phi=.13 fast demo measured ~2.81s per path cycle.
            # Change only this decoder's phase scale; native/host limits stay.
            self.happy.phase_divisor*=happy_period_s/2.81

    def step(self,m,now):
        super().step(m,now)
        status=self.happy.rhythm.modulation_status.get('state_ahm',{})
        if self.mode=='happy' and status.get('applied') is True:
            # Same bounded phi already reached while Touch was held. Preserve
            # the real S/H and phase; install only the next Happy interval.
            self.happy.rhythm.set_ahm_phi(.13)
            self.happy.rhythm.modulation_status={
                **self.happy.rhythm.modulation_status,
                'state_ahm':{**status,'phi_next':.13,
                    'presentation_tempo_override':True,
                    'presentation_target_period_s':self.presentation_target_period_s,
                    'mapping':'presentation_happy_fixed_phi_013'}}
