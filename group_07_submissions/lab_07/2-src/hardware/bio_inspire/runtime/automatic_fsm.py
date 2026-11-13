"""Real-input adapter for the retained Lab FSM; one existing UART owner."""
import csv
import json
import math
from bio_inspire.runtime.lab_fsm import LabFSM
from physical_distance import distance_input_kind

def validate_approach_config(config):
    flag=config.get('approach_requires_face',False)
    if type(flag)is not bool or flag and any(config.get(k)is not True for k in
            ('automatic_fsm_enabled','physical_tof_enabled','gaze_enabled')):
        raise ValueError('Face-confirmed Approach requires automatic ToF and gaze')
    scan=config.get('approach_scan_arrival',False)
    if type(scan)is not bool or scan and (not flag or config.get('yaw_face_scan_enabled') is not True):
        raise ValueError('Scan Approach requires face-confirmed yaw acquisition')
    return flag


def current_selected_face(m,now):
    result=getattr(m,'latest_result',None) or {};obs=result.get('observation') or {}
    intent=result.get('intent') or {};stamp=obs.get('captured_s');box=obs.get('box')
    if (obs.get('status') not in ('ACQUIRED','TRACKING') or intent.get('mode') not in ('FOLLOW','FOLLOW_DROOP')
            or type(stamp) not in (int,float) or not math.isfinite(stamp) or not 0<=now-stamp<=.5
            or not isinstance(box,(tuple,list)) or len(box)!=4
            or any(type(v) not in (int,float) or not math.isfinite(v) for v in box)):
        return False
    x,y,w,h=box
    return x>=0 and y>=0 and w>0 and h>0 and x+w<=1.+1e-9 and y+h<=1.+1e-9


