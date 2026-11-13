"""Map recorded Pi observations to the 13 field groups, preserving each source's clock.

From the package root: python -B 02_Source/analysis/export_native_topics.py [--verify]
Standard library only. Blank fields belong to a different record type or are unavailable.
elapsed_s is relative to original/summary.json.started_s. BOOTTIME source timestamps, the
native monotonic timestamps of the five joint registers and the comparison anchor are retained.
Each row is an observed owner snapshot, ToF receipt, recognized event or pre-start face gate.
contract_groups names coverage of native fields; it does not count published ROS messages.
"""
import argparse
import csv
import gzip
import hashlib
import io
import json
import math
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROBOT = ROOT / "03_Results" / "real_robot"
DESIGN = ROOT / "04_Design"
DEMO = ROOT / "07_Evidence" / "present"
TOFSRC, TRACESRC, FACESRC = "original/tof_frames.jsonl.gz", "original/trace.jsonl.gz", "original/portrait_close.json"
BUTTON, TOUCH, DISTANCE, EVENT, EMOTION, GOAL, LED, STATUS, AHM, JOINT, FACE, DIAG, TRACE = (
    "/lamp/" + s for s in ("input/button", "input/touch", "input/distance", "interaction", "emotion",
    "servo_command", "rgb_command", "input/status", "ahm_cpg/diagnostic", "joint_states", "perception/face",
    "diagnostics", "trace"))
SNAP_GROUPS = (BUTTON, TOUCH, EMOTION, GOAL, LED, STATUS, AHM, JOINT, DIAG, TRACE)
IDS = (1, 2, 3, 4, 5)
IDS_RAW = {"goal_ticks_ID1_5":"goal_raw", "position_ticks_ID1_5":"position_raw",
           "feedback_monotonic_s_ID1_5":"sampled_monotonic_s", "voltage_V_ID1_5":"voltage_V",
           "temperature_C_ID1_5":"temperature_C", "status_raw_ID1_5":"status_raw", "torque_raw_ID1_5":"torque_raw",
           "speed_raw_ID1_5":"speed_raw", "load_raw_ID1_5":"load_raw", "current_raw_ID1_5":"current_raw",
           "moving_raw_ID1_5":"moving_raw"}
STATES = {"normal", "interested", "happy", "angry", "afraid", "sleepy"}
RECORD_KINDS = ("owner_snapshot", "tof_frame", "fsm_event", "face_gate")
HEAD = """pair condition record_type scope elapsed_s pi_time_s time_basis native_source source_record contract_groups
fsm behavior controller route safety active_contact_ids hold_epoch owner_ui_poll_age_s clock_anchor_boot_mono_boot_s
input_pi_s button_scheduled touch_scheduled near_scheduled scheduled_S physical_S_composite physical_near effective_S
input_scripted cached_tof_quality cached_tof_sequence replayed_stable_edges_count
ahm_pi_s ahm_S H R active_bank selected_bank_pi_s phi_selected_rad_update phi_ordinary_rad_update
selected_o1 selected_o2 selected_o1_decoder selected_phase_cycles selected_updates selected_envelope
ahm_applied ahm_reason ahm_mapping ahm_updates full_state_output_eligible_derived
goal_tilt_ID4_rad goal_extend_ID2_rad goal_nod_ID5_rad joint_ID1_rad joint_ID2_rad joint_ID3_rad joint_ID4_rad joint_ID5_rad
led_state led_base_rgb_255 led_r_0_1 led_g_0_1 led_b_0_1 led_alpha_contract requested_brightness
goal_ticks_ID1_5 position_ticks_ID1_5 feedback_monotonic_s_ID1_5 feedback_age_s_ID1_5
voltage_V_ID1_5 temperature_C_ID1_5 status_raw_ID1_5 torque_raw_ID1_5 speed_raw_ID1_5 load_raw_ID1_5 current_raw_ID1_5 moving_raw_ID1_5
event_id source_id event_kind event_source_elapsed_s event_dispatch_elapsed_s event_old_state event_new_state event_status event_source_class
tof_sequence tof_measurement_state tof_status_raw tof_reported_no_target tof_error tof_raw_mm tof_raw_cm tof_guard_cm tof_filtered_valid_m
face_status face_bbox_x_norm face_bbox_y_norm face_bbox_w_norm face_bbox_h_norm face_frames_process_total""".split()

