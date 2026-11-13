"""Observe the three Week 07 roles with the documented Jazzy CSV compatibility fix."""
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import signal
import sqlite3
import subprocess
import sys
import time

import rclpy
from rclpy.utilities import get_rmw_implementation_identifier

workspace=Path(sys.argv[1]).resolve()
out=workspace/"session"
contract=json.loads((workspace/"src/lamp_week07/interface_contract.json").read_bytes())
topics={x["name"]:x["type"] for x in contract["topics"]}
inputs=[name for name in topics if name.startswith("/lamp/input/")]
role={"input":"week07_inputs","interaction":"week07_interaction","collector":"week07_output_collector",
      "recorder":"rosbag2_recorder","observer":"week07_graph_observer"}
clock=time.perf_counter_ns
def utc():return datetime.now(timezone.utc).isoformat()
def dump(name,data):
    (out/name).write_text(json.dumps(data,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def writecsv(name,rows):
    with (out/name).open("w",encoding="utf-8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
def name_of(policy):return getattr(policy,"name",str(policy))
events=[]
children={}
files={}
def event(name,**kwargs):
    events.append(dict(event=name,monotonic_ns=clock(),utc=utc(),**kwargs))
    print(name,kwargs,flush=True)
def launch(name,command):
    files[name]=(workspace/(name+".console.log")).open("wb")
    children[name]=subprocess.Popen(command,cwd=workspace,stdout=files[name],stderr=subprocess.STDOUT,start_new_session=True)
    event("launched_"+name,pid=children[name].pid)
def stop(name):
    proc=children.get(name)
    if proc is None:return
    if proc.poll() is None:
        os.killpg(proc.pid,signal.SIGINT)
        try:proc.wait(timeout=9)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=4)
    files[name].close();event("stopped_"+name,returncode=proc.returncode)
    children.pop(name)
def wait_for(label,check,seconds=12):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        for key,proc in children.items():
            if proc.poll() is not None:
                raise RuntimeError(key+" exited early: "+(workspace/(key+".console.log")).read_text()[-2000:])
        rclpy.spin_once(obs,timeout_sec=.045)
        if check():
            event(label);return
        time.sleep(.02)
    print("Observed topics just before timeout:",obs.get_topic_names_and_types(),flush=True)
    print("Observed subscriptions", {name:[x.node_name for x in obs.get_subscriptions_info_by_topic(name)] for name in topics},flush=True)
    raise TimeoutError(label)
def subscriber(name,topic):return name in {e.node_name for e in obs.get_subscriptions_info_by_topic(topic)}
def publisher(name,topic):return name in {e.node_name for e in obs.get_publishers_info_by_topic(topic)}
def all_ready_without_input():
    return all(subscriber(role["recorder"],topic) and
               (subscriber(role["interaction"],topic) if topic in inputs else
                publisher(role["interaction"],topic) and subscriber(role["collector"],topic)) for topic in topics)
def snapshot():
    graph_time=clock()
    types=dict(obs.get_topic_names_and_types())
    endpoint_rows=[]
    for name,expected in topics.items():
        assert [expected]==types[name],(name,types[name])
        for direction,lookup in (("publisher",obs.get_publishers_info_by_topic),("subscription",obs.get_subscriptions_info_by_topic)):
            for endpoint in lookup(name):
                q=endpoint.qos_profile
                endpoint_rows.append(dict(topic=name,message_type=endpoint.topic_type,endpoint=direction,
                    node=endpoint.node_name,namespace=endpoint.node_namespace,reliability=name_of(q.reliability),
                    durability=name_of(q.durability),history=name_of(q.history),depth=q.depth,
                    liveliness=name_of(q.liveliness),gid=bytes(endpoint.endpoint_gid).hex()))
    endpoint_rows.sort(key=lambda x:(x["topic"],x["endpoint"],x["node"]))
    writecsv("observed_endpoints.csv",endpoint_rows)
    nodes=[dict(name=n,namespace=ns) for n,ns in sorted(obs.get_node_names_and_namespaces())]
    dump("observed_graph.json",dict(monotonic_ns=graph_time,utc=utc(),nodes=nodes,
                                     topic_types={k:types[k] for k in topics},observed_endpoints=endpoint_rows))
    event("live_graph_captured",endpoints=len(endpoint_rows),nodes=nodes)
def executable(name):return str(workspace/"install/lamp_week07/lib/lamp_week07"/name)
def traceopt(name):return ["--ros-args","-p","trace_file:="+str(out/name)]

rclpy.init()
obs=rclpy.create_node(role["observer"],enable_rosout=False,start_parameter_services=False)
started=utc()
try:
    for _ in range(14): rclpy.spin_once(obs,timeout_sec=.06)
    yes=[n for n in dict(obs.get_topic_names_and_types()) if n.startswith("/lamp/")]
    if yes or set(obs.get_node_names())&set(role.values())-{role["observer"]}:
        raise RuntimeError("Selected domain already contains a course session")
    event("isolated_graph_checked",domain=os.environ["ROS_DOMAIN_ID"],rmw=get_rmw_implementation_identifier())
    qos_yaml="".join(f"{t}:\n  reliability: reliable\n  durability: volatile\n  history: keep_last\n  depth: 10\n" for t in topics)
    (out/"recorder_qos.yaml").write_text(qos_yaml)
    launch("collector",[executable("output_collector"),*traceopt("collector.csv")])
    wait_for("collector_subscribed",lambda:all(subscriber(role["collector"],t) for t in topics if t not in inputs))
    launch("recorder",["ros2","bag","record","-o",str(out/"bag"),"-s","sqlite3","--include-unpublished-topics",
                      "--polling-interval","50","--disable-keyboard-controls","--qos-profile-overrides-path",str(out/"recorder_qos.yaml"),
                      "--topics",*topics])
    wait_for("recorder_node_visible",lambda:role["recorder"] in obs.get_node_names())
    launch("interaction",[executable("interaction"),*traceopt("interaction.csv"),"-p","policy_file:="+str(workspace/"completed_policy.py")])
    wait_for("all_seven_recorder_subscriptions_ready_before_source",all_ready_without_input)
    launch("input",[executable("synthetic_inputs"),*traceopt("inputs.csv"),"-p","seed:=41"])
    wait_for("three_role_endpoints_visible",lambda:all(publisher(role["input"],t) for t in inputs) and all_ready_without_input())
    snapshot()
    wait_for("official_source_completed",lambda:"22s source protocol complete" in (workspace/"input.console.log").read_text(errors="replace"),seconds=36)
    stop("input")
    time.sleep(.15)
    stop("interaction")
    time.sleep(.35)
    stop("collector")
    stop("recorder")
    subprocess.run(["ros2","bag","info",str(out/"bag")],check=True,stdout=(out/"bag_info.txt").open("w"))
    q=next((out/"bag").glob("*.db3"))
    with sqlite3.connect(f"file:{q}?mode=ro",uri=True) as db:
        counts=dict(db.execute("select topics.name,count(*) from messages join topics on messages.topic_id=topics.id group by topics.id"))
    assert set(counts)==set(topics) and all(v>0 for v in counts.values()),counts
    summary=dict(started_utc=started,finished_utc=utc(),seed=41,ros_distro=os.environ["ROS_DISTRO"],
                 domain_id=int(os.environ["ROS_DOMAIN_ID"]),discovery_range=os.environ["ROS_AUTOMATIC_DISCOVERY_RANGE"],
                 system=platform.platform(),rmw=get_rmw_implementation_identifier(),same_host=platform.node(),
                 topic_messages_in_bag=counts,source_to_physical_latency_s=None,events=events)
    dump("session.json",summary)
    print("BAG COUNTS",counts,flush=True)
finally:
    for name in ("input","interaction","collector","recorder"):
        stop(name)
    obs.destroy_node()
    if rclpy.ok():rclpy.shutdown()
