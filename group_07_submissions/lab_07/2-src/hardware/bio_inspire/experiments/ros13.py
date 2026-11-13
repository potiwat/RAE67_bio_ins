"""Telemetry-only contract. No ROS/hardware imports or actuator subscribers.

The operator approved [ID4, ID2, ID5] command offsets for the three semantic
angles on 2026-11-05. This projection is not FK/IK or a reversible motor driver.
"""
import math

TOPICS={
 '/lamp/input/button':'std_msgs/msg/Bool',
 '/lamp/input/touch':'std_msgs/msg/Bool',
 '/lamp/input/distance':'std_msgs/msg/Float32',
 '/lamp/interaction':'std_msgs/msg/String',
 '/lamp/emotion':'std_msgs/msg/String',
 '/lamp/servo_command':'std_msgs/msg/Float32MultiArray',
 '/lamp/rgb_command':'std_msgs/msg/ColorRGBA',
 '/lamp/input/status':'std_msgs/msg/String',
 '/lamp/ahm_cpg/diagnostic':'std_msgs/msg/String',
 '/lamp/joint_states':'sensor_msgs/msg/JointState',
 '/lamp/perception/face':'std_msgs/msg/String',
 '/lamp/diagnostics':'diagnostic_msgs/msg/DiagnosticArray',
 '/lamp/trace':'std_msgs/msg/String',
}
NAMES=['base_yaw','base_pitch','elbow_pitch','wrist_roll','wrist_pitch']
COLORS={'normal':[255,255,255],'interested':[255,100,0],'happy':[255,180,40],
        'sleepy':[40,100,255],'afraid':[180,60,255],'angry':[255,0,0]}
RAD_PER_TICK=2*math.pi/4096


def finite(value):
    if type(value) not in (int,float) or not math.isfinite(value):raise ValueError('finite numeric value required')
    return value


class DigitalContinuity:
    """Audit losses within capture, not cumulative counters from earlier play."""
    def __init__(self):self.previous={}
    def check(self,digital):
        for channel,view in digital.items():
            if view.get('sampler_error'):raise ValueError('digital_sampler_error:'+channel)
            if view.get('raw_history_may_be_truncated'):raise ValueError('raw_edge_history_lost:'+channel)
            overflow=view.get('overflow_presses',0);seq=view.get('stable_sequence')
            if type(overflow)is not int or overflow<0:raise ValueError('invalid_overflow_counter:'+channel)
            previous=self.previous.get(channel)
            if previous is not None:
                if overflow!=previous[0]:raise ValueError('digital_overflow_or_counter_reset:'+channel)
                if seq is not None and previous[1] is not None:
                    if type(seq)is not int or seq-previous[1]!=len(view.get('stable_edges',[])):
                        raise ValueError('stable_edge_sequence_lost:'+channel)
            self.previous[channel]=(overflow,seq)


