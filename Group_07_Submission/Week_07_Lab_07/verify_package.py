"""Verify the local Lab 7 delivery and its recorded data. This checker only reads files."""
import csv
import gzip
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from collections import Counter
from pathlib import Path
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parent
DOCS=("01_Proposal/Week07_Proposal_Current_TH.docx","03_Results/Week07_Results_TH.docx","05_Worksheet/Week07_Worksheet_TH.docx")
ESTATES={"normal","happy","angry","interested","afraid","sleepy"}
MOVIE="07_Evidence/present/IMG_4568.MOV"
VIDEO_LINK="https://youtu.be/-zckfxbT9Jk?feature=shared"

def require(ok,message):
    if not ok:
        raise ValueError(message)

def digest(path):
    with path.open("rb") as f:
        h=hashlib.sha256()
        for part in iter(lambda:f.read(4*1024*1024),b""):h.update(part)
    return h.hexdigest()

def rows(path):
    with path.open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))

def obj(path):return json.loads(path.read_text(encoding="utf-8-sig"))

def manifest_check():
    manifest=obj(ROOT/"MANIFEST_SHA256.json")
    files={p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*") if p.is_file()
           and p!=ROOT/"MANIFEST_SHA256.json" and "__pycache__" not in p.parts and ".git" not in p.parts
           and p.suffix not in (".pyc",".pyo") and not p.name.startswith("~$")}
    require(set(manifest)==files,"Package inventory changed")
    for name,value in manifest.items():
        path=(ROOT/name).resolve()
        require(path.is_relative_to(ROOT) and digest(path)==value,"SHA-256 mismatch: "+name)
    return len(manifest)

def real_check():
    base=ROOT/"03_Results/real_robot";index=rows(base/"summary/Run_index.csv")
    require({(int(x["pair"]),x["condition"]) for x in index}=={(p,c) for p in (1,2,3) for c in ("C0","C1")} and len(index)==6,"Invalid paired design")
    count=0; model_rows=0;identities=set();accepted=set()
    for entry in index:
        p,c=entry["pair"],entry["condition"];d=base/("P"+p)/c/"original"
        su=obj(d/"summary.json");ident=obj(d/"identity.json");check=obj(d/"window_review.json")
        require(check["eligible"] and su["complete"] and not su["aborted"] and not su["interruptions"] and not su["dropped"] and not su["writer_error"],"Ineligible trial P"+p+c)
        require(su["last_elapsed_s"]>=180 and ESTATES<=set(su["states"]) and ESTATES<=set(su["behaviors"]),"Incomplete time or states")
        require(su["seed_at_start"]["enabled_ids"]==[1,2,4] and su["seed_at_start"]["r_condition"]==c and su["seed_at_start"]["h"]==0,"Invalid gate identity")
        h=hashlib.sha256();n=0
        with gzip.open(d/"trace.jsonl.gz","rb") as f:
            for line in f:h.update(line);n+=1
        require(h.hexdigest()==su["trace_sha256"]==entry["trace_sha256"] and n==su["written"]==int(entry["raw_rows"]),"Trace checksum or rows mismatch")
        require(digest(d/"shortcut_manifest.json")==ident["manifest_sha256"]==entry["manifest_sha256"],"Incorrect present launcher manifest")
        count+=n;model_rows+=int(entry["in_window_phi_rows"]);identities.add((ident["manifest_sha256"],ident["study_sha256"]));accepted.add(h.hexdigest())
    require(len(identities)==1 and count==21464 and model_rows==21458,"Evidence total or version mismatch")
    require(not {x["trace_sha256"] for x in obj(base/"excluded_attempts.json")}.intersection(accepted),"An accepted trace also appears in exclusions")
    for part in (base/"summary/Worksheet_M1_M2.csv",ROOT/"03_Results/simulation/Worksheet_M1_M2.csv"):
        met=rows(part)
        require(len(met)==36 and {(int(v["pair"]),v["condition"],v["state"]) for v in met}=={(p,c,st) for p in (1,2,3) for c in ("C0","C1") for st in ESTATES},"Incomplete state table: "+str(part))
    return count,model_rows

def evidence_check():
    d=ROOT/"07_Evidence/present";v=obj(d/"SESSION_VERIFICATION.json")
    require(digest(ROOT/MOVIE)==v["video"]["sha256"] and (ROOT/MOVIE).stat().st_size==v["video"]["size_bytes"],"Video copy differs")
    counts=Counter();states=set();times=[]
    with (d/"present_feedback.csv").open(encoding="utf-8-sig",newline="") as f:
        for row in csv.DictReader(f):counts[int(row["id"])]+=1;states.add(row["fsm_state"]);times.append(float(row["elapsed_s"]))
    require(set(counts)=={1,2,3,4,5} and ESTATES<=states and len(times)==v["feedback_rows"]==64212,"Demo rows, joints or states missing")
    require(abs(max(times)-min(times)-v["duration_s"])<.00001 and v["video"]["duration_s"]==632.18,"Video or feedback span differs")
    require(all(digest(d/name)==sha for name,sha in v["csv_sha256"].items()),"Original CSV hash differs")
    for note in (ROOT/"README.md",d/"README_TH.md"):
        require(VIDEO_LINK in note.read_text(encoding="utf-8"),"Missing direct viewing link")
    return len(times),v["duration_s"]

