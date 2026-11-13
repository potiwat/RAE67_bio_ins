"""Paired observation of the actual desktop Present Safety entry, with a scripted input and an explicit response source."""
from contextlib import contextmanager, ExitStack
from collections import deque
from pathlib import Path
from unittest.mock import patch
import argparse
import hashlib
import json
import math
import os
import queue
import runpy
import shutil
import sys
import threading
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
PS=ROOT/"shared/experiments/presentation_safety_play_20261110"
ENTRY=PS/"present_safety_start.py"
SHORTCUT=Path.home()/"Desktop/Present Safety.desktop"
BLOCKS={"button":((16.,24.),),"touch":((42.,59.),(78.,78.2),(78.4,78.6),(78.8,79.)),"near":((108.,136.),)}
DURATION=180
STATES=("normal","interested","happy","angry","afraid","sleepy")
PROTOCOL="conditioned_tof_v2"


def acceptable(summary):
    return (summary.get("protocol")==PROTOCOL and summary["complete"] and not summary["aborted"]
            and not summary["writer_error"] and not summary["dropped"] and not summary["interruptions"]
            and not summary["physical_coinput"] and not summary["physical_stimulus_outside_script"]
            and not summary.get("model_input_problems",[])
            and (summary["last_elapsed_s"] or 0)>=DURATION and summary["written"]>0
            and summary["tof_published_frames"]>0 and set(STATES)<=set(summary["states"])
            and set(STATES)<=set(summary["behaviors"]))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path,data):
    tmp=path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False),encoding="utf-8")
    tmp.replace(path)


def level(ch,t):
    return any(a<=t<b for a,b in BLOCKS[ch])


def digital(ch,t,start):
    edges=[(start+x,pressed) for a,b in BLOCKS[ch] for x,pressed in ((a,True),(b,False)) if x<=t]
    return {"stable_pressed":level(ch,t),"stable_sequence":len(edges),"stable_edges":[
        {"sequence":i+1,"time_s":x,"pressed":pressed} for i,(x,pressed) in enumerate(edges)]}


def identity():
    import shlex
    lines=SHORTCUT.read_text().splitlines()
    cmd=shlex.split(next(x[5:] for x in lines if x.startswith("Exec=")))
    assert cmd==[sys.executable,"-B",str(ENTRY)],("Unexpected desktop command",cmd,sys.executable)
    assert next(x[5:] for x in lines if x.startswith("Path="))==str(ROOT)
    manifest=json.loads((PS/"manifest.json").read_text())
    for name in ("own_sha256","protected_sha256","dependency_sha256"):
        for rel,digest in manifest[name].items():
            if sha(ROOT/rel)!=digest:
                raise RuntimeError("Desktop source differs: "+rel)
    cfg=json.loads((PS/"profile.json").read_text())
    assert cfg["normal_ahm_condition"]=="C1" and cfg["presentation_mode"] and cfg["ahm_scope"]=="all_states"
    assert set(manifest["enabled_ids"])=={1,2,4}
    return {"desktop_exec":cmd,"desktop_sha256":sha(SHORTCUT),"entry_sha256":sha(ENTRY),
            "launcher_sha256":sha(PS/"launch.py"),"config_sha256":sha(PS/"config.json"),
            "profile_sha256":sha(PS/"profile.json"),"manifest_sha256":sha(PS/"manifest.json"),
            "verified_groups":{name:len(manifest[name]) for name in ("own_sha256","protected_sha256","dependency_sha256")},
            "profile_condition":cfg["normal_ahm_condition"],"start_gate":manifest["initial_start_gate"],
            "PID":cfg["startup_pid_by_id"],"normal_raw":cfg["normal_raw"],"script":BLOCKS,
            "script_sha256":hashlib.sha256(json.dumps(BLOCKS,sort_keys=True).encode()).hexdigest()}


