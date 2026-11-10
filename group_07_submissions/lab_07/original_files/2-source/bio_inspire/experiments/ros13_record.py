"""WSL/Jazzy 13-topic observation bridge + independent rosbag2 readback audit.

Reads existing session files, never opens UART/GPIO or subscribes an actuator.
Default is a finalized capture replay, --live follows a growing local mirror.
Source and ROS receipt/bag times remain explicitly separate clock domains.
"""
import argparse, collections, errno, hashlib, json, math, os
from pathlib import Path
import signal, subprocess, time
from .ros13 import TOPICS, Encoder


def dump(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')


def canonical_message(msg):
    # DDS/CDR padding bytes are not semantic data and may be uninitialized.
    # Compare decoded fields, after wire Float32 quantization, not CDR padding.
    from rosidl_runtime_py.convert import message_to_ordereddict
    return json.dumps(message_to_ordereddict(msg),sort_keys=True,separators=(',',':'),
                      default=lambda v:list(v),allow_nan=False).encode('utf8')


def stamp(message,seconds):
    message.sec=math.floor(seconds);message.nanosec=round((seconds-message.sec)*1e9)
    if message.nanosec==1000000000:message.sec+=1;message.nanosec=0


def message_for(packet,classes):
    topic=packet['topic'];data=packet['data'];msg=classes[topic]()
    if topic=='/lamp/joint_states':
        stamp(msg.header.stamp,data['stamp_s']);msg.header.frame_id=data['frame_id']
        for key in ('name','position','velocity','effort'):setattr(msg,key,data[key])
    elif topic=='/lamp/diagnostics':
        from diagnostic_msgs.msg import DiagnosticStatus,KeyValue
        stamp(msg.header.stamp,data['source_s']);msg.header.frame_id='lelamp_source_clock'
        status=DiagnosticStatus();status.name='lelamp/owner_snapshot';status.hardware_id='STS3215_ID1_to_ID5'
        status.level=DiagnosticStatus.ERROR if data['state'] in ('FAULT','WAIT_TOF') else DiagnosticStatus.WARN if data['state']=='STOPPED' else DiagnosticStatus.OK
        status.message=data['state']
        status.values=[KeyValue(key=key,value=json.dumps(value,allow_nan=False)) for key,value in data.items()]
        msg.status=[status]
    elif topic=='/lamp/rgb_command':msg.r,msg.g,msg.b,msg.a=data
    elif TOPICS[topic]=='std_msgs/msg/String':
        msg.data=data if type(data)is str else json.dumps(data,ensure_ascii=False,allow_nan=False,separators=(',',':'))
    else:msg.data=data
    return msg


def rows(session,live,timeout):
    """Retain partial writes; bound line/file/count and wait for final summary."""
    end=time.monotonic()+timeout;count=0;total=0;pending=b'';offset=0
    # Binary chunks retain UTF-8 fragments and an explicit committed offset.
    # WSL/DrvFS can report ENODATA while another process extends the file.
    with (session/'trace.jsonl').open('rb',buffering=0) as stream:
        while True:
            try:
                stream.seek(offset)
                chunk=stream.read(65536)
            except OSError as error:
                if not live or error.errno!=errno.ENODATA:raise
                if time.monotonic()>end:raise TimeoutError('source did not finalize') from error
                time.sleep(.02);continue
            if chunk:
                offset+=len(chunk);total+=len(chunk);pending+=chunk
                if total>128*1024*1024:raise ValueError('source size limit')
                while b'\n' in pending:
                    line,pending=pending.split(b'\n',1)
                    if len(line)+1>65536:raise ValueError('source line limit')
                    count+=1
                    if count>20000:raise ValueError('source row limit')
                    yield json.loads(line)
                if len(pending)>65536:raise ValueError('source line limit')
            elif not live or (session/'summary.json').exists():
                if pending:raise ValueError('partial final source row')
                return
            elif time.monotonic()>end:raise TimeoutError('source did not finalize')
            else:time.sleep(.02)


def verify_bag(bag,expected):
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message
    reader=rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(bag),storage_id='sqlite3'),rosbag2_py.ConverterOptions('',''))
    actual_types={t.name:t.type for t in reader.get_all_topics_and_types()}
    if actual_types!=TOPICS:raise ValueError('bag topic/type contract mismatch')
    counts=collections.Counter();digests={t:hashlib.sha256() for t in TOPICS};times={}
    while reader.has_next():
        topic,data,t=reader.read_next();msg=deserialize_message(data,get_message(TOPICS[topic]))
        counts[topic]+=1;digests[topic].update(canonical_message(msg)+b'\n')
        if topic not in times:times[topic]=[t,t]
        times[topic][1]=t
        if topic=='/lamp/servo_command' and (len(msg.data)!=3 or not all(math.isfinite(v) for v in msg.data)):raise ValueError('bad semantic command')
        if topic=='/lamp/joint_states' and (len(msg.name)!=5 or len(msg.position)!=5 or msg.velocity or msg.effort):raise ValueError('bad measured joints')
        if topic=='/lamp/input/distance' and (not math.isfinite(msg.data) or msg.data<0):raise ValueError('bad meters')
        if topic=='/lamp/rgb_command' and any(not 0<=v<=1 for v in (msg.r,msg.g,msg.b,msg.a)):raise ValueError('bad normalized RGB')
    actual={t:dict(count=counts[t],decoded_fields_sha256=digests[t].hexdigest()) for t in TOPICS}
    if actual!=expected:raise ValueError('bag content/count differs from published ledger')
    missing=[t for t in TOPICS if not counts[t]]
    return dict(all_13_observed=not missing,missing_topics=missing,topics=actual,bag_ros_receipt_ns=times)


