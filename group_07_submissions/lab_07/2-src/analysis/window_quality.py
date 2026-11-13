"""Apply the recording's protocol and sample-time acceptance rule on the PC."""
import hashlib
import json
import math
from .review_pair import STATES

DURATION=180

def acceptable(summary, protocol):
    return (summary.get("protocol")==protocol and summary["complete"] and not summary["aborted"]
            and not summary["writer_error"] and not summary["dropped"] and not summary["interruptions"]
            and not summary["physical_coinput"] and not summary["physical_stimulus_outside_script"]
            and not summary.get("model_input_problems",[])
            and (summary["last_elapsed_s"] or 0)>=DURATION and summary["written"]>0
            and summary["tof_published_frames"]>0 and set(STATES)<=set(summary["states"])
            and set(STATES)<=set(summary["behaviors"]))


def review(summary, trace, protocol):
    actual_sha = hashlib.sha256(trace).hexdigest()
    if actual_sha != summary["trace_sha256"]:
        raise ValueError("Raw trace checksum does not match its recorded summary")
    rows = trace.splitlines()
    if len(rows) != summary["written"]:
        raise ValueError("Raw trace row count differs from its recorded summary")
    result = dict(eligible=bool(acceptable(summary, protocol)), trace_sha256=actual_sha,
                  original_model_input_problems=summary.get("model_input_problems", []),
                  analysis_window_s=[0, DURATION], boundary_handoff_s=None)
    if result["eligible"]:
        return result
    if (summary.get("model_input_problems") != ["input_history_overflow"]
            or not acceptable(dict(summary, model_input_problems=[]), protocol) or len(rows)<2):
        return result
    start=summary["started_s"]
    previous=None
    matched=False
    for index,line in enumerate(rows):
        row=json.loads(line)
        if row.get("AHM",{}).get("reason") in ("input_fault","input_history_overflow","history_gap"):
            ip=row.get("input") or {}
            if (index!=len(rows)-1 or not previous
                    or previous.get("AHM",{}).get("reason")!="tracking"
                    or not (previous.get("input") or {}).get("scripted")
                    or not 0<=previous["t"]<DURATION
                    or row["AHM"]["reason"]!="input_history_overflow" or ip.get("scripted") is not False):
                return result
            clocks=(row["t"],row["owner_s"]-start,row["hormone_time_s"]-start,ip["time_s"]-start)
            if not all(math.isfinite(t) and t>=DURATION for t in clocks):
                return result
            result["boundary_handoff_s"]=dict(zip(("snapshot","owner","model","input"),clocks))
            matched=True
        previous=row
    result["eligible"]=matched
    return result
