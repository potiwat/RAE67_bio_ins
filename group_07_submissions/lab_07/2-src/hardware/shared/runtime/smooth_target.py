"""Lab02 low-pass plus Lab06 bounded step, parameters supplied by caller."""
import math


class SmoothTarget:
    def __init__(self,beta,max_rate):
        if not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in (beta,max_rate)) or not 0<beta<=1 or max_rate<=0:
            raise ValueError('Invalid beta/rate')
        self.beta=beta;self.max_rate=max_rate;self.filtered=None;self.value=None;self.time=None
    def reset(self,value,now):
        if not all(math.isfinite(v) for v in (value,now)):raise ValueError('Invalid filter state')
        self.filtered=float(value);self.value=float(value);self.time=now
    def update(self,target,now):
        if not all(math.isfinite(v) for v in (target,now)) or (self.time is not None and now<self.time):
            raise ValueError('Invalid target/clock')
        if self.value is None:self.reset(target,now);return self.value
        dt=max(0.,now-self.time)
        self.filtered=self.beta*target+(1-self.beta)*self.filtered
        step=self.max_rate*dt
        self.value+=max(-step,min(step,self.filtered-self.value));self.time=now
        return self.value