# Status classification, units, corresponding CSV fields, and evidence boundaries per group.
SPECS = {
 BUTTON: ("ระดับปุ่มตามสคริปต์", "Bool", "button_scheduled;input_pi_s", "บันทึกค่าปุ่มของสคริปต์ ณ ขณะรัน ไม่มี raw/stable edge ของ GPIO รายช่องตลอดรอบ"),
 TOUCH: ("ระดับสัมผัสตามสคริปต์", "Bool", "touch_scheduled;input_pi_s", "บันทึกค่าสัมผัสของสคริปต์ ณ ขณะรัน ไม่มี raw/stable edge ของ GPIO รายช่องตลอดรอบ"),
 DISTANCE: ("ระยะจริงจาก ToF ที่ผ่านเกณฑ์", "m", "tof_filtered_valid_m;tof_sequence;tof_measurement_state;tof_status_raw", "filtered_distance_cm / 100 เฉพาะ range สถานะ 8 หรือ 9 และไม่มี error ค่า unreliable และ no_target คงสถานะแยก"),
 EVENT: ("เหตุการณ์ FSM ที่รู้จำจริง", "s relative to run start", "event_id;source_id;event_kind;event_source_elapsed_s;elapsed_s;event_dispatch_elapsed_s;event_status", "บันทึกเวลารู้จำหรือ dispatch ของ FSM รวมเหตุการณ์จากสคริปต์และเหตุการณ์ภายใน"),
 EMOTION: ("สถานะ FSM ของ owner", "six state names", "fsm;behavior", "fsm เป็นสถานะของตัวควบคุม ส่วน behavior อาจอยู่ระหว่างเปลี่ยนท่า"),
 GOAL: ("แปลงจาก goal register ที่อ่านกลับ", "rad relative to run Normal", "goal_tilt_ID4_rad;goal_extend_ID2_rad;goal_nod_ID5_rad;goal_ticks_ID1_5", "ลำดับ [ID4,ID2,ID5] ใช้ (goal_raw−normal_raw)×2π/4096 เวลาของการอ่าน register อาจต่างกันในแต่ละข้อ"),
 LED: ("คำสั่งสีฐานและ brightness", "RGB 0..1; alpha=1 by contract", "led_state;led_base_rgb_255;led_r_0_1;led_g_0_1;led_b_0_1;led_alpha_contract;requested_brightness", "ฐาน RGB/255 และ brightness ที่ร้องขอแยกคอลัมน์ alpha=1 มาจากสัญญา ไม่มีการวัดแสงจริง"),
 STATUS: ("สถานะอินพุตบางฟิลด์", "Bool, status code, aggregate count, s", "physical_S_composite;physical_near;cached_tof_quality;cached_tof_sequence;replayed_stable_edges_count;tof_measurement_state;tof_reported_no_target;tof_status_raw;tof_error", "มี physical_S รวม physical Near คุณภาพ ข้อมูล ToF และจำนวน edge ที่ AHM เล่นซ้ำ ไม่มี per-channel raw edge stream"),
 AHM: ("ค่าภายใน AHM และ bank ที่เลือก", "S,H,R,o1,o2,envelope dimensionless; phi rad/update; clock s", "ahm_S;H;R;phi_selected_rad_update;phi_ordinary_rad_update;selected_o1;selected_o2;selected_envelope;full_state_output_eligible_derived;ahm_pi_s;selected_bank_pi_s", "ใช้ phi จริงจาก banks[selected].phi ส่วน phi ภายใน AHM เป็นเส้นปกติ เกณฑ์ full-state output คำนวณจาก FSM/behavior/bank/route/envelope/applied"),
 JOINT: ("encoder ของ 5 ข้อใน snapshot", "rad relative to run Normal; feedback timestamps in monotonic s", "joint_ID1_rad;joint_ID2_rad;joint_ID3_rad;joint_ID4_rad;joint_ID5_rad;position_ticks_ID1_5;feedback_monotonic_s_ID1_5", "แปลง (position_raw−normal_raw)×2π/4096 เรียง ID1–5 แต่ละข้อมีเวลาอ่านของตัวเอง"),
 FACE: ("ไม่มีอนุกรมภาพในช่วงวัด", "normalized image x,y,width,height; capture s", "face_status;face_bbox_x_norm;face_bbox_y_norm;face_bbox_w_norm;face_bbox_h_norm;face_frames_process_total", "P1 ไม่มี observation ใบหน้าที่บันทึก P2/P3 มีหนึ่ง bbox ณ gate ก่อน t0 ต่อรอบ จำนวน frames รวมทั้ง process จึงใช้เป็นจำนวนเฟรมในช่วงไม่ได้"),
 DIAG: ("สุขภาพและค่าสถานะจริง", "V, °C, s; other registers in native raw units", "controller;safety;active_contact_ids;hold_epoch;owner_ui_poll_age_s;voltage_V_ID1_5;temperature_C_ID1_5;status_raw_ID1_5;current_raw_ID1_5;feedback_age_s_ID1_5", "เวกเตอร์เรียง ID1–5 คงค่า raw ของ device และเวลารายข้อ อายุ feedback ได้จากคู่เวลา BOOTTIME/MONOTONIC ใน snapshot"),
 TRACE: ("ลำดับเวลาและที่มาของ native owner", "elapsed and native clock s; goal in ticks", "elapsed_s;pi_time_s;source_record;native_source;clock_anchor_boot_mono_boot_s;fsm;controller;route;goal_ticks_ID1_5", "อ้างไฟล์และเลขบรรทัดต้นฉบับของ owner ใช้ร่วมกับแถวเหตุการณ์และ ToF ที่มีเวลาของตนเอง"),
}