class Encoder:
    def __init__(self,metadata):
        self.meta=metadata;self.next_index=0;self.last_s=None;self.event_ids=set();self.digital_audit=DigitalContinuity()
        self.normal={int(k):v for k,v in metadata['profile']['normal_raw'].items()}
        if set(self.normal)!=set(range(1,6)):raise ValueError('five Normal references required')
        for value in self.normal.values():finite(value)
        for name in ('run_id','pair_id','condition','origin','clock'):
            if not metadata.get(name):raise ValueError('metadata missing '+name)
        if metadata['condition'] not in ('C0','C1'):raise ValueError('condition must be C0/C1')

    def encode(self,row,index):
        if index!=self.next_index:raise ValueError('noncontiguous source sequence')
        stamp=finite(row['time_s'])
        if stamp<0 or self.last_s is not None and stamp<self.last_s:raise ValueError('source clock regression')
        ros=row.get('ros',{})
        if ros.get('schema_version')!=1 or ros.get('event_history_lost'):raise ValueError('missing schema or lost FSM history')
        rows=row['rows'];feedback={r['id']:r for r in rows}
        if len(rows)!=5 or set(feedback)!=set(range(1,6)):raise ValueError('complete five-joint feedback required')
        for r in rows:
            for key in ('position_raw','goal_raw'):
                value=finite(r[key])
                if not 0<=value<=4095:raise ValueError('encoder/goal outside STS single-turn range')
        common=dict(schema_version=1,run_id=self.meta['run_id'],pair_id=self.meta['pair_id'],
                    condition=self.meta['condition'],origin=self.meta['origin'],index=index,
                    source_id=self.meta['run_id']+':'+str(index),source_s=stamp,clock=self.meta['clock'])
        out=[]
        def add(topic,data):out.append(dict(topic=topic,type=TOPICS[topic],data=data))
        digital=row['digital_inputs']
        self.digital_audit.check(digital)
        experimental=row.get('experimental_inputs')
        if experimental is not None:
            if experimental.get('source')!='scripted_experimental_inputs':raise ValueError('unknown input origin')
            common['input_origin']='scripted_experimental_inputs'
        for channel in ('button','touch'):
            value=experimental[channel] if experimental is not None else digital[channel]['stable_pressed']
            if type(value) is not bool:raise ValueError('stable Boolean input required')
            add('/lamp/input/'+channel,value)
        distance=row.get('distance') or {}
        if distance.get('measurement_state')=='range' and distance.get('distance_cm') is not None:
            value=finite(distance['distance_cm'])/100.
            if value<0:raise ValueError('negative distance')
            add('/lamp/input/distance',value)
        add('/lamp/input/status',{**common,'digital':digital,'distance':distance,'experimental_inputs':experimental,
                                   'stale_policy':'inspect source sample times; no_target is not distance zero'})
        events=ros.get('events',[])
        for event in events:
            eid=event['event_id']
            if eid in self.event_ids:continue
            # Every recognized candidate is retained, including held/discarded ones.
            # Only the event-name topic is minimal; IDs and status stay in trace.
            add('/lamp/interaction',event['kind']);self.event_ids.add(eid)
        if len(self.event_ids)>20000:raise ValueError('event capacity exceeded')
        state=(row.get('fsm') or {}).get('state',row.get('behavior'))
        if state not in COLORS:raise ValueError('unknown emotion')
        add('/lamp/emotion',state)
        add('/lamp/servo_command',[(feedback[i]['goal_raw']-self.normal[i])*RAD_PER_TICK for i in (4,2,5)])
        rgb=ros.get('led_rgb_255')
        if not isinstance(rgb,list) or len(rgb)!=3 or any(type(v)is not int or not 0<=v<=255 for v in rgb):
            raise ValueError('observed LED command required; no inferred state color')
        add('/lamp/rgb_command',[v/255. for v in rgb]+[1.])
        add('/lamp/ahm_cpg/diagnostic',{**common,'oscillator':row.get('oscillator'),
                  'breathing_rhythm':row.get('breathing_rhythm'),'behavior':row.get('behavior'),
                  'pose_phase':row.get('pose_phase'),'crouch_progress':row.get('crouch_progress')})
        # Header is the owner snapshot's source clock. Per-joint driver sample
        # times use CLOCK_MONOTONIC, not BOOTTIME; retain those in diagnostics.
        # Never silently treat those two clocks as synchronized physical onset.
        add('/lamp/joint_states',dict(stamp_s=stamp,frame_id='lelamp_normal_encoder_offsets',
                 name=NAMES,position=[(feedback[i]['position_raw']-self.normal[i])*RAD_PER_TICK for i in range(1,6)],
                 velocity=[],effort=[]))
        add('/lamp/perception/face',{**common,'observation':row.get('image_observation'),
                   'yaw_acquisition_scan':row.get('yaw_acquisition_scan'),
                   'units':'normalized image coordinates; captured_s uses source clock'})
        add('/lamp/diagnostics',{**common,'state':row['state'],'error':row.get('error'),
                   'rows':rows,'digital':digital,'distance':distance,'brightness':ros.get('brightness'),
                   'feedback_ms':row.get('feedback_ms'),'event_history_lost':False,
                   'feedback_sample_clock':'sampled_monotonic_s = Pi CLOCK_MONOTONIC; header = owner source clock'})
        add('/lamp/trace',{**common,'events':events,'fsm':row.get('fsm'),'pose_phase':row.get('pose_phase'),
             'experimental_inputs':experimental,
             'joint_goals_raw':{str(i):feedback[i]['goal_raw'] for i in range(1,6)},
             'semantic_mapping':{'tilt':4,'extend':2,'nod':5,'unit':'rad relative Normal'},
             'stage':'cached_command_and_feedback_snapshot_not_physical_onset',
             'led_behavior':ros.get('led_behavior'),'coordinated_pose':row.get('coordinated_pose')})
        self.next_index+=1;self.last_s=stamp
        return out