class Capture:
    def __init__(self,condition,folder):
        self.condition=condition;self.folder=folder
        self.start=None;self.owner=None;self.last_input={};self.current_owner=None
        self.done=False;self.aborted=None;self.interruptions=set();self.real_inputs_seen=False
        self.cursor=-1.;self.serial=0;self.written=0;self.dropped=0;self.error=None;self.seed=None
        self.seen=set();self.seen_behavior=set();self.last_time=None;self.last_status=0.;self.actual_flags=None
        self.scratch=None;self.last_poll=None;self.max_poll_gap=0.;self.native_archive=None
        self.samples=[];self.writer=None;self.stop_status=threading.Event()
        self.tof_frames=[];self.suppressed_approach=0;self.physical_coinput=False;self.model_input_problems=set()
        self.obs_max_s=0.;self.trace_max_s=0.;self.slow_calls=deque(maxlen=120)
        from bio_inspire.runtime.angry_fsm import TouchBurst
        self.burst=TouchBurst()
    def open(self):
        if shutil.disk_usage("/dev/shm").free < 240*1024*1024:
            raise RuntimeError("Insufficient scratch space for a supervised recording")
        self.scratch=Path("/dev/shm")/(HERE.name+"_"+self.folder.name)
        self.scratch.mkdir(mode=0o700,exist_ok=False)
        self.writer=threading.Thread(target=self.progress,name="paired-status",daemon=True);self.writer.start()
    def progress(self):
        while not self.stop_status.wait(1):
            if self.last_time is not None:
                print("PAIR_PROGRESS",round(self.last_time,1),"complete" if self.done else "active",self.aborted or "",flush=True)
    def write(self):
        try:
            with (self.scratch/"trace.jsonl").open("x",encoding="utf-8") as f:
                for row in self.samples:
                    f.write(json.dumps(row,ensure_ascii=False,allow_nan=False,separators=(",",":"))+"\n");self.written+=1
            with (self.folder/"tof_frames.jsonl").open("x",encoding="utf-8") as stream:
                for frame in self.tof_frames:
                    stream.write(json.dumps(frame,allow_nan=False,separators=(",",":"))+"\n")
        except Exception as error:
            self.error=repr(error)
    def close(self):
        if self.writer:
            self.stop_status.set();self.writer.join(3)
            if self.writer.is_alive():self.error="writer_close_timeout"
        self.write()
        f=self.folder/"trace.jsonl"
        if self.scratch:
            trace=self.scratch/"trace.jsonl"
            if trace.exists():
                shutil.copy2(trace,f)
                if sha(trace)!=sha(f):raise RuntimeError("Scratch trace copy differs")
            if self.seed:
                original=Path(self.seed["native_log_dir"])
                if original.is_dir() and original.is_relative_to(self.scratch):
                    destination=self.folder/"native"/original.name
                    shutil.copytree(original,destination)
                    for file in original.rglob("*"):
                        if file.is_file() and sha(file)!=sha(destination/file.relative_to(original)):
                            raise RuntimeError("Native telemetry copy differs")
                    self.native_archive=str(destination)
        save(self.folder/"summary.json",self.status()|{"actual_launch_flags":self.actual_flags,
            "seed_at_start":self.seed,"trace_sha256":sha(f) if f.exists() else None,
            "native_archive":self.native_archive,"max_observed_ui_poll_gap_s":self.max_poll_gap,
            "in_memory_observer_max_ms":self.obs_max_s*1000,"native_trace_builder_max_ms":self.trace_max_s*1000,
            "slow_diagnostic_calls":list(self.slow_calls),
            "protected_identity_after":identity(),"script_is_not_physical_contact":True})
        if self.scratch and self.scratch.parent==Path("/dev/shm") and self.scratch.name==HERE.name+"_"+self.folder.name and not self.error:
            shutil.rmtree(self.scratch)
    def status(self):
        return {"condition":self.condition,"protocol":PROTOCOL,"started_s":self.start,"last_elapsed_s":self.last_time,
            "complete":self.done,"aborted":self.aborted,"writer_error":self.error,"dropped":self.dropped,
            "written":self.written,"states":sorted(self.seen),"behaviors":sorted(self.seen_behavior),
            "interruptions":sorted(self.interruptions),"physical_stimulus_outside_script":self.real_inputs_seen,
            "physical_coinput":self.physical_coinput,"suppressed_approach_candidates":self.suppressed_approach,
            "model_input_problems":sorted(self.model_input_problems),
            "tof_published_frames":len(self.tof_frames),"tof_frames_sha256":sha(self.folder/"tof_frames.jsonl") if (self.folder/"tof_frames.jsonl").is_file() else None}
    def observe_frame(self,frame):
        stamp=frame["received_s"]
        if self.in_window(stamp):
            self.tof_frames.append(dict(frame,elapsed_s=stamp-self.start))
    def in_window(self,t):
        return self.start is not None and not self.done and not self.aborted and 0<=t-self.start<DURATION
    def enter(self,m,now):
        if self.done or self.aborted:return
        adapter=m.bus.central_feedback.brake_capture
        if self.start is None:
            if adapter.core.phase!="PLAY" or m.controller.state not in ("READY","FOLLOWING") or m.behavior_trial!="normal":
                return
            if set(adapter.enabled_ids)!={1,2,4}:
                raise RuntimeError("Wrong Present Safety detector membership")
            if m.rhythm_driver.__class__.__name__!="AcceptedRhythms":
                raise RuntimeError("Wrong presentation rhythm owner")
            self.start=now;self.owner=m
            self.seed={"h":m.rhythm_driver.normal_ahm.h,"r_condition":m.rhythm_driver.normal_ahm.condition,
                       "native_log_dir":str(adapter.session.recorder.out),
                       "banks":{k:[r.o1,r.o2,r.updates,r.envelope] for k,r in m.rhythm_driver.bank.items()},
                       "route":type(m.rhythm_driver.breathing).__name__,"driver":type(m.rhythm_driver).__name__,
                       "happy_phase_divisor":m.rhythm_driver.happy.phase_divisor,"enabled_ids":sorted(adapter.enabled_ids)}
        elif self.owner is not m and not self.done:
            self.aborted="Safety created a new motor owner during the acquisition"
        if not self.done and adapter.core.phase!="PLAY":
            self.interruptions.add(adapter.core.phase)
            self.aborted="Present Safety intervention "+adapter.core.phase
    def choices(self,m,fsm,now,candidates,held):
        if not self.in_window(now) or m is not self.owner or m.bus.central_feedback.brake_capture.core.phase!="PLAY":
            return candidates,held
        # Retain real fault and real Near. A synthetic Near drives only the existing FSM.
        if m.controller.state not in ("READY","FOLLOWING") or m.operator_stopped or m.urgent_stop.is_set() or m.stopping.is_set():
            return candidates,held
        elapsed=now-self.start
        if elapsed<self.cursor:return candidates,held
        self.suppressed_approach+=sum(x["kind"]=="approach" for x in candidates)
        events=[x for x in candidates if x["kind"]!="approach"];physical_near=m.distance_gate.near
        scheduled_near=level("near",elapsed)
        if scheduled_near:
            events=[x for x in events if x["kind"]!="clear"]
        for channel in ("button","touch","near"):
            for a,b in BLOCKS[channel]:
                if self.cursor < a <= elapsed:
                    stamp=self.start+a
                    events.append(dict(kind=channel,source_s=stamp,source_id=f"study_{channel}_{a:.1f}"))
                    if channel=="touch" and fsm.state not in ("angry","afraid") and not physical_near and self.burst.press(stamp,now):
                        events.append(dict(kind="touch_burst",source_s=stamp,source_id=f"study_burst_{a:.1f}"))
                if channel=="near" and self.cursor<b<=elapsed and not physical_near and not any(e["kind"]=="clear" for e in events):
                    events.append(dict(kind="clear",source_s=self.start+b,source_id="study_near_released"))
        if scheduled_near and fsm.state!="afraid" and not any(e["kind"]=="near" for e in events):
            events.append(dict(kind="near",source_s=self.start+BLOCKS["near"][0][0],source_id="study_near_held"))
        self.cursor=elapsed
        return events,held or level("touch",elapsed) or level("button",elapsed)
    def record(self,m,row):
        if self.start is None or self.done or self.aborted:return
        t=row["time_s"]-self.start
        if t<0:return
        a=m.bus.central_feedback.brake_capture
        if a.core.phase!="PLAY":
            self.interruptions.add(a.core.phase)
            self.aborted="Present Safety intervention "+a.core.phase
        if not self.aborted and m is not self.owner:self.aborted="Motor owner changed"
        if not self.aborted and row["state"] in ("FAULT","STOPPED") and t<DURATION:self.aborted="controller "+row["state"]
        if self.aborted:
            self.last_time=t
            return
        driver=m.rhythm_driver; rh=driver.rhythm;ah=getattr(rh,"modulation_status",{}).get("state_ahm",{})
        if ah.get("applied") and ah.get("reason") in ("input_fault","input_history_overflow","history_gap"):
            self.model_input_problems.add(ah["reason"])
        fsm=m.automatic_fsm;model=fsm.fsm
        ev=[]
        if model:
            for e in model.events:
                serial=int(e["event_id"].rsplit("_",1)[1])
                if serial>self.serial:ev.append(dict(e));self.serial=serial
        fstate=model.state if model else None
        if fstate:self.seen.add(fstate)
        self.seen_behavior.add(str(row["behavior"]))
        banks={k:{"o1":r.o1,"o2":r.o2,"updates":r.updates,"phi":r.phi,"envelope":r.envelope,
                  "time_s":r.last_time,"decoder_o1":getattr(r,"interpolated_o1",r.o1),
                  "phase_cycles":getattr(r,"decoder_phase_cycles",r.phase_cycles)} for k,r in driver.bank.items()}
        b0=m.now();mon=time.monotonic();b1=m.now()
        sample={"t":t,"owner_s":row["time_s"],"clock_anchor":[b0,mon,b1],"behavior":row["behavior"],"fsm":fstate,
                "real_ui_poll_age_s":None if self.last_poll is None else row["time_s"]-self.last_poll,
                "controller":row["state"],"route":getattr(getattr(m.controller,"pose_route",None),"phase",None),
                "safety":a.core.phase,"active_ids":sorted(a.enabled_ids),"hold_epoch":getattr(a.core,"hold_epoch",None),
                "tof_quality":getattr(a,"sensor_snapshot",{}).get("quality"),"banks":banks,
                "selected":next((k for k,r in driver.bank.items() if r is rh),None),
                "hormone_time_s":driver.normal_ahm.last_time,"AHM":dict(ah),"input":dict(self.last_input),
                "out":{k:v for k,v in m.rhythm_view_cache.items() if k in ("command_offsets_deg","envelope","accepted_happy_hormone","small_happy","decoded_body_offsets_deg","time_scale")},
                "led":dict(getattr(m,"presentation_led_output",{})),"controlled_events":ev,
                "joints":[dict(j) for j in row.get("rows",[])],"normal_targets":dict(row.get("joint_targets") or {})}
        if len(self.samples)<5500:self.samples.append(sample)
        else:self.dropped+=1
        self.last_time=t
        if t>=DURATION:self.done=True
    def observe_input(self,original,m,now,details):
        physical={}
        raw=original(m,now,physical)
        if details is not None:details.update(physical)
        t=m.now()
        if not self.in_window(t) or raw is None or m is not self.owner:
            self.last_input={"time_s":t,"physical_S":raw,"effective_S":raw,"scripted":False}
            return raw
        e=t-self.start
        d=bool(level("button",e) or level("touch",e) or level("near",e))
        actual=float(bool(raw or d))
        if raw and not d:self.real_inputs_seen=True
        if raw:self.physical_coinput=True
        physical_levels=[v.get("stable_pressed") for v in physical.get("views",[])]
        if details is not None:
            views=[digital(ch,e,self.start) for ch in ("button","touch")]
            for v,p in zip(views,physical_levels):
                v["stable_pressed"]=bool(v["stable_pressed"] or p)
            details.update(views=views,near=bool(physical.get("near") or level("near",e)))
        self.last_input={"time_s":t,"physical_S":raw,"effective_S":actual,"scheduled_S":int(d),
                         "scripted":True,"physical_near":physical.get("near"),
                         "button":level("button",e),"touch":level("touch",e),"logical_near":level("near",e),
                         "tof_quality":physical.get("tof_quality"),"tof_sequence":(physical.get("tof_frame") or {}).get("sequence")}
        return actual


