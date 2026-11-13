"""Independent readback of the three CSVs and the seven-topic SQLite ROS bag."""
import argparse
import collections
import csv
import hashlib
import json
import math
from pathlib import Path
import sqlite3

from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message

args=argparse.ArgumentParser();args.add_argument("folder",type=Path)
args.add_argument("--output",type=Path,help="directory for regenerated summaries; defaults to the input folder")
options=args.parse_args()
folder=options.folder.resolve()
destination=options.output.resolve() if options.output else folder
destination.mkdir(parents=True,exist_ok=True)
def load(name):
    return json.loads((folder/name).read_bytes())
def write(name,value):
    (destination/name).write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
meta=load("session.json");graph=load("observed_graph.json")
discovered=graph["topic_types"]
assert all(len(types)==1 for types in discovered.values())
topics={name:types[0] for name,types in discovered.items()}
edges=graph["observed_endpoints"]
roles=["inputs","interaction","collector"]
counts={r:collections.Counter() for r in roles}
ranges={}
states=collections.Counter()
phase_ticks=[]
virtual=[]
layout=set()
rgb_bounds=[1.,0.]
node_name={"inputs":"week07_inputs","interaction":"week07_interaction","collector":"week07_output_collector"}
for role in roles:
    with (folder/(role+".csv")).open(encoding="utf-8",newline="") as f:
        prevtime=0
        for idx,r in enumerate(csv.DictReader(f),1):
            ts=int(r["monotonic_ns"]);key=(r["topic"],r["phase"])
            assert r["node"]==node_name[role] and ts>=prevtime and not r["source_latency_s"]
            prevtime=ts
            counts[role][key]+=1;assert int(r["local_sequence"])==counts[role][key]
            ranges.setdefault(role,[]).append(ts)
            payload=json.loads(r["payload"])
            if role=="inputs" and r["topic"]=="/lamp/input/button":
                virtual.append(payload["virtual_sample_s"])
            if role=="collector" and r["topic"]=="/lamp/emotion":
                states[payload["data"]]+=1
            if role=="interaction" and r["phase"]=="publish" and r["topic"]=="/lamp/interaction":
                phase_ticks.append(int(r["duration_ns"]))
assert len(virtual)==1101 and min(virtual)==0 and max(virtual)==22
dbfile=next((folder/"bag").glob("*.db3"))
bagcounts=collections.Counter();examples={}
def msg_value(name,msg):
    if name.endswith("/servo_command"):
        sizes=tuple((d.label,d.size,d.stride) for d in msg.layout.dim)
        layout.add((sizes,msg.layout.data_offset))
        assert len(msg.data)==3 and all(math.isfinite(v) for v in msg.data)
        return {"data":list(msg.data),"layout":[dict(label=d.label,size=d.size,stride=d.stride) for d in msg.layout.dim],
                "data_offset":msg.layout.data_offset}
    if name.endswith("/rgb_command"):
        vals=[msg.r,msg.g,msg.b,msg.a]
        assert all(0<=v<=1 for v in vals) and msg.a==1.
        rgb_bounds[0]=min(rgb_bounds[0],*vals[:3]);rgb_bounds[1]=max(rgb_bounds[1],*vals[:3])
        return dict(r=msg.r,g=msg.g,b=msg.b,a=msg.a)
    return {"data":"NaN" if isinstance(msg.data,float) and not math.isfinite(msg.data) else msg.data}
with sqlite3.connect(f"file:{dbfile}?mode=ro",uri=True) as db:
    assert db.execute("pragma integrity_check").fetchone()[0]=="ok"
    typetable={id:(name,typ,get_message(typ)) for id,name,typ in db.execute("select id,name,type from topics")}
    assert {name:typ for name,typ,_ in typetable.values()}==topics
    for tid,t,blob in db.execute("select topic_id,timestamp,data from messages order by id"):
        name,typ,cls=typetable[tid];bagcounts[name]+=1
        message=deserialize_message(blob,cls)
        payload=msg_value(name,message)
        examples.setdefault(name,dict(first_bag_system_time_ns=t,message_type=typ,payload=payload))
assert len(layout)==1 and next(iter(layout))==((("tilt_extend_nod_rad",3,3),),0)
assert dict(bagcounts)==meta["topic_messages_in_bag"]
rows=[]
for topic,typ in sorted(topics.items()):
    source="inputs" if topic.startswith("/lamp/input/") else "interaction"
    sink="interaction" if source=="inputs" else "collector"
    pub=counts[source][(topic,"publish")];rec=counts[sink][(topic,"receive")]
    rows.append(dict(topic=topic,message_type=typ,publisher=node_name[source],subscriber=node_name[sink],
         published_in_role_trace=pub,received_in_role_trace=rec,messages_in_bag=bagcounts[topic]))
    assert pub>0 and rec>0
    observed_pub=[e for e in edges if e["topic"]==topic and e["endpoint"]=="publisher"]
    observed_sub=[e for e in edges if e["topic"]==topic and e["endpoint"]=="subscription"]
    assert {e["node"] for e in observed_pub}=={node_name[source]}
    assert {e["node"] for e in observed_sub}=={node_name[sink],"rosbag2_recorder"}
with (destination/"message_counts.csv").open("w",encoding="utf-8",newline="") as f:
    wr=csv.DictWriter(f,fieldnames=rows[0]);wr.writeheader();wr.writerows(rows)
event={e["event"]:e["monotonic_ns"] for e in meta["events"]}
first_input=ranges["inputs"][0]
assert event["all_seven_recorder_subscriptions_ready_before_source"] < first_input < event["official_source_completed"]
result=dict(
    trace_rows={k:len(v) for k,v in ranges.items()},
    trace_spans_s={k:(v[-1]-v[0])/1e9 for k,v in ranges.items()},
    source_virtual_frames=len(virtual),source_virtual_span_s=[min(virtual),max(virtual)],
    recorder_ready_to_first_source_publish_ms=(first_input-event["all_seven_recorder_subscriptions_ready_before_source"])/1e6,
    interaction_output_ticks=len(phase_ticks),emotion_messages_in_collector=dict(states),
    sqlite_integrity="ok",bag_total_messages=sum(bagcounts.values()),bag_topic_count=len(bagcounts),
    bag_sha256=digest(dbfile),application_roles=list(node_name.values()),
    observed_application_endpoints=sum(e["node"] in node_name.values() for e in edges),
    observed_recorder_subscriptions=sum(e["node"]=="rosbag2_recorder" for e in edges),
    observed_reliability=sorted({e["reliability"] for e in edges}),observed_durability=sorted({e["durability"] for e in edges}),
    observed_history=sorted({e["history"] for e in edges}),observed_depth=sorted({e["depth"] for e in edges}),
    verified_all_cdr_messages=True,servo_layout={"label":"tilt_extend_nod_rad","size":3,"stride":3,"offset":0},
    observed_rgb_range=rgb_bounds,source_to_physical_latency_s=None
)
write("verification.json",result);write("message_samples.json",examples);print(json.dumps(result,indent=2))
