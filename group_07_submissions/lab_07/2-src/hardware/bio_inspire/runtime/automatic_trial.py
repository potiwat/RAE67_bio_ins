"""Opt-in timed experimental inputs; never opens hardware or writes registers.

Actual ToF, UART, camera and STOP remain the existing owner's responsibility.
This adapter only supplies labelled logical events to the existing FSM.
"""
import hashlib
import json
import math
from types import SimpleNamespace

DURATION = 600.
DT = .05
VERSION = 'lab07_scripted_natural_fsm_v2_balanced'
# Five 120s blocks, with all event types in the first block. The final idle
# interval intentionally admits Sleepy; do not fill most of a run with idle.
BUTTON = tuple((base+8.,base+9.) for base in range(0,600,120))
TOUCH = tuple(sorted([(base+30.,base+42.) for base in range(0,600,120)] + [
    (base+52.+offset,base+52.+offset+.15) for base in range(0,600,120) for offset in (0.,.4,.8)]))
NEAR = tuple((base+80.,base+92.) for base in range(0,600,120))

def level_at(intervals,elapsed):
    return any(a<=elapsed<b for a,b in intervals)

def stimulus_at(elapsed):
    return float(any(level_at(intervals,elapsed) for intervals in (BUTTON,TOUCH,NEAR)))

def schedule():
    return dict(version=VERSION,duration_s=DURATION,dt_s=DT,button=BUTTON,touch=TOUCH,near=NEAR,
                source='scripted_experimental_inputs_not_physical_GPIO_or_range',
                ahm='old-H Euler H_next=clamp(H+.05*(.8*S-.6*H-.2*H),0,1)',phi='.10+.03*R')

def schedule_sha256():
    return hashlib.sha256(json.dumps(schedule(),sort_keys=True,separators=(',',':')).encode()).hexdigest()

def validate(config):
    flag=config.get('lab07_automatic_script',False)
    if type(flag)is not bool:raise ValueError('Automatic experiment flag must be Boolean')
    if flag and (config.get('lab07_recording_seconds')!=600 or config.get('lab07_start_button_presses')!=5
            or config.get('automatic_fsm_enabled') is not True or config.get('ahm_scope')!='all_states'
            or config.get('normal_ahm_condition') not in ('C0','C1')):
        raise ValueError('Automatic experiment requires recorded600s gated all-state C0/C1')
    return flag

class ScriptAHM:
    """Condition-independent H reference; C0 reads S, C1 reads H.

    Select the fixed-grid history by elapsed time, retaining skipped callback
    indices instead of inventing an observation at each missed 50ms tick.
    """
    def __init__(self,condition):
        if condition not in ('C0','C1'):raise ValueError('Expected C0/C1')
        self.condition=condition;self.started=None;self.last_time=None;self.last_index=None
        self.skipped=0;self.last_view={};self.h_values=[];self.h=0.
        h=0.
        for i in range(12001):
            self.h_values.append(h)
            h=max(0.,min(1.,h+DT*(.8*stimulus_at(i*DT)-.6*h-.2*h)))
    def start(self,now):
        if self.started is not None or type(now) not in (int,float) or not math.isfinite(now):
            raise ValueError('Finite one-shot experimental start required')
        self.started=now;self.last_time=None
    def step(self,now,stimulus=None,enabled=True):
        if type(now) not in (int,float) or not math.isfinite(now) or self.last_time is not None and now<self.last_time:
            raise ValueError('Invalid experimental clock')
        self.last_time=now
        elapsed=0. if self.started is None else max(0.,now-self.started)
        i=min(12000,int((elapsed+1e-9)/DT))
        if self.last_index is not None and enabled:self.skipped+=max(0,i-self.last_index-1)
        if enabled:self.last_index=i
        s=stimulus_at(i*DT) if self.started is not None else 0.
        self.h=self.h_values[i] if self.started is not None else 0.
        r=(self.h if self.condition=='C1' else s) if enabled else 0.
        self.last_view=dict(condition=self.condition,stimulus=s,h=self.h,r_used=r,phi=.1+.03*r,
            reason='disabled' if not enabled else 'waiting' if self.started is None else 'complete' if elapsed>=DURATION else 'tracking',
            schedule_index=i,skipped_schedule_updates=self.skipped,schedule_sha256=schedule_sha256(),
            elapsed_s=elapsed,duration_s=DURATION,hormone_dt_s=DT,hormone_updates=i,
            stimulus_policy='scripted_button_or_touch_or_near_v1',mapping='hardware_all_states_phi_010_013',
            clock='fixed_50ms_script_selected_by_elapsed_owner_boottime')
        return dict(self.last_view)

