"""One opt-in, operator-taught Happy recipe. No device or motion owner."""
BODY_CENTERS={2:2654,3:3095}
ROLL_BOUNDS=(1636,2383)
PITCH_WINDOW=(2070,2764)
PHASE_DIVISOR=6.
ENTRY_SECONDS=12.
FAST_PHASE_DIVISOR=8./3.8
FAST_ENTRY_SECONDS=4.


def validate(config):
    flag=config.get('happy_taught_center_trial',False)
    fast=config.get('happy_taught_fast_trial',False)
    if type(fast)is not bool or fast and not flag:raise ValueError('Fast Happy requires taught-center opt-in')
    period=config.get('happy_taught_fast_period_s',8.)
    if type(period) not in (int,float) or period not in (3.8,4.5,5.,6.,8.) or period!=8. and not fast:
        raise ValueError('Fast Happy period must be explicit3.8or4.5or5or6or8 with fast trial')
    dynamic=config.get('happy_dynamic_trial',False)
    if type(dynamic)is not bool or dynamic and (not fast or period not in (3.8,4.5,5.) or config.get('happy_height_probe_trial',False)):
        raise ValueError('Dynamic Happy requires explicit fast taught3.8or4.5or5s, no height probe')
    if period in (3.8,4.5) and not dynamic:raise ValueError('3.8or4.5s requires dynamic Happy')
    wide=config.get('happy_wide_caps_trial',False)
    if type(wide)is not bool or wide and (not dynamic or period!=3.8
            or config.get('fast_awake_trial') is not True or config.get('happy_dance_only') is not True
            or config.get('small_happy_speed_raw')!=1000):
        raise ValueError('Wide Happy caps require dynamic3.8s, awake policy, dance-only and Speed1000')
    head=config.get('happy_taught_head_up_deg',0)
    if type(head)is not int or head not in (0,5) or head and not fast:
        raise ValueError('Happy head offset requires fast taught trial and0or5deg')
    probe=config.get('happy_height_probe_trial',False)
    if type(probe)is not bool or probe and (not fast or period!=8. or head!=0):
        raise ValueError('Height probe requires accepted8s fast Happy with no new head bias')
    step=config.get('happy_height_probe_step_deg',3)
    if type(step)is not int or step not in (3,6) or step!=3 and not probe:
        raise ValueError('Height observation step must be3or6 in explicit probe')
    if type(flag) is not bool:raise ValueError('Taught Happy opt-in must be boolean')
    if flag and any(config.get(k) is not True for k in
            ('small_happy_expanded_trial','automatic_fsm_enabled','native_posture_compensation')):
        raise ValueError('Taught Happy requires expanded automatic compensated Happy')
    return flag


def restore_pitch(m):
    c=m.controller
    if getattr(c,'happy_taught_active',False) is not True:return
    old=getattr(c,'behavior_pitch_window',None) or PITCH_WINDOW
    c.behavior_pitch_window=(min(old[0],PITCH_WINDOW[0],c.pitch_window[0]),
                             max(old[1],PITCH_WINDOW[1],c.pitch_window[1]))
    c.sleepy_return_pending=True;c.interest_pitch_window=None
    c.happy_taught_active=False