def documents_check():
    require({s.relative_to(ROOT).as_posix() for s in ROOT.rglob("*.docx") if not s.name.startswith("~$")}==set(DOCS),"Unexpected Word document")
    w="{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    banned=re.compile(r"normal_controlled_pilot|real_robot_final|simulation_final|20261106T044600Z|46,053|85,032|7,098|0\.3212\b|0\.2698\b|(?:รอบละ|ต่อเงื่อนไข)\s*600\s*(?:วินาที|seconds?\b|s\b)|esp[- ]?32|micro[- ]?ros",re.I)
    for name in DOCS:
        with zipfile.ZipFile(ROOT/name) as z:
            require(z.testzip() is None,"Invalid Word file: "+name)
            root=ET.fromstring(z.read("word/document.xml"));text=" ".join((v.text or "") for v in root.iter(w+"t"))
            checked_text=text.replace("micro ROS และ ESP32","") if name==DOCS[2] else text
            require(banned.search(checked_text) is None,"Historical result in "+name)
            require("180" in text and ("21,464" in text or "21464" in text),"Current protocol missing in "+name)
            if name==DOCS[1]:
                embedded={hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist() if n.startswith("word/media/")}
                figures={digest(f) for f in (ROOT/"03_Results/Figures").glob("*.png")}
                require(embedded==figures,"Report figures differ from the delivered PNGs")
    require(banned.search((ROOT/"05_Worksheet/worksheet.md").read_text(encoding="utf-8-sig").replace("micro ROS และ ESP32","")) is None,"Historical result in Markdown worksheet")
    for relative in ("README.md","LAB07_REQUIREMENTS_TH.md","03_Results/README_TH.md","04_Design/README_TH.md","05_Worksheet/worksheet.md","06_References/README_TH.md","07_Evidence/present/README_TH.md"):
        path=ROOT/relative;text=path.read_text(encoding="utf-8-sig")
        for match in re.finditer(r"\]\((?:<([^>]+)>|([^\s)]+))\)",text):
            link=match.group(1) or match.group(2);parts=urlsplit(link)
            if parts.scheme or not parts.path:continue
            target=(path.parent/unquote(parts.path)).resolve()
            require(target.is_relative_to(ROOT) and target.exists(),f"Broken link in {relative}: {link}")

def course_check():
    base=ROOT/"03_Results"
    proof=obj(ROOT/"06_References/TEACHER_LAB07_SOURCE.json")
    upstream=proof["files"]
    checker=base/"course_bridge/runtime/check_submission.py"
    proposal_checker=ROOT/"01_Proposal/check_proposal.py"
    contract=ROOT/"04_Design/interface_contract.json"
    for file,key in ((checker,"check_submission.py"),(proposal_checker,"check_proposal.py"),(contract,"interface_contract.json")):
        require(digest(file)==upstream[key]["sha256"],"Teacher reference checksum differs: "+key)
    policy=checker.with_name("completed_policy.py")
    with tempfile.TemporaryDirectory() as tmp:
        policy_copy=Path(tmp)/policy.name;shutil.copyfile(policy,policy_copy)
        for command in ([str(checker),"--policy-file",str(policy_copy),"--contract","group"],
                        [str(proposal_checker),str(ROOT/"01_Proposal/proposal.json")]):
            result=subprocess.run([sys.executable,"-B",*command],capture_output=True,text=True,timeout=15)
            require(result.returncode==0,"Official checker failed: "+result.stdout+result.stderr)
    cv=obj(base/"course_bridge/verification.json")
    require(cv["group_checker_transition_pairs"]==40 and cv["group_checker_failures"]==0 and cv["matched_seeds"]==[41,42,43]
            and cv["preregistered_primary_rows"]==42 and cv["retained_source_outcomes"]==60,"Missing matched bridge results")
    seven={v["name"] for v in obj(contract)["topics"]}
    extended={v["topic"] for v in obj(ROOT/"04_Design/TOPIC_CONTRACT_13.json")["topics"]}
    ros=rows(base/"course_ros/message_counts.csv");report=obj(base/"course_ros/verification.json")
    require(len(seven)==7 and len(extended)==13 and seven<extended,"Topic design count mismatch")
    require({v["topic"] for v in ros}==seven and sum(int(v["messages_in_bag"]) for v in ros)==7425 and report["verified_all_cdr_messages"],"Invalid observed 7-topic ROS evidence")
    require(len(rows(ROOT/"04_Design/TOPIC_COVERAGE.csv"))==13 and len(rows(base/"real_robot/summary/Topic_coverage_by_run.csv"))==78,"Incomplete native coverage inventory")

if __name__=="__main__":
    files=manifest_check()
    count,models=real_check()
    n,seconds=evidence_check()
    documents_check()
    course_check()
    print(f"PASS | {files} file hashes | 3 Word documents | 6 real runs | {count:,} trace rows | {models:,} parameter samples | {n:,} demonstration rows over {seconds:.3f} s | official proposal and group policy checks | 7 ROS topics | 13 native coverage entries.")
