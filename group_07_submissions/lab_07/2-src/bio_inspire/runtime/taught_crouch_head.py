"""Empirical postural reference + visual correction; not a calibrated IK model."""
from bounded_motion import BoundedMotion,MotionLimits
import math


class TaughtCrouchHead:
    def __init__(self,visual,initial,now,native_posture=False):
        self.visual=visual;self.reference=initial
        self.native_posture=native_posture
        visual.reset(initial,now)
        self.motion=BoundedMotion(initial,now,MotionLimits(visual.low,visual.high,
            visual.max_speed,visual.max_acceleration,visual.max_dt))

    def step(self,reference,error,now,measurement,target_window=None):
        v=self.visual
        if type(reference) not in (int,float) or not math.isfinite(reference):raise ValueError('Finite postural reference required')
        # Translate the postural base, preserving the visual offset/filter.
        # Only the final combined command is sent, with the existing V/A caps.
        v.position=max(v.low,min(v.high,v.position+reference-self.reference))
        self.reference=reference
        desired=v.step(error,now,measurement)
        if target_window is not None:desired=max(target_window[0],min(target_window[1],desired))
        if self.native_posture:
            # The deterministic posture target is handled by the native ramp.
            # VisualServo still filters and limits the corrective component;
            # do not make the posture wait through a second host position ramp.
            self.motion.position=float(desired);self.motion.velocity=v.velocity;self.motion.time=now
            return round(desired)
        return round(self.motion.step(desired,now))

    def contract(self,low,high):
        v=self.visual;p=self.motion.position;speed=self.motion.velocity;a=self.motion.limits.acceleration
        if not low<=p<=high or not low<=v.position<=high:return False
        if speed>0 and speed*speed/(2*a)>high-p:return False
        if speed<0 and speed*speed/(2*a)>p-low:return False
        k=self.motion.limits
        self.motion.limits=MotionLimits(low,high,k.speed,k.acceleration,k.max_dt)
        v.low,v.high=low,high
        return True
