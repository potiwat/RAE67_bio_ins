"""Decode one 180-second recording and its five native servo streams.

Acquisition-specific parsing, timing and export precision follow review_pair.py.
Only the CSVs required by the six-record submission are produced.
"""
from collections import Counter
import csv
import gzip
import hashlib
import json
import numpy as np

STATES=("normal","interested","happy","angry","afraid","sleepy")
BANK={s:("happy" if s=="happy" else "afraid" if s=="afraid" else "body") for s in STATES}
JOINT={"normal":2,"interested":2,"happy":1,"angry":2,"afraid":3,"sleepy":3}
GAP=.30
DEG=360/4096


def obj(path):
    return json.loads(path.read_text(encoding="utf-8"))


def unpack(path):
    with gzip.open(path,"rt",encoding="utf8") as f:return [json.loads(l) for l in f]


def write_export(path,values):
    rows=list(values)
    if not rows:return
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8-sig",newline="") as f:
        fields=list(dict.fromkeys(k for row in rows for k in row))
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for row in rows:
            writer.writerow({k:(round(float(v),8) if isinstance(v,(float,np.floating)) else v) if v is not None else "N/A" for k,v in row.items()})


def decode_record(d, c, out):
    identity=obj(d/"identity.json");su=obj(d/"summary.json");pr=obj(d/"shortcut_profile.json")
    raw=gzip.decompress((d/"trace.jsonl.gz").read_bytes())
    assert hashlib.sha256(raw).hexdigest()==su["trace_sha256"]
    assert su["complete"] and not su["aborted"] and not su["writer_error"] and not su["dropped"] and not su["interruptions"]
    assert set(STATES)<=set(su["states"]) and set(STATES)<=set(su["behaviors"])
    assert su["seed_at_start"]["enabled_ids"]==[1,2,4] and su["seed_at_start"]["r_condition"]==c
    assert identity["desktop_exec"][-1].endswith("/present_safety_start.py")
    assert identity["profile_sha256"]==hashlib.sha256((d/"shortcut_profile.json").read_bytes()).hexdigest()
    for k in ("manifest_sha256","profile_sha256","desktop_sha256","config_sha256","entry_sha256","launcher_sha256"):
        assert identity[k]==su["protected_identity_after"][k]
    native=json.loads(gzip.decompress((d/"native_summary.json.gz").read_bytes()))
    pid_before=native.get("pid_before");pid_after=native.get("pid_after")
    if pid_before is not None:assert pid_before==pid_after
    allrows=[json.loads(l) for l in raw.splitlines()];assert len(allrows)==su["written"]
    rows=[];events=[];bankrows=[];last_model=-1.;start=su["started_s"]
    offsets=[];half=[];mapping=[];invalid_inputs=0;external=0;state_coverage=Counter()
    for r in allrows:
        if not 0<=r["t"]<180:continue
        assert r["safety"]=="PLAY" and r["active_ids"]==[1,2,4]
        a=r["AHM"];b0,m,b1=r["clock_anchor"];offsets.append((b0+b1)/2-m);half.append((b1-b0)/2)
        for e in r["controlled_events"]:
            if e.get("recognized_s",0)<start:continue
            events.append({"condition":c,"event":e["kind"],"source_id":e.get("source_id"),
               "status":e["status"],"from_state":e["old_state"],"to_state":e["new_state"],
               "source_s":e["source_s"]-start,"recognized_s":e["recognized_s"]-start,
               "dispatch_s":None if e.get("dispatch_s") is None else e["dispatch_s"]-start})
        inp=r["input"];fsm=r["fsm"];ss=r["selected"]
        if fsm not in STATES or ss not in ("body","afraid","happy") or not a:continue
        t=r["hormone_time_s"]-start
        if t<=last_model or not 0<=t<180:continue
        last_model=t;B=r["banks"][ss];active=bool(a.get("applied"));valid=active and a["reason"]=="tracking" and a["stimulus"] is not None
        if valid:
            rr=a["stimulus"] if c=="C0" else a["h"];assert a["condition"]==c
            assert abs(a["r_used"]-rr)<1e-9 and abs(a["phi"]-(.10+.03*rr))<1e-9
            expected=(identity["happy_phi_low"]+(.13-identity["happy_phi_low"])*rr) if a["state"]=="happy" and ss=="happy" else .10+.03*rr
            err=abs(B["phi"]-expected);mapping.append(err)
            assert abs(B["phi"]-a["phi_next"])<1e-9 and err<1e-8, (t,c,a,ss,B)
        else:invalid_inputs+=1
        for name,v in r["banks"].items():
            bankrows.append({"condition":c,"snapshot_s":r["t"],"t":v["time_s"]-start if v["time_s"] is not None else None,
                             "fsm":fsm,"behavior":r["behavior"],"bank":name,"selected":int(name==ss),"o1":v["o1"],"o2":v["o2"],
                             "phi_rad_per_update":v["phi"],"decoder_o1":v["decoder_o1"],"envelope":v["envelope"],"updates":v["updates"]})
        if inp.get("physical_S") and not inp.get("scheduled_S"):external+=1
        row={"condition":c,"t":t,"snapshot_s":r["t"],"fsm":fsm,"behavior":r["behavior"],"selected":ss,"valid":int(valid),
             "physical_S":inp.get("physical_S"),"scheduled_S":inp.get("scheduled_S"),"S":a.get("stimulus"),"H":a["h"],"R":a["r_used"],
             "phi_base":a["phi"],"phi_selected":B["phi"],"mapping":a.get("mapping"),"active_o1":B["o1"],"active_o2":B["o2"],
             "route":r["route"],"reason":a["reason"],"UI_poll_age_s":r.get("real_ui_poll_age_s"),
             "script_button":inp.get("button"),"script_touch":inp.get("touch"),"script_near":inp.get("logical_near")}
        for name,v in r["banks"].items():
            for k in ("o1","o2","envelope","updates","phi","phase_cycles"):
                row[name+"_"+k]=v[k]
            row[name+"_t"]=v["time_s"]-start if v["time_s"] is not None else None
        row["state_output_on"]=int(valid and ss==BANK[fsm] and r["behavior"]==fsm and B["envelope"]>=.95)
        rows.append(row);state_coverage[fsm]+=1
    assert set(state_coverage)==set(STATES)
    mo=float(np.median(offsets)); assert max(offsets)-min(offsets)<.02
    nativefeedback=unpack(d/"native_feedback.jsonl.gz");joints={}
    for j in range(1,6):
        jr=[];n=pr["normal_raw"][str(j)];last=0
        for q in nativefeedback:
            if q["id"]!=j:continue
            t=q["time_s"]+mo-start
            if not 0<=t<180 or not q["complete_feedback"] or q["time_s"]<=last:continue
            last=q["time_s"];jr.append({"condition":c,"t":t,"joint":j,"fsm":q["fsm_state"],"behavior":q["behavior"],
                 "controller":q["controller_state"],"route":q["route_phase"],"goal_ticks":q["goal_raw"],"encoder_ticks":q["position_raw"],
                 "internal_ticks":q["internal_target_raw"],"target_deg":(q["goal_raw"]-n)*DEG,"encoder_deg":(q["position_raw"]-n)*DEG,
                 "error_deg":(q["goal_raw"]-q["position_raw"])*DEG,"status":q["status_raw"],"torque":q["torque_raw"],
                 "speed_raw":q["speed_signed_raw"],"load_raw":q["load_signed_raw"],"current_raw":q["current_raw"],
                 "V":q["voltage_V"],"T_degC":q["temperature_C"]})
        joints[j]=jr;assert jr
    times=np.asarray([r["t"] for r in rows])
    # The recorded export defines rhythm_on for the three focus joints.
    for primary in sorted(set(JOINT.values())):
        for q in joints[primary]:
            idx=int(np.searchsorted(times,q["t"],side="right"))-1
            q["rhythm_on"]=int(idx>=0 and q["t"]-times[idx]<=GAP and rows[idx]["state_output_on"] and rows[idx]["fsm"]==q["fsm"])
    steps=[]
    for edge,end,high in [(16,24,True),(24,42,False),(42,59,True),(59,78,False),(108,136,True),(136,180,False)]:
        window=[v for v in rows if edge<=v["t"]<end and v["valid"] and bool(v["S"])==high]
        first=window[0] if window else None
        met=next((v for v in window if (v["R"]>=.9 if high else v["R"]<=.1)),None)
        prior=next((v for v in reversed(rows) if met and v["t"]<met["t"] and v["valid"]),None)
        steps.append({"condition":c,"scheduled_edge_s":edge,"edge":"ON" if high else "OFF",
             "S_first_seen_s":first["t"] if first else None,"R90_first_seen_s":met["t"] if met else None,
             "source_to_R90_s":met["t"]-edge if met else None,"first_S_to_R90_s":met["t"]-first["t"] if first and met else None,
             "crossing_lower_bound_s":max(edge,prior["t"]) if prior else None,"crossing_upper_bound_s":met["t"] if met else None})
    base_d=[abs(b["phi_base"]-a["phi_base"]) for a,b in zip(rows,rows[1:]) if a["valid"] and b["valid"]]
    checks={"condition":c,"run_id":su["seed_at_start"]["native_log_dir"].split("/")[-1],"desktop_sha256":identity["desktop_sha256"],
       "entry_sha256":identity["entry_sha256"],"profile_sha256":identity["profile_sha256"],"manifest_sha256":identity["manifest_sha256"],
       "study_sha256":identity["study_sha256"],"schedule_sha256":identity["script_sha256"],"trace_sha256":su["trace_sha256"],
       "duration_s":su["last_elapsed_s"],"start_boot_s":start,"snapshots":su["written"],"distinct_signals":len(rows),"dropped":su["dropped"],
       "states":",".join(sorted(state_coverage)),"verified_phi_rows":len(mapping),"max_phi_model_error":max(mapping),
       "max_abs_observed_base_phi_change":max(base_d),"invalid_hormone_rows":invalid_inputs,"extra_physical_input_rows":external,
       "CPG_gap_max_s":float(max(np.diff(times))),"CPG_gaps_over_0p3":int(np.sum(np.diff(times)>GAP)),
       "max_UI_poll_gap_s":su.get("max_observed_ui_poll_gap_s"),"observation_max_ms":su.get("in_memory_observer_max_ms"),
       "PID_readback_equal":pid_before==pid_after if pid_before is not None else None,
       "native_feedback_samples":sum(len(j) for j in joints.values()),"feedback_clock_anchor_halfwidth_max_ms":1000*max(half),
       "detector_ids":"1,2,4","seed_at_gate":su["seed_at_start"]["banks"],"H_at_gate":su["seed_at_start"]["h"]}
    write_export(out/"control.csv",rows)
    write_export(out/"all_CPG_banks.csv",bankrows)
    write_export(out/"five_joint_feedback.csv",sorted(sum(joints.values(),[]),key=lambda a:a["t"]))
    return steps, events, checks
