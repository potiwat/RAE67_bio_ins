"""Actual Pi input recording -> causal grid -> ROS2 replay diagnostic.

No actuator output is published. ROS imports are delayed to the role entry point.
"""
from dataclasses import asdict
import json
import math
from pathlib import Path
import time

from . import ahm_cpg_compare as model
from .ahm_input_bridge import InputAdapter,InputFrame,EmotionAdapter


def resample_capture(rows):
    if not rows:raise ValueError('empty recording')
    if any(not math.isfinite(r['time_s']) for r in rows):raise ValueError('nonfinite capture clock')
    if any(b['time_s']<=a['time_s'] for a,b in zip(rows,rows[1:])):raise ValueError('capture clock must increase')
    origin=min(rows[0][key] for key in ('time_s','button_sample_s','touch_sample_s','distance_sample_s'))
    end=rows[-1]['time_s']-origin
    count=math.floor((end+1e-9)/model.DT)+1
    if not 1<=count<=12000:raise ValueError('recording outside1..12000modelintervals')
    frames=[];index=-1
    for k in range(count):
        t=k*model.DT
        while index+1<len(rows) and rows[index+1]['time_s']-origin<=t+1e-9:index+=1
        if index<0:
            frames.append(InputFrame(t,t,False,False,'error',None,'awaiting_first_sample'))
        else:
            r=rows[index]
            frames.append(InputFrame(t,r['time_s']-origin,r['button'],r['touch'],r['distance_kind'],r['distance_m'],r['source_id'],
                                     r['button_sample_s']-origin,r['touch_sample_s']-origin,r['distance_sample_s']-origin))
    return frames


class CPGPair:
    def __init__(self):
        a,b=model.warmup()
        self.states={'C0':(a,b,None),'C1':(a,b,0.)};self.k=0
        self.course=model.course_model();self.contract=model.contract()

    def step(self,value):
        valid=type(value) in (int,float) and math.isfinite(value) and 0<=value<=1
        result={}
        for condition,(a,b,h) in self.states.items():
            r=(h if condition=='C1' else float(value)) if valid else 0.
            phi=self.course['mapped_parameters'](r,self.contract,'phi-only')['phi_rad']
            an,bn=self.course['step_cpg'](a,b,model.ALPHA,phi)
            hn=self.course['hormone_step'](h,float(value) if valid else math.nan,model.DT,model.RATES)['h'] if condition=='C1' else None
            result[condition]=dict(t_s=self.k*model.DT,t_next_s=(self.k+1)*model.DT,condition=condition,
                                   stimulus=float(value) if valid else None,fault=int(not valid),h=h,r_used=r,phi_rad_per_update=phi,
                                   alpha=model.ALPHA,o1=a,o2=b,h_next=hn,o1_next=an,o2_next=bn)
            self.states[condition]=(an,bn,hn)
        self.k+=1
        return result


def capture_frames(rows):
    """One recorded acquisition per model update; retain source clock separately.

    Re-gridding a nearly20Hz recording can hold an extra sample and manufacture
    stale ToF ages. This diagnostic preserves each acquisition exactly once.
    CPG model time is still k*.05, not a claim of exact physical update timing.
    """
    if not 1<=len(rows)<=12000:raise ValueError('1..12000 snapshots required')
    keys=('time_s','button_sample_s','touch_sample_s','distance_sample_s')
    if any(type(r.get(k)) not in (int,float) or not math.isfinite(r[k]) for r in rows for k in keys):
        raise ValueError('finite source clocks required')
    if any(b['time_s']<=a['time_s'] for a,b in zip(rows,rows[1:])):raise ValueError('capture clock must increase')
    origin=min(rows[0][k] for k in keys)
    return [InputFrame(r['time_s']-origin,r['time_s']-origin,r['button'],r['touch'],r['distance_kind'],r['distance_m'],r['source_id'],
                       r['button_sample_s']-origin,r['touch_sample_s']-origin,r['distance_sample_s']-origin,
                       r.get('digital_predebounced',False),
                       tuple(t-origin for t in r.get('button_events',())),tuple(t-origin for t in r.get('touch_events',()))) for r in rows]


class SequenceGuard:
    def __init__(self):self.count=0
    def accept(self,packet):
        if packet.get('end'):
            if type(packet.get('count')) is not int or packet['count']!=self.count:
                raise ValueError('ROS end count does not match contiguous received sequence')
        else:
            if type(packet.get('index')) is not int or packet['index']!=self.count:
                raise ValueError('missing, duplicated or reordered ROS snapshot')
            self.count+=1