def hooks(cap, original):
    @contextmanager
    def instrumented(*a,**kw):
        if cap.scratch:
            a=(a[0],cap.scratch/"native",*a[2:])
        with original(*a,**kw) as sessions, ExitStack() as stack:
            from shared.experiments.presentation_safety_play_20261110.range_conditioning import RangeFilter
            original_frame=RangeFilter.frame
            def observe_frame(bank,*args,**kwargs):
                frame=original_frame(bank,*args,**kwargs)
                cap.observe_frame(frame)
                return frame
            stack.enter_context(patch.object(RangeFilter,"frame",observe_frame))
            from bio_inspire.runtime import camera_motor,normal_ahm,automatic_fsm,angry_fsm,presentation_accepted_20261110 as accepted
            import play_view
            cap.actual_flags=list(sys.argv[1:])
            required={"--experimental-contact","--auto-contact-recovery","--accepted-coordination","--id1-effort-trial",
                      "--id2-effort-trial","--id4-effort-trial","--tof-mode2-trial","--isolate-tof","1,2,4"}
            assert required.issubset(cap.actual_flags)
            fsm_service=automatic_fsm.AutomaticFSM.service;fsm_step=angry_fsm.AngryFSM.step
            source=normal_ahm.read_stimulus;constructor=normal_ahm.NormalAHM.__init__
            happy_step=accepted.AcceptedRhythms.step;trace=camera_motor.CameraMotor._record_trace;draw=play_view.draw
            original_poll=camera_motor.CameraMotor.poll
            def monitor_poll(m):
                result=original_poll(m)
                stamp=m.last_frame
                if cap.start is not None and not cap.done and cap.last_poll is not None:
                    cap.max_poll_gap=max(cap.max_poll_gap,stamp-cap.last_poll)
                cap.last_poll=stamp
                return result
            def init_mod(self,c):
                if c!="C1":raise ValueError("Unexpected source profile condition")
                constructor(self,cap.condition)
            def fservice(self,m,now):
                cap.enter(m,now);cap.current_owner=m
                try:return fsm_service(self,m,now)
                finally:cap.current_owner=None
            def fstep(self,now,candidates,*,ready=True,held=False):
                m=cap.current_owner
                if m is not None and getattr(m.automatic_fsm,"fsm",None) is self:
                    candidates,held=cap.choices(m,self,now,candidates,held)
                return fsm_step(self,now,candidates,ready=ready,held=held)
            def read_input(m,now,details=None):
                return cap.observe_input(source,m,now,details)
            def cpg_step(self,m,now):
                result=happy_step(self,m,now)
                if cap.condition=="C0" and self.mode=="happy":
                    r=self.happy.rhythm;view=r.modulation_status.get("state_ahm",{})
                    if view.get("applied"):
                        phi=accepted.happy_phi(view["r_used"])
                        r.set_ahm_phi(phi)
                        r.modulation_status["state_ahm"]={**view,"phi_next":phi,"mapping":"accepted_happy_band_direct_S"}
                return result
            def record(m,row):
                before=time.monotonic()
                result=trace(m,row)
                after=time.monotonic();cap.trace_max_s=max(cap.trace_max_s,after-before)
                if after-before>.015:cap.slow_calls.append(("native_trace",before,after-before))
                if cap.start is not None and not cap.done:
                    try:cap.record(m,row)
                    except Exception as err:
                        cap.aborted="observer "+repr(err);cap.error=repr(err)
                    duration=time.monotonic()-after;cap.obs_max_s=max(cap.obs_max_s,duration)
                    if duration>.015:cap.slow_calls.append(("observation",after,duration))
                return result
            def overlay(cv,image,result,motor=None,start_error=""):
                out=draw(cv,image,result,motor,start_error)
                line=("Study interrupted - support lamp then Q" if cap.aborted else
                      ("Complete 180/180s - support lamp then Q" if cap.done else
                      (f"{cap.last_time or 0:.0f}/180s - automatic six states" if cap.start is not None else "Five base releases to start")))
                out=cv.copyMakeBorder(out,0,22,0,0,cv.BORDER_CONSTANT,value=(43,42,22))
                cv.putText(out,cap.condition+" | "+line,(7,out.shape[0]-6),cv.FONT_HERSHEY_SIMPLEX,.41,(190,242,240),1)
                return out
            for obj,name,fn in ((normal_ahm.NormalAHM,"__init__",init_mod),(automatic_fsm.AutomaticFSM,"service",fservice),
                    (angry_fsm.AngryFSM,"step",fstep),(normal_ahm,"read_stimulus",read_input),
                    (accepted.AcceptedRhythms,"step",cpg_step),(camera_motor.CameraMotor,"_record_trace",record),
                    (camera_motor.CameraMotor,"poll",monitor_poll),(play_view,"draw",overlay)):
                stack.enter_context(patch.object(obj,name,fn))
            yield sessions
    return instrumented


