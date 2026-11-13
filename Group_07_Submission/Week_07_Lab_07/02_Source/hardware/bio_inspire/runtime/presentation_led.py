"""Demonstration-only LED breathing, approved 5 to 8 percent brightness."""
import math
import subprocess

COLORS=dict(normal=(255,255,255),interested=(255,100,0),happy=(255,180,40),
            angry=(255,0,0),afraid=(180,60,255),sleepy=(40,100,255))


def service_breathing(m,state,force=False):
    if state not in COLORS:return
    if getattr(m,'presentation_led_disabled',False):return
    now=m.now()
    if not hasattr(m,'presentation_led_origin_s'):m.presentation_led_origin_s=now
    if not force and now-getattr(m,'presentation_led_last_s',-math.inf)<.1:return
    brightness=.05+.03*.5*(1+math.cos(2*math.pi*(now-m.presentation_led_origin_s)/5.))
    color=COLORS[state]  # Do not pre-dim RGB and lose low-valued channels twice.
    try:
        if m.led_ring is None:
            from led_ring import LedRing
            m.led_ring=LedRing()
            force=True
        if force or (color,brightness)!=getattr(m,'presentation_led_last_frame',None):m.led_ring.show_color(color,brightness=brightness)
    except (OSError,RuntimeError,subprocess.SubprocessError) as error:
        # Decorative output failure must not terminate the motor worker.
        # Disable retries for this owner lifetime; never re-arm motor safety.
        m.presentation_led_disabled=True
        m.presentation_led_output=dict(state=state,disabled=True,error=str(error),failed_s=now)
        ring=m.led_ring;m.led_ring=None
        try:
            if ring is not None:ring.close()
        except (OSError,RuntimeError,subprocess.SubprocessError) as cleanup_error:
            m.presentation_led_output['cleanup_error']=str(cleanup_error)
        print('PRESENTATION_LED_DISABLED',m.presentation_led_output,flush=True)
        return
    m.last_led_behavior=state;m.presentation_led_last_s=now;m.presentation_led_last_color=color
    m.presentation_led_last_frame=(color,brightness)
    m.presentation_led_output=dict(state=state,rgb_255=color,period_s=5.,brightness_ceiling=.08,
                                   requested_brightness=brightness,actual_color_quantized=True)