def run_role(role,source,out,domain,fast=False):
    import os
    os.environ['ROS_DOMAIN_ID']=str(domain)
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import QoSProfile,ReliabilityPolicy,DurabilityPolicy,HistoryPolicy
    from std_msgs.msg import Bool,Float32,String
    qos=QoSProfile(history=HistoryPolicy.KEEP_LAST,depth=10,reliability=ReliabilityPolicy.RELIABLE,durability=DurabilityPolicy.VOLATILE)
    rclpy.init()
    node=Node('lamp_ahm_'+role)
    stream=Path(out).open('x',encoding='utf-8')
    done=False;adapter=InputAdapter();emotion=EmotionAdapter();pair=CPGPair();received=[];guard=SequenceGuard()
    def log(record):stream.write(json.dumps(record,allow_nan=False)+'\n');stream.flush()
    def controller(msg):
        nonlocal done
        packet=json.loads(msg.data)
        guard.accept(packet)
        if packet.get('end'):
            output=String();output.data=json.dumps(dict(end=True,count=len(received)))
            diag_pub.publish(output);log(dict(end=True,count=len(received)));done=True;return
        f=InputFrame(**packet['frame'])
        sample=emotion.step(adapter.step(f));cp=pair.step(sample['stimulus'])
        record=dict(index=packet['index'],frame=packet['frame'],sample=sample,cpg=cp,
                    stimulus_policy=adapter.stimulus_policy,
                    received_host_monotonic_s=time.monotonic(),physical_output=False)
        received.append(packet['index'])
        output=String();output.data=json.dumps(record,allow_nan=False);diag_pub.publish(output)
        state_pub.publish(String(data=sample['emotion']))
        if sample['interaction']:event_pub.publish(String(data=sample['interaction']))
        log(record)
    def collector(msg):
        nonlocal done
        packet=json.loads(msg.data);log(packet)
        guard.accept(packet)
        if packet.get('end'):done=True
    if role=='controller':
        diag_pub=node.create_publisher(String,'/lamp/ahm_cpg/diagnostic',qos)
        state_pub=node.create_publisher(String,'/lamp/emotion',qos)
        event_pub=node.create_publisher(String,'/lamp/interaction',qos)
        ready_pub=node.create_publisher(String,'/lamp/ahm_cpg/ready',qos)
        node.create_timer(.1,lambda:ready_pub.publish(String(data='collector_discovered')) if diag_pub.get_subscription_count()>=1 else None)
        node.create_subscription(String,'/lamp/input/status',controller,qos)
    elif role=='collector':
        node.create_subscription(String,'/lamp/ahm_cpg/diagnostic',collector,qos)
    elif role=='publisher':
        pub=node.create_publisher(String,'/lamp/input/status',qos)
        bpub=node.create_publisher(Bool,'/lamp/input/button',qos)
        tpub=node.create_publisher(Bool,'/lamp/input/touch',qos)
        dpub=node.create_publisher(Float32,'/lamp/input/distance',qos)
        readiness=[]
        node.create_subscription(String,'/lamp/ahm_cpg/ready',lambda msg:readiness.append(msg.data) if msg.data=='collector_discovered' else None,qos)
        frames=capture_frames([json.loads(line) for line in Path(source).read_text().splitlines() if line])
        deadline=time.monotonic()+5
        while (pub.get_subscription_count()<1 or not readiness) and time.monotonic()<deadline:rclpy.spin_once(node,timeout_sec=.05)
        if pub.get_subscription_count()<1 or not readiness:raise RuntimeError('complete ROS receiver chain not discovered')
        began=time.monotonic()
        for k,frame in enumerate(frames):
            packet=dict(index=k,frame=asdict(frame));log(packet)
            pub.publish(String(data=json.dumps(packet,allow_nan=False)))
            bpub.publish(Bool(data=frame.button));tpub.publish(Bool(data=frame.touch))
            if frame.distance_kind=='range' and frame.distance_m is not None:dpub.publish(Float32(data=float(frame.distance_m)))
            rclpy.spin_once(node,timeout_sec=0.)
            next_offset=frames[k+1].time_s-frames[0].time_s if k+1<len(frames) else frame.time_s-frames[0].time_s+model.DT
            time.sleep(.01 if fast else max(0.,began+next_offset-time.monotonic()))
        pub.publish(String(data=json.dumps(dict(end=True,count=len(frames)))));time.sleep(1.);done=True
    else:raise ValueError('unknown role')
    end=time.monotonic()+90
    try:
        while not done and time.monotonic()<end:rclpy.spin_once(node,timeout_sec=.1)
        if not done:raise TimeoutError('bounded ROS run timed out')
        time.sleep(.3)
    finally:
        stream.close();node.destroy_node();rclpy.shutdown()


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--role',choices=('publisher','controller','collector'),required=True)
    p.add_argument('--source',type=Path)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--domain',type=int,default=73)
    p.add_argument('--fast',action='store_true')
    a=p.parse_args();run_role(a.role,a.source,a.out,a.domain,a.fast)
