"""Pure joint-reference arbitration. No clocks, oscillator state, or UART access.

Offsets use encoder ticks, not radians. The caller converts its model units and
owns phase/envelope updates. Exclusive actions suppress both additive layers;
STOP/FAULT return no goal and leave holding to the existing motor owner.
"""
import math

JOINTS=set(range(1,6))

def compose_goals(base,bounds,*,cpg=None,gaze=None,cpg_enabled=False,
                  gaze_enabled=False,exclusive=False,state='READY'):
    if state in ('IDLE','FAULT','STOPPED'):return None
    if state not in ('READY','FOLLOWING','NORMAL_STARTUP'):
        raise ValueError('Unknown motion state')
    if set(base)!=JOINTS or set(bounds)!=JOINTS:
        raise ValueError('Five joint references and bounds required')
    layers=(base,cpg or {},gaze or {})
    for layer in layers:
        if not set(layer)<=JOINTS or any(type(v) not in (int,float) or not math.isfinite(v) for v in layer.values()):
            raise ValueError('Invalid joint reference')
    result={}
    for i in sorted(JOINTS):
        low,high=bounds[i]
        if any(type(v) not in (int,float) or not math.isfinite(v) for v in (low,high)) or not 0<=low<=high<=4095:
            raise ValueError('Invalid reviewed bounds')
        # Startup and pose actions own the reference; oscillator keeps running
        # upstream, but cannot change the protected action's motor targets.
        protected=exclusive or state=='NORMAL_STARTUP'
        value=base[i]
        if not protected and cpg_enabled:value+=(cpg or {}).get(i,0)
        if not protected and gaze_enabled:value+=(gaze or {}).get(i,0)
        if not math.isfinite(value) or not low<=value<=high:
            raise ValueError(f'Combined reference outside reviewed range: ID{i}')
        result[i]=round(value)
        if not low<=result[i]<=high:
            raise ValueError(f'Rounded reference outside reviewed range: ID{i}')
    return result
