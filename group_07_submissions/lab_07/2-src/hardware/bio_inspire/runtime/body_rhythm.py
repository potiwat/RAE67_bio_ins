"""Supervised body rhythm: retained Lab03/05 SO(2), not a new emotion FSM.

Source: worksheet_review/section4_sources/Week_05_Lab_05__02_Source__course_model.py.txt,
step_cpg. Post-common-10s-warmup state and dt come from the paired phi-only
config beside that source. This trial is fixed-phi C0; no invented AHM mapping.
"""
import math
import random
from functools import lru_cache

@lru_cache(maxsize=4)
def decoder_reference_peak(alpha,phi):
    """Deterministic SO(2) orbit peak for a degree-normalized decoder only."""
    a,b=-.026965330782974153,-.5608626776309884
    c,s=math.cos(phi),math.sin(phi);peak=0.
    for n in range(4096):
        a,b=math.tanh(alpha*(c*a+s*b)),math.tanh(alpha*(-s*a+c*b))
        if n>=512:peak=max(peak,abs(a))
    return peak



def validate_manual_amplitude(value):
    if type(value) not in (int,float) or not math.isfinite(value) or not 1.<=value<=3. or abs(value*10-round(value*10))>1e-7:raise ValueError('CPG size must be 1.0..3.0 in 0.1 steps')
    return float(value)


class ManualAmplitude:
    def __init__(self,initial=2.):
        self.start=self.target=validate_manual_amplitude(initial);self.began=None;self.last_time=None
    def value(self,now):
        if type(now) not in (int,float) or not math.isfinite(now) or (self.last_time is not None and now<self.last_time):raise ValueError('Invalid amplitude clock')
        if self.began is None:self.began=now
        self.last_time=now;t=max(0.,min(1.,(now-self.began)/2.))
        return self.start+(self.target-self.start)*t*t*(3.-2.*t)
    def request(self,value,now):
        value=validate_manual_amplitude(value)
        current=self.value(now)
        if value!=self.target:self.start=current;self.target=value;self.began=now


class SmoothAmplitude:
    """Replayable decoder modulation; no random motor targets or oscillator reset."""
    def __init__(self,seed=0):
        if type(seed)is not int or not 0<=seed<2**32:raise ValueError('Invalid variation seed')
        self.seed=seed;self.rng=random.Random(seed)
        self.origin=None;self.last_time=None;self.segment=0
        self.start=1.;self.target=self.rng.uniform(1.,2.)
    def value(self,now):
        if type(now) not in (int,float) or not math.isfinite(now) or (self.last_time is not None and now<self.last_time):raise ValueError('Invalid modulation clock')
        if self.origin is None:self.origin=now
        elapsed=now-self.origin
        segment=math.floor(elapsed/2.)
        while self.segment<segment:
            self.start=self.target;self.target=self.rng.uniform(1.,2.);self.segment+=1
        fraction=max(0.,min(1.,(elapsed-self.segment*2.)/2.))
        weight=fraction*fraction*(3.-2.*fraction)
        self.last_time=now
        return self.start+(self.target-self.start)*weight

