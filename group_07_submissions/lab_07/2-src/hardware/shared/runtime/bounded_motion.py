"""Continuous floating command follower; limits are caller-supplied host limits.

Not measured actuator velocity/acceleration, and not a jerk-limit certificate.
Round ONLY after composing all motion layers and advancing this state.
"""
import math
from dataclasses import dataclass

def finite(x):return type(x) in (int,float) and math.isfinite(x)

@dataclass(frozen=True,slots=True)
class MotionLimits:
    low:float
    high:float
    speed:float
    acceleration:float
    max_dt:float
    def __post_init__(self):
        if not all(finite(v) for v in (self.low,self.high,self.speed,self.acceleration,self.max_dt)) or not self.low<self.high or min(self.speed,self.acceleration,self.max_dt)<=0:
            raise ValueError('Finite explicit command limits required')

class BoundedMotion:
    def __init__(self,position,now,limits):
        if not isinstance(limits,MotionLimits) or not finite(position) or not limits.low<=position<=limits.high or not finite(now):raise ValueError('Invalid initial command state')
        self.position=float(position);self.velocity=0.;self.time=now;self.limits=limits
    def step(self,target,now):
        k=self.limits
        if not finite(target) or not k.low<=target<=k.high or not finite(now) or not 0<=now-self.time<=k.max_dt:raise ValueError('Invalid target/control time')
        dt=now-self.time
        if not dt:return self.position
        distance=target-self.position
        # Reserve braking distance to the requested target as well as the
        # outer limits. sqrt(2*a*d) alone ignores this cycle's travel and causes
        # a persistent sampled-data limit cycle around an interior target.
        sign=1. if distance>=0 else -1.
        parallel=self.velocity*sign;a=k.acceleration
        arrival=max(0.,(-a*dt+math.sqrt(max(0.,(a*dt)**2-4*a*dt*parallel+8*a*abs(distance))))/2)
        desired=sign*min(k.speed,arrival)
        previous=self.velocity;change=k.acceleration*dt
        velocity=previous+max(-change,min(change,desired-previous))
        # Same trapezoidal stopping-distance reservation as VisualServo;
        # the outer limits protect the final sum, not merely its components.
        a=k.acceleration
        if velocity>0:
            room=k.high-self.position
            limit=max(0.,(-a*dt+math.sqrt(max(0.,(a*dt)**2-4*a*dt*previous+8*a*room)))/2)
            velocity=min(velocity,limit)
        elif velocity<0:
            room=self.position-k.low
            limit=max(0.,(-a*dt+math.sqrt(max(0.,(a*dt)**2+4*a*dt*previous+8*a*room)))/2)
            velocity=max(velocity,-limit)
        travel_dt=dt
        if velocity==0 and previous:travel_dt=min(dt,abs(previous)/a)
        position=self.position+(previous+velocity)*.5*travel_dt
        self.position=max(k.low,min(k.high,position));self.velocity=velocity;self.time=now
        return self.position
