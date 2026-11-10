"""Image-error velocity control with bounded acceleration and integrated yaw.

Normal is only an initial reference, never the commanded angle for zero error.
All gains and bounds are supplied by the approved experiment profile.
"""
import math


class VisualServo:
    def __init__(self,low,high,max_speed,max_acceleration,beta,deadband,half_width,max_dt):
        values=(low,high,max_speed,max_acceleration,beta,deadband,half_width,max_dt)
        if not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in values):
            raise ValueError('Nonfinite visual servo parameters')
        if not low<high or min(max_speed,max_acceleration,max_dt)<=0 or not 0<beta<=1 or not 0<=deadband<half_width:
            raise ValueError('Invalid visual servo bounds/gains')
        self.low=low;self.high=high;self.max_speed=max_speed;self.max_acceleration=max_acceleration
        self.beta=beta;self.deadband=deadband;self.half_width=half_width;self.max_dt=max_dt
        self.position=None;self.velocity=0.;self.filtered_error=0.;self.time=None;self.last_measurement=None
    def reset(self,actual,now):
        if not math.isfinite(actual) or not self.low<=actual<=self.high or not math.isfinite(now):
            raise ValueError('Invalid initial heading/time')
        self.position=float(actual);self.velocity=0.;self.filtered_error=0.;self.time=now
        self.last_measurement=None
    def step(self,error,now,measurement_id):
        if self.position is None:raise RuntimeError('Reset to measured heading before following')
        if not math.isfinite(now) or not 0<=now-self.time<=self.max_dt:
            raise ValueError(f'Control interval dt={now-self.time:.3f}s exceeds {self.max_dt}s or clock invalid')
        dt=now-self.time
        if error is None:
            self.filtered_error=0.;desired_velocity=0.
        else:
            if not math.isfinite(error) or abs(error)>self.half_width:
                raise ValueError('Invalid image error')
            if measurement_id!=self.last_measurement:
                # Filter the measurement first; deadband belongs to the filtered
                # signal, not an abrupt reset of filter state at the raw edge.
                self.filtered_error=self.beta*error+(1-self.beta)*self.filtered_error
                self.last_measurement=measurement_id
            magnitude=max(0.,abs(self.filtered_error)-self.deadband)/(self.half_width-self.deadband)
            desired_velocity=math.copysign(self.max_speed*min(1.,magnitude),self.filtered_error)
        previous_velocity=self.velocity
        change=self.max_acceleration*dt
        self.velocity+=max(-change,min(change,desired_velocity-self.velocity))
        if dt:
            # Reserve enough distance to stop after this trapezoidal step.
            # Solve v_next^2/(2a) + (v_old+v_next)*dt/2 <= distance.
            a=self.max_acceleration
            if self.velocity>0:
                distance=self.high-self.position
                limit=max(0.,(-a*dt+math.sqrt(max(0.,(a*dt)**2-4*a*dt*previous_velocity+8*a*distance)))/2)
                self.velocity=min(self.velocity,limit)
            elif self.velocity<0:
                distance=self.position-self.low
                limit=max(0.,(-a*dt+math.sqrt(max(0.,(a*dt)**2+4*a*dt*previous_velocity+8*a*distance)))/2)
                self.velocity=max(self.velocity,-limit)
        travel_dt=dt
        if self.velocity==0 and previous_velocity:
            # A stop can finish inside a long cycle; do not coast for the rest.
            travel_dt=min(dt,abs(previous_velocity)/self.max_acceleration)
        position=self.position+(previous_velocity+self.velocity)*.5*travel_dt
        self.position=max(self.low,min(self.high,position))
        if position<=self.low and self.velocity<0 or position>=self.high and self.velocity>0:self.velocity=0.
        self.time=now
        return self.position