class BodyRhythm:
    dt_s=.05
    alpha=1.1
    phi=.2
    def __init__(self,amplitude_deg=1.,fade_s=2.,phi=.2,time_scale=1.,max_amplitude_deg=3.):
        if fade_s!=2.:raise ValueError('Unreviewed body rhythm trial')
        if type(phi) not in (int,float) or phi not in (.1,.2):raise ValueError('Unreviewed CPG rhythm rate')
        self.phi=phi
        if type(time_scale) not in (int,float) or time_scale not in (.5,.75,1.,3.402/3.8):raise ValueError('Unreviewed breathing time stretch')
        self.time_scale=time_scale;self.logical_elapsed_s=0.
        if max_amplitude_deg not in (3.,4.):raise ValueError("Unreviewed amplitude ceiling")
        self.max_amplitude_deg=max_amplitude_deg
        self.set_amplitude(amplitude_deg)
        self.fade_s=fade_s
        self.o1=-.026965330782974153;self.o2=-.5608626776309884
        self.origin=None;self.last_time=None;self.updates=0;self.envelope=0.
        from bio_inspire.runtime.happy_path import CpgPhaseProgress
        self.phase_tracker=CpgPhaseProgress()
        self.phase_cycles=self.phase_tracker.advance(self.o1,self.o2,0,0.)
    def set_amplitude(self,amplitude_deg):
        if type(amplitude_deg) not in (int,float) or not 1.<=amplitude_deg<=self.max_amplitude_deg:raise ValueError('Unreviewed body rhythm amplitude')
        self.amplitude_ticks=amplitude_deg*4096/360
    def set_normal_ahm_phi(self,phi):
        self.set_ahm_phi(phi)
    def set_ahm_phi(self,phi):
        # Explicit opt-in setter, never broadens constructor/profile defaults.
        if type(phi) not in (int,float) or not math.isfinite(phi) or not .1<=phi<=.13:
            raise ValueError('Hardware-adapted AHM phi must be .10..13')
        self.phi=float(phi)
    def advance(self,now,active,exclusive=False):
        if type(now) not in (int,float) or not math.isfinite(now) or (self.last_time is not None and now<self.last_time):
            raise ValueError('Invalid/nonmonotonic rhythm clock')
        if self.origin is None:self.origin=now;self.last_time=now
        self.logical_elapsed_s+=(now-self.last_time)*self.time_scale
        count=math.floor((self.logical_elapsed_s+1e-9)/self.dt_s)
        c,s=math.cos(self.phi),math.sin(self.phi)
        for update in range(self.updates+1,count+1):
            a,b=self.o1,self.o2
            self.o1=math.tanh(self.alpha*(c*a+s*b))
            self.o2=math.tanh(self.alpha*(-s*a+c*b))
            self.phase_cycles=self.phase_tracker.advance(self.o1,self.o2,update,update*self.dt_s)
        self.updates=count
        self.interpolated_o1=self.o1;self.interpolated_o2=self.o2
        if self.time_scale!=1.:
            fraction=max(0.,min(1.,(self.logical_elapsed_s-count*self.dt_s)/self.dt_s))
            following=math.tanh(self.alpha*(c*self.o1+s*self.o2))
            self.interpolated_o1=self.o1+(following-self.o1)*fraction
            next_o2=math.tanh(self.alpha*(-s*self.o1+c*self.o2))
            self.interpolated_o2=self.o2+(next_o2-self.o2)*fraction
        # Interpolate decoded phase, not the retained course model state.
        angle=math.atan2(-self.o2,self.o1)
        next_a=math.tanh(self.alpha*(c*self.o1+s*self.o2))
        next_b=math.tanh(self.alpha*(-s*self.o1+c*self.o2))
        delta=(math.atan2(-next_b,next_a)-angle+math.pi)%(2*math.pi)-math.pi
        fraction=max(0.,min(1.,(self.logical_elapsed_s-count*self.dt_s)/self.dt_s))
        self.decoder_phase_cycles=self.phase_cycles+max(0.,delta)*fraction/(2*math.pi)
        change=(now-self.last_time)/self.fade_s
        self.envelope=max(0.,min(1.,self.envelope+(change if active else -change)))
        # Protected actions mask output immediately; phase keeps advancing.
        if exclusive:self.envelope=0.
        self.last_time=now
    def offsets(self):
        value=self.amplitude_ticks*self.envelope*getattr(self,'interpolated_o1',self.o1)
        return {2:-value,3:value}
    def status(self):
        report=dict(o1=self.o1,o2=self.o2,alpha=self.alpha,phi=self.phi,
                    dt_s=self.dt_s,model_time_s=self.updates*self.dt_s,
                    time_scale=self.time_scale,wall_model_step_s=self.dt_s/self.time_scale,
                    logical_output_time_s=self.logical_elapsed_s,decoder_output_o1=getattr(self,'interpolated_o1',self.o1),
                    updates=self.updates,envelope=self.envelope,decoder_phase_cycles=getattr(self,"decoder_phase_cycles",self.phase_cycles),
                    amplitude_deg_limit=self.amplitude_ticks*360/4096,
                    command_offsets_deg={i:v*360/4096 for i,v in self.offsets().items() if i in getattr(self,'active_joint_ids',(2,3))},condition='breathing_time_stretch_preview' if self.time_scale!=1. else 'C0_fixed_phi_trial',
                    active_joint_ids=list(getattr(self,'active_joint_ids',(2,3))))
        report.update(getattr(self,'modulation_status',{}))
        return report

