"""Provisional ID1 stall/effort pause logic; not a force or safety controller.

Pilot thresholds are reviewed trial values, not identified collision forces.
This module has no UART access and never resumes because effort decreased.
"""
import math
from collections import deque

class ID1PauseGuard:
    internal_error_ticks=12
    effort_duty_raw=32
    effort_current_raw=3
    window_s=.30
    minimum_samples=4
    position_span_ticks=2
    maximum_feedback_age_s=.18
    maximum_feedback_gap_s=.20
    def __init__(self):
        self.state='MONITORING';self.reason=None;self.history=deque();self.last_now=None;self.last_stamp=None
    def _result(self,trip=False):return dict(state=self.state,reason=self.reason,trip=trip)
    def _fault(self,reason):
        self.state='FAULT_HOLD';self.reason=reason;self.history.clear();return self._result()
    def update(self,row,now):
        if (type(now) not in (int,float) or not math.isfinite(now)
            or self.last_now is not None and now<self.last_now):return self._fault('invalid/regressing owner time')
        self.last_now=now
        if self.state=='FAULT_HOLD':return self._result()
        t=row.get('sampled_monotonic_s')
        if (type(t) not in (int,float) or not math.isfinite(t) or not 0<=now-t<=self.maximum_feedback_age_s
            or self.last_stamp is not None and (t<self.last_stamp or t-self.last_stamp>self.maximum_feedback_gap_s)):
            return self._fault('stale/gapped/regressing feedback')
        if row.get('id')!=1 or row.get('mode')!=0 or row.get('torque_raw')!=1 or row.get('status_raw')!=0:
            return self._fault('ID1 status/mode/torque invalid')
        for key,maximum in [('position_raw',4095),('goal_raw',4095),('internal_target_raw',4095),('load_raw',2047),('current_raw',65535)]:
            if type(row.get(key)) is not int or not 0<=row[key]<=maximum:return self._fault('invalid '+key)
        if t==self.last_stamp:return self._result()
        self.last_stamp=t
        if self.state=='RESISTANCE_PAUSE':return self._result()
        error=row['internal_target_raw']-row['position_raw'];sign=1 if error>0 else -1
        effort=(row['load_raw']&1023)>=self.effort_duty_raw or row['current_raw']>=self.effort_current_raw
        if abs(error)<self.internal_error_ticks or not effort:
            self.history.clear();return self._result()
        if self.history and self.history[-1][2]!=sign:self.history.clear()
        self.history.append((t,row['position_raw'],sign))
        # Keep one sample on/before the time boundary; real UART intervals vary.
        while len(self.history)>1 and t-self.history[1][0]>=self.window_s:self.history.popleft()
        span=max(x[1] for x in self.history)-min(x[1] for x in self.history)
        if (len(self.history)>=self.minimum_samples and t-self.history[0][0]>=self.window_s-1e-9
            and span<=self.position_span_ticks):
            self.state='RESISTANCE_PAUSE';self.reason='sustained internal error + effort + little encoder progress'
            return self._result(trip=True)
        return self._result()
    def resume(self,*,clearance_confirmed):
        if clearance_confirmed is not True or self.state!='RESISTANCE_PAUSE':
            raise ValueError('Explicit operator clearance required; faults cannot resume here')
        self.state='MONITORING';self.reason=None;self.history.clear();self.last_now=None;self.last_stamp=None