def read_json(path):
    return json.loads(path.read_bytes())


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def packed(values):
    return json.dumps(values, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def finite(v):
    return type(v) in (int, float) and math.isfinite(v)


def csv_data(items, fields=None):
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=fields or list(items[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(items)
    return out.getvalue().encode("utf-8-sig")


def checked_lines(path, original_sha):
    checksum = hashlib.sha256()
    with gzip.open(path, "rb") as stream:
        for n, line in enumerate(stream, 1):
            checksum.update(line)
            yield n, json.loads(line)
    if checksum.hexdigest() != original_sha:
        raise ValueError(f"Uncompressed recorder checksum failed for {path.name}")


def base_row(pair, cond, kind, elapsed, pi_s, time_basis, source, source_record, groups):
    return dict(pair=pair, condition=cond, record_type=kind, scope="pre_start_gate" if kind == "face_gate" else "in_window",
                elapsed_s=elapsed, pi_time_s=pi_s, time_basis=time_basis, native_source=source,
                source_record=source_record, contract_groups="|".join(groups))


def snapshot_row(pair, cond, q, n, start, normals):
    ah, inp, led = q["AHM"], q["input"], q["led"]
    bank_name = q["selected"]
    b = q["banks"][bank_name]
    a0, mono, a1 = q["clock_anchor"]
    assert a0 <= a1 and abs((q["owner_s"] - start) - q["t"]) < 1e-7
    assert q["fsm"] in STATES and ah["condition"] == cond and ah["reason"] == "tracking" and ah["applied"]
    assert ah["r_used"] == (ah["stimulus"] if cond == "C0" else ah["h"])
    assert math.isclose(b["phi"], ah["phi_next"], abs_tol=1e-10) and finite(b["o1"]) and finite(b["o2"])
    assert inp["scripted"] and type(inp["button"]) is bool and type(inp["touch"]) is bool
    row = base_row(pair, cond, "owner_snapshot", q["t"], q["owner_s"], "Pi owner BOOTTIME snapshot", TRACESRC, n, SNAP_GROUPS)
    state_bank = q["fsm"] if q["fsm"] in ("happy", "afraid") else "body"
    eligible = (q["fsm"] == q["behavior"] and state_bank == bank_name
                and q.get("route") not in ("look","return","lean","tilt") and b["envelope"] >= 1 - 1e-9)
    rgb = led["rgb_255"]
    assert len(rgb) == 3 and all(type(v) is int and 0 <= v <= 255 for v in rgb)
    row.update(fsm=q["fsm"], behavior=q["behavior"], controller=q["controller"], route=q["route"], safety=q["safety"],
               active_contact_ids=packed(q["active_ids"]), hold_epoch=q["hold_epoch"], owner_ui_poll_age_s=q["real_ui_poll_age_s"],
               clock_anchor_boot_mono_boot_s=packed(q["clock_anchor"]), input_pi_s=inp["time_s"],
               button_scheduled=inp["button"], touch_scheduled=inp["touch"], near_scheduled=inp["logical_near"],
               scheduled_S=inp["scheduled_S"], physical_S_composite=inp["physical_S"], physical_near=inp["physical_near"],
               effective_S=inp["effective_S"], input_scripted=inp["scripted"], cached_tof_quality=inp["tof_quality"],
               cached_tof_sequence=inp["tof_sequence"], replayed_stable_edges_count=ah["replayed_stable_edges"],
               ahm_pi_s=q["hormone_time_s"], ahm_S=ah["stimulus"], H=ah["h"], R=ah["r_used"],
               active_bank=bank_name, selected_bank_pi_s=b["time_s"], phi_selected_rad_update=b["phi"],
               phi_ordinary_rad_update=ah["phi"], selected_o1=b["o1"], selected_o2=b["o2"],
               selected_o1_decoder=b["decoder_o1"], selected_phase_cycles=b["phase_cycles"], selected_updates=b["updates"],
               selected_envelope=b["envelope"], ahm_applied=ah["applied"], ahm_reason=ah["reason"],
               ahm_mapping=ah["mapping"], ahm_updates=ah["hormone_updates"], full_state_output_eligible_derived=eligible,
               led_state=led["state"], led_base_rgb_255=packed(rgb), led_r_0_1=rgb[0]/255,
               led_g_0_1=rgb[1]/255, led_b_0_1=rgb[2]/255, led_alpha_contract=1, requested_brightness=led["requested_brightness"])
    joints = {j["id"]:j for j in q["joints"]}
    assert set(joints) == set(IDS) and len(q["joints"]) == len(IDS)
    for field, rawkey in IDS_RAW.items():
        values = [joints[i][rawkey] for i in IDS]
        assert all(finite(v) for v in values)
        row[field] = packed(values)
    offset = (a0 + a1) / 2 - mono
    row["feedback_age_s_ID1_5"] = packed([q["owner_s"] - (joints[i]["sampled_monotonic_s"] + offset) for i in IDS])
    for field, i in (("goal_tilt_ID4_rad",4), ("goal_extend_ID2_rad",2), ("goal_nod_ID5_rad",5)):
        row[field] = (joints[i]["goal_raw"] - normals[str(i)]) * math.tau / 4096
    for i in IDS:
        row[f"joint_ID{i}_rad"] = (joints[i]["position_raw"] - normals[str(i)]) * math.tau / 4096
    return row


def event_row(pair, cond, e, start, line):
    t = e["recognized_s"] - start
    if not 0 <= t < 180:
        return None
    sid = e.get("source_id") or ""
    row = base_row(pair, cond, "fsm_event", t, e["recognized_s"], "Pi FSM recognized_s BOOTTIME",
                   TRACESRC, line, (EVENT,))
    row.update(event_id=e["event_id"], source_id=sid, event_kind=e["kind"], event_source_elapsed_s=e["source_s"]-start,
               event_dispatch_elapsed_s=e["dispatch_s"]-start if e.get("dispatch_s") is not None else None,
               event_old_state=e["old_state"], event_new_state=e["new_state"], event_status=e["status"],
               event_source_class=("scheduled_study_input" if sid.startswith("study_") else
                                   "internal_FSM" if sid.startswith("internal_") else "native_recorded_id"))
    return row


def tof_row(pair, cond, q, n, start):
    cm = q.get("filtered_distance_cm")
    valid = (q["measurement_state"] == "range" and q["range_status_raw"] in (8,9) and not q["error"]
             and finite(cm) and 0 <= cm <= 400)
    assert valid == (cm is not None) and abs((q["received_s"]-start)-q["elapsed_s"]) < 1e-7
    row = base_row(pair, cond, "tof_frame", q["elapsed_s"], q["received_s"], "Pi ToF received_s BOOTTIME",
                   TOFSRC, n, (DISTANCE, STATUS) if valid else (STATUS,))
    row.update(tof_sequence=q["sequence"], tof_measurement_state=q["measurement_state"], tof_status_raw=q["range_status_raw"],
               tof_reported_no_target=q["measurement_state"] == "no_target", tof_error=q.get("error"),
               tof_raw_mm=q.get("raw_range_mm"), tof_raw_cm=q.get("raw_distance_cm"), tof_guard_cm=q.get("guard_distance_cm"),
               tof_filtered_valid_m=cm/100 if valid else None)
    return row


def export_run(pair, cond, frozen):
    directory = ROBOT / f"P{pair}" / cond
    srcs = [TRACESRC, TOFSRC, "original/summary.json", "original/identity.json", "original/window_review.json"]
    if (directory / FACESRC).is_file():
        srcs.append(FACESRC)
    for src in srcs:
        key = (directory/src).relative_to(ROBOT).as_posix()
        if frozen[key] != file_hash(directory/src):
            raise ValueError(f"Input checksum mismatch {key}")
    summary, identity = (read_json(directory/"original"/f) for f in ("summary.json","identity.json"))
    assert read_json(directory/"original/window_review.json")["eligible"] and summary["complete"] and not summary["aborted"]
    start = summary["started_s"]
    output = []
    for n, q in checked_lines(directory/TRACESRC, summary["trace_sha256"]):
        if 0 <= q["t"] < 180:
            output.append(snapshot_row(pair,cond,q,n,start,identity["normal_raw"]))
            for e in q["controlled_events"]:
                event = event_row(pair,cond,e,start,n)
                if event is not None:
                    output.append(event)
    for n, q in checked_lines(directory/TOFSRC, summary["tof_frames_sha256"]):
        if 0 <= q["elapsed_s"] < 180:
            output.append(tof_row(pair,cond,q,n,start))
    if FACESRC in srcs:
        gate = read_json(directory/FACESRC)
        face = gate.get("live_face_at_measurement")
        if face is not None:
            delta = face["captured_s"] - start
            assert delta < 0 and len(face["box"]) == 4 and all(0 <= v <= 1 for v in face["box"])
            row = base_row(pair,cond,"face_gate",delta,face["captured_s"],"camera capture at gate, minus Pi run start",
                           FACESRC,"live_face_at_measurement",(FACE,))
            x,y,w,h = face["box"]
            row.update(face_status=face["status"],face_bbox_x_norm=x,face_bbox_y_norm=y,face_bbox_w_norm=w,
                       face_bbox_h_norm=h,face_frames_process_total=gate["live_face_frames"])
            output.append(row)
    output.sort(key=lambda r:r["elapsed_s"])
    assert len({r["event_id"] for r in output if r["record_type"] == "fsm_event"}) == sum(r["record_type"] == "fsm_event" for r in output)
    return output


def counts_per_group(records):
    counts = Counter()
    for row in records:
        for topic in row["contract_groups"].split("|"):
            counts[topic, row["record_type"]] += 1
    return counts


def source_and_clock(topic):
    default = "elapsed_s=owner snapshot BOOTTIME minus original/summary.json.started_s"
    if topic == DISTANCE:
        return TOFSRC, "elapsed_s=ToF received_s minus run start, seconds"
    if topic == EVENT:
        return TRACESRC + ":controlled_events", "elapsed_s=recognized_s minus run start; source/dispatch also relative seconds"
    if topic == FACE:
        return FACESRC + ":live_face_at_measurement (P2/P3 only)", "elapsed_s=captured_s minus run start; negative pre-start gate"
    if topic == STATUS:
        return TRACESRC + " + " + TOFSRC, default + " / ToF receipt minus run start"
    if topic in (GOAL, JOINT):
        return TRACESRC + ":joints + original/identity.json:normal_raw", default + "; five register sample times in Pi MONOTONIC seconds"
    if topic == AHM:
        return TRACESRC + ":AHM,banks[selected]", default + "; ahm_pi_s and selected_bank_pi_s are separate source times"
    if topic in (BUTTON, TOUCH):
        return TRACESRC + ":input", default + "; input_pi_s is the recorded input observation time"
    return TRACESRC, default


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def demo_notes():
    v = read_json(DEMO/"SESSION_VERIFICATION.json")
    for name, h in v["csv_sha256"].items():
        assert file_hash(DEMO/name) == h
    facefile = v["last_viewer_snapshot"]["file"]
    assert file_hash(DEMO/facefile) == v["last_viewer_snapshot"]["sha256"]
    viewer = read_json(DEMO/facefile)
    assert v["first_feedback_monotonic_s"] <= viewer["time_s"] <= v["last_feedback_monotonic_s"]
    events = read_csv(DEMO/"Last_Owner_FSM_Events.csv")
    feedback_file = "present_feedback.csv"
    with (DEMO/feedback_file).open(encoding="utf-8-sig", newline="") as f:
        count, fsm_labeled = 0, 0
        for row in csv.DictReader(f):
            count += 1
            fsm_labeled += row["fsm_state"] in STATES
    assert count == v["feedback_rows"] and len(events) == 50
    ne, na = len(events), len(read_csv(DEMO/"present_events.csv"))
    assert na == v["event_entries"]
    gpio = viewer["digital_inputs"]
    fsmfile = "Last_Owner_FSM_Events.csv"
    eventfile = "present_events.csv"
    names = lambda *cols: " | ".join(cols)
    s = {}
    for topic,ch in ((BUTTON,"button"),(TOUCH,"touch")):
        d = gpio[ch]
        s[topic] = ("partial, last-owner only", f"{sum(e['kind']==ch for e in events)} เหตุการณ์ {ch} ของ owner สุดท้าย; "
                    f"snapshot ปิดงานเก็บ raw_edges {len(d['raw_edges'])} และ stable_edges {len(d['stable_edges'])} รายการใน history ของ owner นี้",
                    names(fsmfile,facefile))
    s[DISTANCE] = ("partial", f"distance_cm ตามเหตุการณ์ {sum(e['distance_cm'] not in ('','N/A') for e in events)} แถวของ owner สุดท้าย และกรอบ ToF สุดท้ายหนึ่งกรอบ; ไม่มี stream ทุกกรอบ",names(fsmfile,facefile))
    s[EVENT] = ("partial", f"{ne} แถว FSM ของ owner สุดท้าย; {na} รายการ context/safety จาก 4 owners มีชนิดเหตุการณ์คนละชุด",names(fsmfile,eventfile))
    s[EMOTION] = ("sampled native state", f"พบป้าย FSM ทั้ง 6 สถานะใน {fsm_labeled:,} จาก {count:,} แถว feedback; แถว startup ไม่มีป้าย",feedback_file)
    s[GOAL] = ("per-joint goal registers", f"goal_raw ราย ID ใน {count:,} แถว; เวกเตอร์ ID4/2/5 ไม่ได้บันทึกพร้อมกันในหนึ่งแถว",feedback_file)
    s[LED] = ("partial, state label only", f"led_state_written ในตารางเหตุการณ์ owner สุดท้าย {ne} แถว; ไม่มีชุด RGBA/brightness ต่อเนื่อง",fsmfile)
    s[STATUS] = ("partial", "เหตุการณ์ owner สุดท้ายบอกอินพุตบางจุด; snapshot สุดท้ายมี GPIO edge history และคุณภาพ ToF",names(fsmfile,facefile))
    s[AHM] = ("one terminal snapshot", "rhythm.state_ahm และ selected rhythm หนึ่งค่า ณ snapshot ปิดงาน; CSV ของคลิปไม่มีลำดับ S/H/R/phi/o1/o2",facefile)
    s[JOINT] = ("per-joint samples", f"{count:,} แถว ID1–5, position_raw ตามเวลาของแต่ละข้อ; ยังไม่ได้จัดเป็น JointState พร้อมกัน",feedback_file)
    assert viewer["face"]["status"] == "LOST" and viewer["face"]["box"] is None
    s[FACE] = ("one terminal status, no bbox", f"viewer t={viewer['time_s']} s: face LOST ไม่มี box; ไม่มีอนุกรม face/target ที่ผูกกับเฟรมคลิป",facefile)
    s[DIAG] = ("per-joint samples plus safety", f"status_raw, voltage_V, temperature_C, current_raw ฯลฯ ใน {count:,} แถว; เหตุการณ์ safety แยกไฟล์",names(feedback_file,eventfile))
    s[TRACE] = ("partial owner traces", f"{count:,} feedback, {na} context/safety และ {ne} FSM เฉพาะ owner สุดท้าย; นาฬิกาวิดีโอแยกจาก feedback",names(feedback_file,eventfile,fsmfile,facefile))
    return s


def save_or_check(path, blob, verify):
    if verify:
        if path.read_bytes() != blob:
            raise ValueError(f"Stored export differs: {path}")
    else:
        path.write_bytes(blob)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true", help="Rebuild in memory; byte-compare all eight exported CSVs")
    opt = parser.parse_args()
    if not __debug__:
        parser.error("Run without -O")
    contract = read_json(DESIGN/"TOPIC_CONTRACT_13.json")["topics"]
    assert [x["topic"] for x in contract] == list(SPECS)
    frozen = read_json(ROBOT/"SHA256.json")
    demo = demo_notes()
    bag = {r["topic"]:int(r["messages_in_bag"]) for r in read_csv(ROOT/"03_Results/course_ros/message_counts.csv")}
    assert len(bag) == 7 and sum(bag.values()) == 7425 and set(bag) == set(list(SPECS)[:7])
    group_rows, totals, tof_totals = [], Counter(), Counter()
    for pair in (1,2,3):
        for cond in ("C0","C1"):
            records = export_run(pair,cond,frozen)
            counts = counts_per_group(records)
            totals.update(counts)
            tof_states = Counter(r["tof_measurement_state"] for r in records if r["record_type"] == "tof_frame")
            tof_totals.update(tof_states)
            origin = f"03_Results/real_robot/P{pair}/{cond}/native_topics.csv"
            save_or_check(ROOT/origin, csv_data(records,HEAD),opt.verify)
            for t in contract:
                name = t["topic"]
                ns, nf, ne, ng = (counts[name,k] for k in RECORD_KINDS)
                source_files, clock = source_and_clock(name)
                group_rows.append(dict(pair=pair, condition=cond, topic=name, contract_type=t["type"],
                    in_window_observed=bool(ns+nf+ne), in_window_records=ns+nf+ne, owner_snapshots=ns,
                    tof_frames=nf, fsm_events=ne, before_start_face_gate_records=ng, native_scope=SPECS[name][0],
                    source_tof_unreliable_frames=tof_states['unreliable'] if name in (DISTANCE, STATUS) else None,
                    source_tof_no_target_frames=tof_states['no_target'] if name in (DISTANCE, STATUS) else None,
                    original_source_files=source_files, time_reference=clock,
                    units=SPECS[name][1], native_csv_columns=SPECS[name][2], limitation=SPECS[name][3],
                    csv_path=origin))
            assert sum(bool(sum(counts[t,k] for k in RECORD_KINDS[:3])) for t in SPECS) == 12
            print(f"P{pair} {cond}: {counts[AHM,'owner_snapshot']} snapshots, {counts[EVENT,'fsm_event']} events, "
                  f"{counts[STATUS,'tof_frame']} ToF frames / {counts[DISTANCE,'tof_frame']} valid, "
                  f"{counts[FACE,'face_gate']} pre-start face records")
    global_rows = []
    for tc in contract:
        t = tc["topic"]
        ns,nf,ne,ng = (totals[t,k] for k in RECORD_KINDS)
        dstatus,dnote,dfiles = demo[t]
        source_files, clock = source_and_clock(t)
        global_rows.append(dict(topic=t, contract_type=tc["type"], native_scope=SPECS[t][0],
            real_robot_runs_with_in_window_observation=sum(r["in_window_observed"] for r in group_rows if r["topic"] == t),
            real_robot_runs_total=6, in_window_owner_snapshots=ns, in_window_tof_frames=nf,
            in_window_fsm_events=ne, before_start_face_gates=ng, native_csv_columns=SPECS[t][2],
            source_tof_unreliable_frames=tof_totals['unreliable'] if t in (DISTANCE, STATUS) else None,
            source_tof_no_target_frames=tof_totals['no_target'] if t in (DISTANCE, STATUS) else None,
            original_source_files=source_files, time_reference=clock,
            units_and_reference=SPECS[t][1], real_robot_limitation=SPECS[t][3],
            pi_ros_recording="12 of 13 native field groups present in each Pi run; no ROS publications counted",
            course_ros_bag_recorded=t in bag, course_ros_bag_messages=bag[t] if t in bag else 0,
            course_ros_scope="separate 5-state ROS / synthetic input / 7 topics",
            demo_coverage=dstatus, demo_evidence=dnote, demo_files=dfiles))
    save_or_check(ROBOT/"summary/Topic_coverage_by_run.csv",csv_data(group_rows),opt.verify)
    save_or_check(DESIGN/"TOPIC_COVERAGE.csv",csv_data(global_rows),opt.verify)
    print("Verified" if opt.verify else "Wrote", "six native CSVs, 78 per-run coverage rows and 13 topic crosswalk rows.")


if __name__ == "__main__":
    main()