class ScriptPort:
    def __init__(self,intervals):
        self.intervals=intervals;self.edge=SimpleNamespace(stable=False);self.pending=[];self.cursor=-1.
    def advance(self,origin,elapsed):
        for a,b in self.intervals:
            if self.cursor<a<=elapsed:self.pending.append(origin+a)
        self.cursor=elapsed;self.edge.stable=level_at(self.intervals,elapsed)
    def drain_events(self,now):
        events=self.pending;self.pending=[];return events
    def discard_pending(self):self.pending=[]

class AutomaticTrial:
    def __init__(self,condition):
        self.replay=ScriptAHM(condition);self.state='waiting';self.reason=None;self.started=None;self.last_callback=None
        self.near=False;self.distance_event=None;self.completion_dispatched=False
        self.pause_started=None;self.distance_pauses=[];self.recovered_from_pause=False
        self.sources=dict(button=ScriptPort(BUTTON),touch=ScriptPort(TOUCH))
    def start(self,now):
        self.replay.start(now);self.started=now;self.state='running';self.last_callback=now
        self.advance(now)
    def advance(self,now):
        elapsed=max(0.,now-self.started)
        for source in self.sources.values():source.advance(self.started,elapsed)
        near=level_at(NEAR,elapsed)
        self.distance_event='near' if near and not self.near else 'clear' if self.near and not near else None
        self.near=near
    def abort(self,m,reason,*,hold=True):
        if self.state=='aborted':return
        self.state='aborted';self.reason=reason
        recorder=getattr(m,'lab07_recorder',None)
        if recorder is not None:recorder.invalid=True
        for port in self.sources.values():port.discard_pending()
        # Existing all-axis hold, not torque release or automatic restart.
        if hold and not getattr(m,'operator_stopped',False):m._key(ord('h'))
    def service(self,m,now):
        if self.state in ('waiting','aborted'):return False
        self.recovered_from_pause=False
        if (getattr(m,'operator_stopped',False) or m.stopping.is_set() or m.urgent_stop.is_set()):
            self.abort(m,'operator_or_controller_hold');return False
        if m.distance_gate.near:
            self.abort(m,'actual_ToF_Near_safety_override');return False
        rec=getattr(m,'lab07_recorder',None)
        if getattr(m,'lab07_recording_error',None) or rec is not None and (getattr(rec,'error',None) or getattr(rec,'dropped',0)):
            self.abort(m,'recorder_error_or_dropped_rows');return False
        if self.last_callback is not None and now-self.last_callback>1.+1e-9:
            self.abort(m,'owner_callback_gap_over_1s');return False
        self.last_callback=now
        # Input time continues during an output hold. Keep recorded Bool levels
        # and queued source edges consistent with the fixed-grid S/H reference.
        self.advance(now)
        if self.pause_started is not None and now-self.pause_started>=.5-1e-9:
            self.abort(m,'ToF_wait_over_0.5s');return False
        if m.controller.state=='WAIT_TOF':
            sample=getattr(m,'distance_view',None) or {}
            if sample.get('error'):
                self.abort(m,'ToF_source_error:'+str(sample['error']));return False
            if self.pause_started is None:
                if len(self.distance_pauses)>=32:
                    self.abort(m,'distance_pause_history_capacity');return False
                self.pause_started=now
                self.distance_pauses.append(dict(start_s=now,end_s=None,reason='existing_WAIT_TOF_hold'))
            if now-self.pause_started>=.5-1e-9:
                self.abort(m,'ToF_wait_over_0.5s')
            # poll_distance already held every axis. Never command motion from
            # a stale sample or reset the hormone/script clock during this wait.
            return False
        if m.controller.state not in ('READY','FOLLOWING'):
            self.abort(m,'controller_'+m.controller.state);return False
        if self.pause_started is not None:
            self.distance_pauses[-1]['end_s']=now
            self.pause_started=None;self.recovered_from_pause=True
        # Drain physical queues for health, but never relabel them as script.
        for name in ('button','touch'):
            source=getattr(m,'physical_'+name,None)
            if source is not None:source.drain_events(now)
        if self.state=='complete':return False
        if now-self.started>=DURATION:
            self.state='complete';self.reason='script_600s_complete'
            return False
        return True
    def status(self,now):
        return dict(state=self.state,reason=self.reason,condition=self.replay.condition,
            source='scripted_experimental_inputs',schedule_sha256=schedule_sha256(),duration_s=DURATION,
            elapsed_s=0. if self.started is None else max(0.,now-self.started),
            button=self.sources['button'].edge.stable,touch=self.sources['touch'].edge.stable,
            near=self.near,distance_event=self.distance_event,
            distance_pauses=[dict(p) for p in self.distance_pauses],
            distance_pause_active=self.pause_started is not None,
            physical_inputs_recorded_separately=True,actual_ToF_safety_override=True)