def run(session,out,*,live=False,domain=81,pair_id=None,timeout=680.):
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import QoSProfile,ReliabilityPolicy,DurabilityPolicy,HistoryPolicy
    from rclpy.serialization import serialize_message,deserialize_message
    from rosidl_runtime_py.utilities import get_message
    session=Path(session).resolve();out=Path(out).resolve()
    if not (session/'metadata.json').exists():raise ValueError('metadata.json required; legacy raw captures cannot invent 13-topic telemetry')
    metadata=json.loads((session/'metadata.json').read_text(encoding='utf8'))
    if pair_id:metadata['pair_id']=pair_id
    encoder=Encoder(metadata)
    out.mkdir(parents=True,exist_ok=False);dump(out/'source_metadata.json',metadata)
    qos_yaml='\n'.join(t+':\n  history: keep_last\n  depth: 10\n  reliability: reliable\n  durability: volatile' for t in TOPICS)+'\n'
    (out/'qos.yaml').write_text(qos_yaml)
    os.environ['ROS_DOMAIN_ID']=str(domain);rclpy.init();node=Node('lelamp_session_observer')
    qos=QoSProfile(history=HistoryPolicy.KEEP_LAST,depth=10,reliability=ReliabilityPolicy.RELIABLE,durability=DurabilityPolicy.VOLATILE)
    classes={t:get_message(kind) for t,kind in TOPICS.items()}
    pubs={t:node.create_publisher(classes[t],t,qos) for t in TOPICS}
    counts=collections.Counter();digests={t:hashlib.sha256() for t in TOPICS};n=0;bagproc=None
    baglog=(out/'rosbag_record.log').open('w');failure=None;graph={}
    try:
        bagproc=subprocess.Popen(['ros2','bag','record','--disable-keyboard-controls','-s','sqlite3','-o',str(out/'bag'),
                     '--max-bag-duration','700','--max-bag-size',str(128*1024*1024),
                     '--qos-profile-overrides-path',str(out/'qos.yaml'),*TOPICS],stdout=baglog,stderr=subprocess.STDOUT)
        deadline=time.monotonic()+20
        while not all(p.get_subscription_count()>=1 for p in pubs.values()):
            if bagproc.poll() is not None:raise RuntimeError('rosbag recorder exited during discovery')
            if time.monotonic()>deadline:raise TimeoutError('rosbag did not subscribe all 13 topics')
            rclpy.spin_once(node,timeout_sec=.05)
        for t in TOPICS:
            graph[t]=dict(type=TOPICS[t],publishers=[dict(node=e.node_name,reliability=str(e.qos_profile.reliability),
                 durability=str(e.qos_profile.durability),history=str(e.qos_profile.history),depth=e.qos_profile.depth)
                 for e in node.get_publishers_info_by_topic(t)],subscribers=[e.node_name for e in node.get_subscriptions_info_by_topic(t)])
        dump(out/'ros_graph_qos.json',graph)
        with (out/'publisher_ledger.jsonl').open('x',encoding='utf8') as ledger:
            for n,row in enumerate(rows(session,live,timeout),1):
                if bagproc.poll() is not None:raise RuntimeError('recorder stopped before source end')
                packets=encoder.encode(row,n-1)
                for packet in packets:
                    t=packet['topic'];msg=message_for(packet,classes);data=serialize_message(msg)
                    pubs[t].publish(msg);counts[t]+=1
                    digests[t].update(canonical_message(deserialize_message(data,classes[t]))+b'\n')
                ledger.write(json.dumps(dict(index=n-1,source_s=row['time_s'],topics=[p['topic'] for p in packets]),allow_nan=False)+'\n')
                rclpy.spin_once(node,timeout_sec=0.)
                # Bound replay rate to 100 snapshots/s, avoid overflowing DDS queues.
                if not live:time.sleep(.01)
        if not n:raise ValueError('empty source')
        for pub in pubs.values():
            from rclpy.duration import Duration
            if not pub.wait_for_all_acked(Duration(seconds=5)):raise TimeoutError('DDS acknowledgement timeout')
        time.sleep(.3)
    except BaseException as error:failure=error
    finally:
        if bagproc is not None and bagproc.poll() is None:
            bagproc.send_signal(signal.SIGINT)
            try:bagproc.wait(timeout=15)
            except subprocess.TimeoutExpired:bagproc.kill();bagproc.wait();failure=failure or RuntimeError('bag finalize timeout')
        baglog.close();node.destroy_node();rclpy.shutdown()
    expected={t:dict(count=counts[t],decoded_fields_sha256=digests[t].hexdigest()) for t in TOPICS}
    dump(out/'published_counts.json',expected)
    if failure is not None:
        dump(out/'verification.json',dict(status='FAIL',error=str(failure),source_rows=n));raise failure
    if bagproc.returncode not in (0,-signal.SIGINT):raise RuntimeError('rosbag nonzero exit')
    try:result=verify_bag(out/'bag',expected)
    except Exception as error:
        dump(out/'verification.json',dict(status='FAIL',error=str(error),source_rows=n));raise
    summary_path=session/'summary.json'
    summary=json.loads(summary_path.read_text(encoding='utf8')) if summary_path.exists() else {}
    source_hash=hashlib.sha256((session/'trace.jsonl').read_bytes()).hexdigest()
    source_ok=(summary.get('complete') is True and summary.get('written')==n and summary.get('trace_sha256')==source_hash
               and not summary.get('dropped') and not summary.get('error'))
    pair_assigned=metadata['pair_id']!='unassigned'
    result.update(status='PASS' if result['all_13_observed'] and source_ok and pair_assigned else 'INCOMPLETE',source_rows=n,
                  source_complete=source_ok,source_sha256=source_hash,source_metadata=metadata,
                  pair_assigned=pair_assigned,
                  bridge_source_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in (Path(__file__),Path(__file__).with_name('ros13.py'))},
                  transport='live_file_follow' if live else 'recorded_session_replay',physical_actuation_via_ros=False,
                  clock_note='bag clock is WSL ROS receipt; message source clock is retained; not synchronized physical latency')
    dump(out/'verification.json',result)
    dump(out/'manifest.json',{'files':{p.relative_to(out).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                                     for p in out.rglob('*') if p.is_file()}})
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--session',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--pair-id');p.add_argument('--live',action='store_true')
    p.add_argument('--domain',type=int,default=81);a=p.parse_args()
    result=run(a.session,a.out,live=a.live,domain=a.domain,pair_id=a.pair_id)
    print(json.dumps({k:v for k,v in result.items() if k not in ('topics','bag_ros_receipt_ns','source_metadata')},indent=2))
    if result['status']!='PASS':raise SystemExit(2)