def main():
    arg=argparse.ArgumentParser();arg.add_argument("condition",choices=("C0","C1"));arg.add_argument("--check",action="store_true")
    arg.add_argument("--desktop-entry",default=str(ENTRY))
    arg.add_argument("--pair",type=int,choices=(1,2,3),default=1)
    opts=arg.parse_args()
    assert Path(opts.desktop_entry).resolve()==ENTRY.resolve()
    os.chdir(ROOT);sys.path[:0]=[str(ROOT),str(ROOT/"bio_inspire/runtime"),str(ROOT/"shared/runtime")]
    ident=identity()
    from shared.experiments.presentation_safety_play_20261110 import launch
    from bio_inspire.runtime import presentation_accepted_20261110 as accepted
    ident["happy_phi_low"]=accepted.happy_phi(0);ident["happy_phi_high"]=accepted.happy_phi(1)
    out=ROOT/"shared/hardware/lab07_present_safety_pair1_20261112"/PROTOCOL/f"P{opts.pair}"
    folder=out/(opts.condition+"_"+str(time.time_ns()))
    cap=Capture(opts.condition,folder)
    if not opts.check:
        folder.mkdir(parents=True,exist_ok=False)
        save(folder/"identity.json",ident|{"study_sha256":sha(__file__),"effective_condition":opts.condition,"protocol":PROTOCOL,"pair":opts.pair})
        save(HERE/(f"{PROTOCOL}_P{opts.pair}_{opts.condition}_last.json"),{"folder":str(folder)})
        cap.open()
    try:
        viewer_args=launch.viewer_arguments
        def without_snapshot_write(preview,profile):
            args=viewer_args(preview,profile)
            assert args.count("--diagnostic-snapshot")==1
            return [arg for arg in args if arg!="--diagnostic-snapshot"]
        with patch.object(launch,"runtime_surfaces",hooks(cap,launch.runtime_surfaces)),patch.object(launch,"viewer_arguments",without_snapshot_write):
            sys.argv=[str(ENTRY)]+(["--check"] if opts.check else [])
            # Invoke the production entry function itself. Its own hash guard and owner gate run normally.
            namespace=runpy.run_path(str(ENTRY),run_name="verified_present_safety_entry")
            namespace["main"]()
    finally:
        if not opts.check:cap.close()
    if opts.check:print("PRESENT_SAFETY_PAIR_CHECK",opts.condition,json.dumps(ident,ensure_ascii=False))


if __name__=="__main__":main()