class BodyRhythmDriver:
    """Called by the existing UART worker only; never opens a device/thread.

The action route owns all joints while active. Once settled, this layer owns
2/3, visual feedback owns 1/5, and the existing roll timer owns 4.
"""
    def __init__(self,normal_amplitude_deg=1.,normal_amplitude_mode='fixed',variation_seed=0,interested_amplitude_deg=1.,phi=.2,active_joint_ids=(2,3),time_scale=1.,sleepy_amplitude_deg=0.,happy_amplitude_deg=0.,happy_time_scale=.75,happy_body_excursion_deg=None):
        if active_joint_ids not in ((2,),(3,),(2,3)):raise ValueError('Only reviewed body CPG joints allowed')
        self.active_joint_ids=active_joint_ids
        if type(normal_amplitude_deg) not in (int,float) or not 1.<=normal_amplitude_deg<=3.:raise ValueError('Unreviewed Normal rhythm amplitude')
        if normal_amplitude_mode not in ('fixed','smooth_1_2','manual_1_3'):raise ValueError('Unreviewed amplitude modulation')
        self.normal_amplitude_deg=normal_amplitude_deg
        if type(interested_amplitude_deg) not in (int,float) or interested_amplitude_deg not in (1.,1.9):raise ValueError('Unreviewed Interested CPG size')
        self.interested_amplitude_deg=interested_amplitude_deg
        if type(sleepy_amplitude_deg) not in (int,float) or sleepy_amplitude_deg not in (0.,2.):raise ValueError('Unreviewed Sleepy CPG size')
        self.sleepy_amplitude_deg=sleepy_amplitude_deg
        if happy_amplitude_deg not in (0.,2.,4.) or happy_time_scale!=.75:raise ValueError("Unreviewed Happy rhythm")
        if happy_body_excursion_deg not in (None,6.):raise ValueError("Unreviewed Happy body excursion")
        self.happy_body_excursion_deg=happy_body_excursion_deg
        self.happy_amplitude_deg=happy_amplitude_deg;self.happy_time_scale=happy_time_scale;self.base_time_scale=time_scale
        self.variation=SmoothAmplitude(variation_seed) if normal_amplitude_mode=='smooth_1_2' else None
        self.manual=ManualAmplitude(normal_amplitude_deg) if normal_amplitude_mode=='manual_1_3' else None
        self.rhythm=BodyRhythm(phi=phi,time_scale=time_scale,max_amplitude_deg=4. if happy_amplitude_deg==4. else 3.);self.centers=None;self.mode=None;self.last_sent={}
        self.rhythm.active_joint_ids=active_joint_ids
    def request_amplitude(self,value,now):
        if self.manual is None:raise ValueError('Manual CPG adjustment disabled')
        self.manual.request(value,now)
    def pause(self,now):
        self.rhythm.advance(now,False,exclusive=True)
        self.mode=None;self.last_sent={}
    def step(self,motor,now):
        from motion_composer import compose_goals
        def cancelled():
            return (getattr(motor,'operator_stopped',False)
                    or any(event is not None and event.is_set() for event in
                           (getattr(motor,'stopping',None),getattr(motor,'urgent_stop',None))))
        c=motor.controller;route=getattr(c,'pose_route',None)
        mode=getattr(motor,'behavior_trial','normal')
        # Angry uses the approved pose center (Normal-level or legacy lean);
        # emotion identity remains Angry in the owner/FSM and LED output.
        range_angry=mode=='angry' and getattr(motor,'angry_face_approach',False)
        if mode=='angry':mode='interested' if range_angry else 'normal' if getattr(motor,'angry_normal_level',False) else 'interested'
        changed=mode!=self.mode
        roll_row=next((r for r in c.last_rows if r['id']==4),None)
        roll_busy=(mode=='interested' and not range_angry and (getattr(motor,'interested_roll_due',None) is not None
                   or getattr(c,'current_roll_goal',c.normal[4])!=c.normal[4]
                   or (roll_row is not None and (roll_row['speed_raw'] or roll_row['moving_raw'] or abs(roll_row['position_raw']-c.normal[4])>c.normal_tolerances[4]))))
        protected=(c.state not in ('READY','FOLLOWING') or cancelled() or getattr(route,'safety_hold',False)
                   or getattr(motor,'joint_mode',False) or getattr(motor,'head_probe_active',False)
                   or roll_busy
                   or (route is not None and route.phase in ('look','return','lean','tilt')))
        variable_amplitude=self.variation.value(now) if self.variation is not None else None
        if self.manual is not None:
            variable_amplitude=self.manual.value(now)
            self.rhythm.modulation_status=dict(amplitude_mode='manual_1_3' if mode=='normal' else 'fixed',manual_target_deg=self.manual.target,modulation_transition_s=2.)
        if self.variation is not None:
            self.rhythm.modulation_status=dict(amplitude_mode='smooth_1_2' if mode=='normal' else 'fixed',variation_seed=self.variation.seed,
                                              modulation_target_deg=self.variation.target,modulation_transition_s=2.,
                                              modulation_origin_s=self.variation.origin,modulation_segment=self.variation.segment)
        active=not protected and (mode in ('normal','interested') or mode=='sleepy' and self.sleepy_amplitude_deg>0 or mode=='happy' and self.happy_amplitude_deg>0)
        self.rhythm.advance(now,active,exclusive=protected)
        self.rhythm.time_scale=self.happy_time_scale if mode=="happy" else self.base_time_scale
        if protected:
            motor.posture_body_plan=None
            self.mode=None;self.last_sent={};return
        if (mode in ('normal','interested') or mode=='sleepy' and self.sleepy_amplitude_deg>0 or mode=='happy' and self.happy_amplitude_deg>0) and mode!=self.mode:
            old_centers=self.centers
            self.centers=({2:c.normal[2],3:c.normal[3]} if mode=='normal' else
                          (dict(getattr(c,'angry_body_reference',None) or {2:c.normal[2],3:c.normal[3]}) if range_angry else {2:c.normal[2]-102,3:c.normal[3]+102}) if mode=='interested' else
                          dict(getattr(c,'happy_body_reference',None) or self.centers or {2:c.normal[2],3:c.normal[3]}) if mode=='happy' else
                          dict(getattr(c,'sleepy_body_reference',None) or self.centers or getattr(c,'rhythm_base_reference',None) or {2:c.normal[2],3:c.normal[3]}))
            self.rhythm.set_amplitude(self.normal_amplitude_deg if mode=='normal' else self.interested_amplitude_deg if mode=='interested' else self.happy_amplitude_deg if mode=='happy' else self.sleepy_amplitude_deg)
            if old_centers!=self.centers or self.mode is None:self.rhythm.envelope=0.
            self.mode=mode;self.last_sent={}
        if mode=='sleepy' and getattr(c,'sleepy_deep_rest_enabled',False) and self.centers is not None:
            # One writer composes the changing rest center and breathing.
            start=c.sleepy_body_reference
            elapsed=max(0.,now-c.sleepy_contraction_start_s)
            u=min(1.,elapsed/8.);blend=u*u*(3.-2.*u)
            from bio_inspire.runtime.sleepy_trial import sleepy_fold_ticks
            self.centers={2:start[2],3:start[3]+(sleepy_fold_ticks(c) if getattr(c,'sleepy_native_fold_enabled',False) else round(68*blend))}
        if self.centers is None:return
        if mode not in ('normal','interested','sleepy','happy'):return
        if mode=='normal' and variable_amplitude is not None:self.rhythm.set_amplitude(variable_amplitude)
        # Keep a stable feedback envelope across the entire approved modulation.
        limit=3. if self.manual is not None else 2.
        margin=math.ceil((limit*4096/360) if mode=='normal' and variable_amplitude is not None else self.rhythm.amplitude_ticks)
        if mode=='happy' and self.happy_body_excursion_deg is not None:margin=math.ceil(self.happy_body_excursion_deg*4096/360)
        windows={i:(value-(margin if i in self.active_joint_ids else 0)-c.normal_tolerances[i],value+(margin if i in self.active_joint_ids else 0)+c.normal_tolerances[i])
                 for i,value in self.centers.items()}
        if mode=='sleepy' and getattr(c,'sleepy_deep_rest_enabled',False):
            # Reserve the full combined path, including the current feedback,
            # so a moving center cannot outrun the real motor's guard.
            start=c.sleepy_body_reference
            for i in (2,3):
                actual=getattr(c,'sleepy_entry_positions',start).get(i,start[i])
                excursion=sleepy_fold_ticks(c) if getattr(c,'sleepy_native_fold_enabled',False) else 68
                end=start[i]+(excursion if i==3 else 0)
                windows[i]=(min(start[i],end,actual)-margin-c.normal_tolerances[i],
                            max(start[i],end,actual)+margin+c.normal_tolerances[i])
        if changed:
            previous=getattr(c,'behavior_joint_windows',{})
            self.transition_windows={i:(min(windows[i][0],previous.get(i,windows[i])[0]),max(windows[i][1],previous.get(i,windows[i])[1])) for i in windows}
            self.transition_counts={i:0 for i in windows}
        for i,bounds in list(getattr(self,'transition_windows',{}).items()):
            row=next((r for r in c.last_rows if r['id']==i),None)
            inside=row is not None and windows[i][0]<=row['position_raw']<=windows[i][1]
            self.transition_counts[i]=self.transition_counts[i]+1 if inside else 0
            if self.transition_counts[i]>=3:del self.transition_windows[i]
            else:windows[i]=(min(windows[i][0],bounds[0]),max(windows[i][1],bounds[1]))
        c.behavior_joint_windows={**getattr(c,'behavior_joint_windows',{}),**windows}
        c.behavior_joint_allowances={**getattr(c,'behavior_joint_allowances',{}),2:0,3:0}
        c.bus.windows.update(windows)
        c.rhythm_base_reference=dict(self.centers)
        # Cached references, not extra UART reads or measured-pose rebasing.
        base={**c.normal,**self.centers,1:getattr(c,'last_goal',None) or c.normal[1],
              5:getattr(c,'last_pitch_goal',None) or c.normal[5],
              4:getattr(c,'current_roll_goal',c.normal[4])}
        offsets={i:v for i,v in self.rhythm.offsets().items() if i in self.active_joint_ids}
        if range_angry:
            # Smooth one-sided breathing: retreat then return, never advance past the stop pose.
            reserve=self.rhythm.amplitude_ticks*self.rhythm.envelope
            value=max(0.,min(reserve,(offsets.get(2,0.)+reserve)/2))
            offsets={i:v for i,v in {2:value,3:-value}.items() if i in self.active_joint_ids}
        if mode=='sleepy' and getattr(c,'sleepy_native_fold_enabled',False):
            from bio_inspire.runtime.sleepy_trial import sleepy_native_fold_weight
            weight=sleepy_native_fold_weight(c,now,cancelled)
            if 3 in offsets:offsets[3]*=weight
        if mode=='happy' and self.happy_body_excursion_deg is not None:
            peak=decoder_reference_peak(self.rhythm.alpha,self.rhythm.phi)
            unit=max(-1.,min(1.,getattr(self.rhythm,'interpolated_o1',self.rhythm.o1)/peak))
            value=self.happy_body_excursion_deg*4096/360*self.rhythm.envelope*unit
            offsets={i:v for i,v in {2:-value,3:value}.items() if i in self.active_joint_ids}
            self.rhythm.modulation_status={**getattr(self.rhythm,'modulation_status',{}),
                'happy_body_excursion_deg':self.happy_body_excursion_deg,
                'happy_decoder_reference_peak':peak,
                'decoded_body_offsets_deg':{i:v*360/4096 for i,v in offsets.items()}}
        goals=compose_goals(base,c.bus.windows,cpg=offsets,cpg_enabled=True,state=c.state)
        if goals is not None:motor.posture_body_plan=dict(mode=getattr(motor,'behavior_trial','normal'),time_s=now,goals={i:goals[i] for i in (2,3)})
        from coordinated_positions import write_positions
        outgoing={i:goals[i] for i in self.active_joint_ids if self.last_sent.get(i)!=goals[i]}
        if outgoing:
            if write_positions(c.bus,outgoing,cancelled,source='cpg_'+getattr(motor,'behavior_trial','normal')) is None:return
            self.last_sent.update(outgoing)

        if mode=='happy' and getattr(motor,'happy_yaw_enabled',False):
            base=getattr(motor,'happy_yaw_base',None)
            if base is not None:
                offset=self.rhythm.amplitude_ticks*self.rhythm.envelope*getattr(self.rhythm,"interpolated_o2",self.rhythm.o2)
                margin=c.command_margin_ticks
                reserve=math.ceil(self.rhythm.amplitude_ticks)
                low,high=c.yaw_window[0]+margin,c.yaw_window[1]-margin
                center=max(low+reserve,min(high-reserve,base))
                goal=round(max(low,min(high,center+offset)))
                if not motor.stopping.is_set() and not motor.urgent_stop.is_set():c.goal_yaw(goal)
                self.rhythm.modulation_status={**getattr(self.rhythm,"modulation_status",{})}
                self.rhythm.modulation_status.update(happy_yaw_offset_ticks=offset,happy_yaw_base=base,happy_yaw_reserved_center=center)