class AutomaticFSM:
    def __init__(self,*,motion_aware=False,active_timeout_s=2.,sleep_after_s=6.,angry_enabled=False,happy_timeout_s=None,approach_requires_face=False,approach_scan_arrival=False):
        if type(approach_requires_face)is not bool:raise ValueError('Approach face gate must be boolean')
        self.approach_requires_face=approach_requires_face;self.pending_approach=None
        if type(approach_scan_arrival)is not bool or approach_scan_arrival and not approach_requires_face:
            raise ValueError('Scan Approach requires face confirmation')
        self.approach_scan_arrival=approach_scan_arrival
        self.scan_arrival=None;self.scan_serial=0;self.last_auto_approach_s=None
        self.happy_timeout_s=happy_timeout_s
        self.fsm=None;self.applied='normal';self.approach=False
        self.last_approach_s=None;self.faulted=False;self.last_dispatch=None
        self.sleep_after_s=sleep_after_s;self.motion_aware=motion_aware;self.active_timeout_s=active_timeout_s
        self.no_target_since=None;self.recovering_approach=False
        self.angry_enabled=angry_enabled
        from bio_inspire.runtime.angry_fsm import TouchBurst
        self.touch_burst=TouchBurst() if angry_enabled else None
        self.last_input_gate=None
    def snapshot(self):
        return dict(state='normal' if self.fsm is None else self.fsm.state,
                    last_activity_s=None if self.fsm is None else self.fsm.last_activity,
                    entry_s=None if self.fsm is None else self.fsm.entry,
                    last_event=None if self.fsm is None else self.fsm.last_winner,
                    last_dispatch=self.last_dispatch,source_fault=self.faulted,
                    active_timeout_s=self.active_timeout_s,happy_timeout_s=self.happy_timeout_s,sleep_after_s=self.sleep_after_s,motion_aware=self.motion_aware,
                    timer_ready=None if self.fsm is None else self.fsm.clock_ready,
                    approach_requires_face=self.approach_requires_face,approach_waiting_for_face=self.pending_approach is not None,
                    approach_scan_arrival=self.approach_scan_arrival,last_auto_approach_s=self.last_auto_approach_s,
                    angry_enabled=self.angry_enabled,touch_burst_count=0 if self.touch_burst is None else len(self.touch_burst.times),
                    last_input_gate=self.last_input_gate,angry_near_deferred=self.fsm is not None and self.fsm.state=='angry' and getattr(self.fsm,'near_active',False))
    @staticmethod
    def digital_events(source,now):
        drain=getattr(source,'drain_events',None)
        if callable(drain):
            stamps=drain(now)
            if isinstance(stamps,(list,tuple)):
                if len(stamps)>180 or any(type(t) not in (int,float) or not math.isfinite(t) for t in stamps):
                    raise ValueError('Invalid bounded digital input events')
                return stamps
        if not source.poll(now):return []
        stamp=getattr(source,'last_event_s',None)
        if type(stamp) not in (int,float):stamp=getattr(getattr(source,'edge',None),'since',now)
        return [stamp if type(stamp) in (int,float) else now]
    def fault(self,now,source_id='hardware_fault'):
        if self.fsm is not None and not self.faulted:
            self.fsm.step(now,[dict(kind='fault',source_s=now,source_id=source_id)])
        self.faulted=True;self.applied=None
        self.recovering_approach=True
        self.pending_approach=None
        self.no_target_since=None
        if self.touch_burst is not None:self.touch_burst.clear()
    def timer_ready(self,m):
        state=self.fsm.state;c=m.controller
        if self.applied!=state or getattr(m,'pending_behavior',None) is not None:return False
        route=getattr(c,'pose_route',None)
        if state=='interested' and getattr(route,'waiting_for_player',False):return True
        if getattr(m,'behavior_trial','normal')!=state:return False
        if getattr(route,'phase',None) in ('look','return','lean','tilt'):return False
        if state=='interested' and getattr(m,'interested_roll_due',None) is not None:return False
        if state=='happy':
            if getattr(m,'happy_height_probe_trial',False) is True:return False
            if getattr(m,'happy_head_wake_goal',None) is not None:return False
            cache=getattr(m,'rhythm_view_cache',{}) or {}
            if cache.get('small_happy')!='running' or cache.get('envelope',0.)<1.:return False
        return True
    def service(self,m,now):
        if m.stopping.is_set() or m.urgent_stop.is_set() or getattr(m,'operator_stopped',False):
            trial=getattr(m,'automatic_trial',None)
            if trial is not None and trial.state=='running':trial.abort(m,'operator_stop_or_closing')
            self.discard_inputs(m,'operator_stop_or_closing');return
        from bio_inspire.runtime.distance_behavior import poll_distance
        poll_distance(m,now,dispatch=False)
        c=m.controller;now=m.now()
        trial=getattr(m,'automatic_trial',None)
        if trial is not None and not trial.service(m,now):
            if trial.state=='complete' and not trial.completion_dispatched:
                trial.completion_dispatched=True
                self.discard_inputs(m,'experimental_complete')
                self.fsm.step(now,[dict(kind='clear',source_s=now,source_id='experimental_complete')])
                if self.dispatch(m,'normal','clear'):self.applied='normal'
            return
        if trial is not None and trial.recovered_from_pause:
            # poll_distance restored healthy READY feedback, but its hold left
            # behavior=distance_wait. Re-enter the existing FSM state's route;
            # do not strand it just because the FSM name did not change.
            self.applied=None
        if c.state not in ('READY','FOLLOWING'):
            self.discard_inputs(m,'controller_'+c.state)
            if self.fsm is not None and c.state in ('FAULT','WAIT_TOF','STOPPED') and not self.faulted:
                self.fault(now)
            return
        initializing=self.fsm is None
        if initializing:
            self.discard_inputs(m,'initializing')
            from bio_inspire.runtime.angry_fsm import AngryFSM
            factory=AngryFSM if self.angry_enabled else LabFSM
            self.fsm=factory(now,active_timeout_s=self.active_timeout_s,sleep_after_s=self.sleep_after_s,motion_aware=self.motion_aware,happy_timeout_s=self.happy_timeout_s)
        self.faulted=False;events={}
        sample=(getattr(m,'distance_view',None) or {});gate=m.distance_gate
        if trial is not None:
            # Logical Near/Clear is scripted. Do not mutate the physical gate
            # or fabricate a range reading in /lamp/input/distance.
            from types import SimpleNamespace
            gate=SimpleNamespace(near=trial.near)
            sample={**sample,'event':trial.distance_event,'received_s':now}
        def add(kind,source_s=None,source_id=None):
            events.setdefault(kind,dict(kind=kind,source_s=now if source_s is None else source_s,
                                       source_id=source_id or (f'script_{kind}_{int((now-trial.started)/.05)}' if trial is not None else f'tof_{sample.get("sequence",0)}')))
        if sample.get('event') in ('near','clear'):add(sample['event'],sample.get('received_s',now))
        if gate.near and self.fsm.state!='afraid':add('near',sample.get('received_s',now))
        if not gate.near and self.fsm.state=='afraid':add('clear',sample.get('received_s',now))
        route=getattr(c,'pose_route',None)
        approach_eligible=(trial is None and self.fsm.state in ('normal','sleepy')
            and getattr(m,'behavior_trial','normal')==self.fsm.state
            and getattr(m,'pending_behavior',None) is None
            and getattr(route,'phase',None) not in ('look','return','lean','tilt'))
        if not approach_eligible:self.recovering_approach=True
        arrival_cm=50. if self.approach_scan_arrival else 80.
        kind=distance_input_kind(sample,now);old=self.approach
        if kind=='range':
            self.approach=sample['distance_cm']<95. if old else sample['distance_cm']<=arrival_cm
            self.last_approach_s=sample['received_s'] if self.approach else None
            self.no_target_since=None
        elif kind=='no_target':
            if self.no_target_since is None:self.no_target_since=sample['received_s']
            if now-self.no_target_since>=.5-1e-9:self.approach=False;self.last_approach_s=None
        else:
            # Unknown quality is not evidence that a player left and arrived.
            self.no_target_since=None
        recovering=self.recovering_approach or initializing
        if approach_eligible and (kind=='range' or (kind=='no_target' and now-self.no_target_since>=.5-1e-9)):self.recovering_approach=False
        if self.approach_requires_face:
            if not approach_eligible or recovering or gate.near or kind!='range' or not self.approach:
                self.pending_approach=None
            elif self.approach and not old:
                self.pending_approach=dict(kind='approach',source_s=sample.get('received_s',now),
                                           source_id=f'tof_{sample.get("sequence",0)}')
            pending=self.pending_approach
            if pending is not None:
                if now-pending['source_s']>.5:self.pending_approach=None
                elif (sample['distance_cm']<=arrival_cm and current_selected_face(m,now)
                      and not (self.approach_scan_arrival and any(getattr(m,k,None) is not None for k in ('yaw_face_scan','yaw_scan_handoff')))):
                    add('approach',pending['source_s'],pending['source_id']);self.pending_approach=None
        elif approach_eligible and self.approach and not old and not gate.near and not recovering:
            add('approach',sample.get('received_s',now))
        if self.approach_scan_arrival:
            self.scan_approach(m,now,sample,kind,approach_eligible and not recovering and not gate.near,add)
            if self.last_auto_approach_s is not None and now-self.last_auto_approach_s<30.:
                events.pop('approach',None);self.pending_approach=None;self.scan_arrival=None
        # Approach departure only rearms arrival detection. Clear is exclusively
        # the Near20/Clear28 gate event, never a lost80/95cm object while dancing.
        held=False
        route=getattr(c,'pose_route',None)
        if (self.fsm.state=='interested' and getattr(m,'behavior_trial',None)=='interested'
                and getattr(route,'phase',None)=='complete' and getattr(route,'interested_upright_requested',False)):
            roll=next((r for r in c.last_rows if r['id']==4),None)
            if (roll is not None and not roll['speed_raw'] and not roll['moving_raw']
                    and abs(roll['position_raw']-c.normal[4])<=c.normal_tolerances[4]):
                add('timeout',now,'interested_gesture_complete')
        if self.fsm.state=='interested' and getattr(route,'phase',None) in ('lean','return') and getattr(route,'gaze_wait_elapsed_s',0.)>=self.active_timeout_s:
            add('timeout',now,'interested_gaze_wait_budget')
        if (self.fsm.state=='angry' and getattr(route,'phase',None)=='lean'
                and getattr(route,'waiting_for_player',False) and getattr(route,'gaze_wait_elapsed_s',0.)>=self.active_timeout_s):
            add('timeout',now,'angry_head_wait_budget')
        level_start=getattr(route,'angry_level_started_s',None)
        if (self.fsm.state=='angry' and getattr(route,'phase',None)=='return'
                and type(level_start) in (int,float) and math.isfinite(level_start) and now-level_start>=12.):
            add('timeout',now,'angry_level_entry_budget')
        burst_blocked=gate.near or self.fsm.state in ('afraid','angry')
        if burst_blocked and self.touch_burst is not None:
            # Clearing just the counter leaves old debounced presses in the
            # sampler queue, which could replay after Clear/Angry timeout.
            self.discard_inputs(m,'blocked_'+self.fsm.state)
        for channel in ('touch','button'):
            source=trial.sources[channel] if trial is not None else getattr(m,'physical_'+channel,None)
            if source is None:continue
            held=held or getattr(getattr(source,'edge',None),'stable',None) is True
            for source_s in self.digital_events(source,now):
                field=channel+'_sequence';serial=getattr(m,field,0)+1;setattr(m,field,serial)
                source_id=('script_' if trial is not None else '')+f'{channel}_{serial:06d}';add(channel,source_s,source_id)
                if channel=='touch' and self.touch_burst is not None and not burst_blocked and self.touch_burst.press(source_s,now):
                    add('touch_burst',source_s,source_id+'_burst')
                setattr(m,'last_'+channel+'_event',dict(source_id=source_id,source_s=source_s,recognized_s=now,status='fsm_candidate'))
        # Isolated Happy observation: ordinary interaction/clear events must
        # not cut an endpoint capture short. Near/fault/STOP still preempt.
        if getattr(m,'happy_height_probe_trial',False) is True and self.fsm.state=='happy':
            suppressed=[kind for kind in events if kind!='near']
            if suppressed:self.last_input_gate=dict(reason='happy_height_observation',time_s=now,suppressed_kinds=suppressed)
            events={kind:event for kind,event in events.items() if kind=='near'}
        prior_serial=self.fsm.serial
        winner=self.fsm.step(now,list(events.values()),ready=self.timer_ready(m),held=held)
        if m.stopping.is_set() or m.urgent_stop.is_set() or getattr(m,'operator_stopped',False):return
        if winner is not None and winner['kind']=='approach' and self.fsm.state=='interested':
            self.last_auto_approach_s=now
        replay_button=winner is not None and winner['kind']=='button' and self.fsm.state=='interested' and winner['status']=='no_state_change'
        if self.applied!=self.fsm.state or replay_button:
            admitted=self.dispatch(m,self.fsm.state,None if winner is None else winner['kind'])
            if admitted and c.state not in ('FAULT','STOPPED','WAIT_TOF'):
                self.applied=self.fsm.state
                self.last_dispatch=dict(time_s=m.now(),state=self.applied,trigger=None if winner is None else winner['kind'],behavior=m.behavior_trial)
                if winner is not None:winner['dispatch_s']=m.now()
        added=self.fsm.serial-prior_serial
        if added:
            cache={**getattr(c,'last_joint_targets',{}),1:getattr(c,'last_goal',None),4:getattr(c,'current_roll_goal',None),5:getattr(c,'last_pitch_goal',None)}
            route=getattr(c,'pose_route',None)
            if getattr(route,'phase',None) in ('look','return','lean','tilt','complete'):
                cache.update(getattr(route,'last_sent_goals',{}) or {})
            elif m.behavior_trial=='happy':cache.update(getattr(c,'happy_entry_targets',{}))
            context=dict(button_event='button' in events,touch_event='touch' in events,
                         distance_cm=sample.get('distance_cm') if sample.get('distance_cm') is not None else 'N/A',
                         interaction=None if winner is None else winner['kind'],emotion=self.fsm.state,
                         command_cache_raw=json.dumps({str(i):cache.get(i) if cache.get(i) is not None else 'N/A' for i in range(1,6)}),
                         led_state_written=getattr(m,'last_led_behavior',None) or 'N/A',behavior=m.behavior_trial)
            for row in list(self.fsm.events)[-added:]:row.update(context)
    def scan_approach(self,m,now,sample,kind,eligible,add):
        found=getattr(m,'yaw_scan_found',None) or {}
        serial=found.get('serial');stamp=found.get('time_s')
        if type(serial)is int and serial>self.scan_serial:
            self.scan_serial=serial;self.scan_arrival=None
            if type(stamp) in (int,float) and math.isfinite(stamp) and 0<=now-stamp<=.5:
                captured=found.get('captured_s',stamp)
                if type(captured) in (int,float) and math.isfinite(captured) and 0<=stamp-captured<=.5:
                    self.scan_arrival=dict(serial=serial,time_s=stamp,captured_s=captured,frames=[])
        pending=self.scan_arrival
        if pending is None:return
        if (not eligible or self.fsm.state!='normal' or kind!='range'
                or sample['distance_cm']>50. or not 0<=now-pending['time_s']<=.5
                or not current_selected_face(m,now)):
            self.scan_arrival=None;return
        stamp=m.latest_result['observation']['captured_s']
        frames=pending['frames']
        if stamp>=pending['captured_s'] and (not frames or stamp>frames[-1]):frames.append(stamp)
        if len(frames)>=3 and frames[-1]-frames[0]>=.15-1e-9 and getattr(m,'yaw_scan_handoff',None) is None:
            add('approach',pending['time_s'],f"face_scan_{pending['serial']}")
            self.scan_arrival=None

    def discard_inputs(self,m,reason='requested'):
        self.pending_approach=None;self.scan_arrival=None
        found=getattr(m,'yaw_scan_found',None) or {}
        if type(found.get('serial'))is int:self.scan_serial=max(self.scan_serial,found['serial'])
        self.last_input_gate=dict(reason=reason,time_s=m.now())
        if self.touch_burst is not None:self.touch_burst.clear()
        for channel in ('touch','button'):
            discard=getattr(getattr(m,'physical_'+channel,None),'discard_pending',None)
            if callable(discard):discard()
    def dispatch(self,m,target,event):
        c=m.controller;route=getattr(c,'pose_route',None)
        if getattr(m,'behavior_trial',None)=='sleepy' and target!='sleepy':m.wake_serial=getattr(m,'wake_serial',0)+1
        # Sleepy must see a live busy route so its existing interruption
        # handling holds all axes and keeps the actual body references.
        if target=='interested' and route is not None:
            if event=='button' and route.phase in ('look','return','lean','tilt'):
                m.interested_return_reference=dict(route.return_pose)
            route.cancel()
        m.pending_behavior=None;m.fsm_input_kind=event
        if target=='afraid':
            from bio_inspire.runtime.afraid_pose import enter_afraid
            enter_afraid(m);return m.behavior_trial=='afraid'
        if target=='angry':
            from bio_inspire.runtime.angry_behavior import enter_angry
            return enter_angry(m)
        from bio_inspire.runtime.three_state_behavior import handle_state_key
        if target=='happy':m.pending_happy_from_touch=True
        key={'normal':'n','interested':'i','happy':'d','sleepy':'s'}[target]
        handle_state_key(m,ord(key))
        accepted=m.behavior_trial in {'normal':('normal','normal_transition'),
                    'interested':('interested','button_look','interested_transition'),
                    'happy':('happy',),'sleepy':('sleepy','sleepy_transition')}[target]
        if accepted and c.state not in ('FAULT','WAIT_TOF','STOPPED') and getattr(m,'last_led_behavior',None)!=target:
            from bio_inspire.runtime.three_state_behavior import _color
            _color(m,target)
        return accepted
    def save_csv(self,path,m):
        if self.fsm is None:return
        columns=('event_id','source_id','kind','source_s','recognized_s','old_state','new_state','status','dispatch_s',
                 'button_event','touch_event','distance_cm','interaction','emotion','command_cache_raw','led_state_written','behavior')
        tmp=path.with_suffix('.tmp')
        with tmp.open('w',newline='',encoding='utf-8') as out:
            writer=csv.DictWriter(out,fieldnames=columns,extrasaction='ignore');writer.writeheader()
            for row in self.fsm.events:writer.writerow({k:row.get(k,'N/A') for k in columns})
        tmp.replace(path)
