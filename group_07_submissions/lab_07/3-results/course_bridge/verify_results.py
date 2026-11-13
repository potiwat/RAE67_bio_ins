"""Reconcile the six official offline traces and the independent recorded-input replay."""
import argparse
from collections import Counter
import csv
from datetime import datetime
from hashlib import sha256
import io
import json
import math
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parent
RUNS = ROOT / "runs_20261112"
REPLAY = ROOT / "replay_seed42_20261112"
STATES = {"normal", "interested", "happy", "afraid", "sleepy"}
MATCH = ("sequence", "channel", "topic", "type", "value", "source_time_s",
         "sample_time_s", "publish_time_s", "input_id")


def read_json(path):
    return json.loads(path.read_bytes())


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def rows(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def check_manifest(folder):
    frozen = read_json(folder / "manifest.json")["sha256"]
    files = {p.relative_to(folder).as_posix() for p in folder.rglob("*")
             if p.is_file() and p != folder / "manifest.json"}
    assert files == set(frozen)
    assert all(digest(folder / name) == h for name, h in frozen.items())
    for name, src in (("selected_policy.py", "completed_policy.py"),
                      ("offline_lab.py", "offline_lab.py"),
                      ("bridge.py", "lamp_week07/bridge.py"),
                      ("course_model.py", "lamp_week07/course_model.py")):
        assert digest(folder / "source_snapshot" / name) == digest(ROOT / "runtime" / src)
    return len(files)


def table_bytes(data):
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=list(data[0]), lineterminator="\n")
    writer.writeheader()
    for row in data:
        writer.writerow({k: ("N/A" if v is None else v) for k, v in row.items()})
    return out.getvalue().encode("utf-8")


def check_trial(folder, cfg, primary, contract):
    m = read_json(folder / "metrics.json")
    conf = read_json(folder / "config.json")
    inputs = rows(folder / "input_trace.csv")
    cmd = rows(folder / "command_trace.csv")
    events = rows(folder / "events.csv")
    assert set(conf["topics"]) == {t["name"] for t in contract["topics"]} and len(conf["topics"]) == 7
    assert all(conf["topics"][t["name"]][0] == t["type"] for t in contract["topics"])
    assert (conf["config"]["seed"], conf["config"]["duration_s"], conf["config"]["dt_s"],
            conf["config"]["scheduler_delay_s"]) == (m["seed"],22,0.02,0.04)
    assert conf["policy_sha256"] == cfg["matched_controls"]["group_policy_sha256"]
    assert m["condition"] == conf["transport"]["condition"]
    assert len(cmd) == 1101 and all(float(r["time_s"]) == i / 50 for i, r in enumerate(cmd))
    assert set(r["emotion"] for r in cmd) <= STATES
    assert m["state_transitions"] == sum(a["emotion"] != b["emotion"] for a, b in zip(cmd, cmd[1:]))
    for r in cmd:
        assert all(abs(float(r[k])) <= bound + 1e-9 for k, bound in
                   zip(("tilt_rad","extend_rad","nod_rad"),contract["semantic_joint_bounds_rad"]))
        assert all(0 <= float(r[k]) <= 1 for k in ("rgb_r","rgb_g","rgb_b"))
        assert float(r["rgb_a"]) == 1.0
    assert len(inputs) == len({(r["sequence"], r["channel"]) for r in inputs}) == 3303
    assert all(r["topic"] == "/lamp/input/" + r["channel"] for r in inputs)
    counts = Counter(r["status"] for r in inputs)
    ages = [float(r["receipt_time_s"]) - float(r["publish_time_s"]) for r in inputs if r["receipt_time_s"]]
    assert all(r["status"] in ("accepted", "discarded_out_of_order") for r in inputs if r["receipt_time_s"])
    expected_counts = dict(published=len(inputs), received=len(ages), accepted=counts["accepted"],
                           discarded_out_of_order=counts["discarded_out_of_order"], transport_dropped=counts["dropped"],
                           censored_after_trial=counts["censored_after_trial"])
    assert all(m[k] == v for k, v in expected_counts.items())
    assert m["published"] == m["received"] + m["transport_dropped"] + m["censored_after_trial"]
    assert m["received"] == m["accepted"] + m["discarded_out_of_order"]
    assert math.isclose(m["mean_transport_age_s"], mean(ages), abs_tol=1e-12)
    assert math.isclose(m["max_transport_age_s"], max(ages), abs_tol=1e-12)
    faults = [float(r["time_s"]) for r in cmd if r["fault_channels"]]
    invalid_window = sum(11 <= t < 11.14 for t in faults)
    stale_window = sum(12 <= t < 12.26 for t in faults)
    assert len(faults) == m["fault_ticks"] and m["total_ticks"] == len(cmd)
    gates = set(cfg["other_source_input_ids_to_retain"])
    assert {s["input_id"] for s in m["source_outcomes"]} == set(primary) | gates
    primary_rows = []
    for s in m["source_outcomes"]:
        candidates = [e for e in events if (e["input_id"], e["kind"]) == (s["input_id"], s["kind"])]
        onsets = [min((float(e[field]) for e in candidates if e[field]), default=None)
                  for field in ("first_motion_s", "first_rgb_s")]
        latency = None if None in onsets else round(max(onsets) - s["source_time_s"], 8)
        passed = None if latency is None else latency <= cfg["both_command_deadline_s"] + 1e-9
        assert [s["first_motion_s"], s["first_rgb_s"]] == onsets
        assert len(candidates) == s["recognized_count"] and s["both_latency_s"] == latency
        assert s["pass_1s_both"] == passed and s["primary_expected_both"] == (s["input_id"] in primary)
        if s["primary_expected_both"]:
            primary_rows.append(dict(seed=m["seed"], transport=m["condition"], input_id=s["input_id"],
                                     kind=s["kind"], source_s=s["source_time_s"], recognized_count=len(candidates),
                                     first_motion_s=onsets[0], first_rgb_s=onsets[1], both_latency_s=latency,
                                     outcome=("missing" if passed is None else "pass" if passed else "late")))
    assert len(primary_rows) == m["primary_expected_count"] == len(primary) == 7
    primary_rows.sort(key=lambda x: primary.index(x["input_id"]))
    outcomes = Counter(r["outcome"] for r in primary_rows)
    observed = [r["both_latency_s"] for r in primary_rows if r["both_latency_s"] is not None]
    assert outcomes["pass"] == m["primary_pass_1s_both_count"] and outcomes["missing"] == m["primary_missing_both_count"]
    assert median(observed) == m["primary_median_both_latency_s"] and max(observed) == m["primary_max_both_latency_s"]
    record = dict(pair=m["repeat"], seed=m["seed"], transport=m["condition"],
                  profile="ideal" if m["condition"] == "C0" else "stressed", **expected_counts,
                  mean_received_age_s=m["mean_transport_age_s"], max_received_age_s=m["max_transport_age_s"],
                  total_ticks=len(cmd), fault_ticks=len(faults), baseline_invalid_window_fault_ticks=invalid_window,
                  baseline_stale_window_fault_ticks=stale_window, outside_probe_windows_fault_ticks=len(faults)-invalid_window-stale_window,
                  state_transitions=m["state_transitions"], source_ids_retained=len(m["source_outcomes"]),
                  primary_expected=7, observed_both=len(observed), passed_1s=outcomes["pass"],
                  late_observed=outcomes["late"], missing_both=outcomes["missing"],
                  observed_both_median_s=m["primary_median_both_latency_s"], observed_both_max_s=m["primary_max_both_latency_s"])
    seed_inputs = [tuple(r[k] for k in MATCH) for r in inputs]
    return record, primary_rows, seed_inputs


def calculate():
    cfg = read_json(ROOT / "preregistered_protocol.json")
    provenance = read_json(ROOT / "source_provenance.json")
    execution = read_json(ROOT / "execution_record.json")
    contract = read_json(ROOT / "runtime/interface_contract.json")
    assert digest(ROOT / "preregistered_protocol.json") == provenance["preregistered_protocol_sha256"] == execution["predeclaration_sha256"]
    assert cfg["primary_expected_input_ids"] == contract["primary_expected_input_ids"]
    assert digest(ROOT / "group_protocol_before_results_TH.md") == "4a2613d297f9f9087cd8faf5b37b9ae0e7e255d4ce3e78deee9d7b160156e961"
    assert all(digest(ROOT / name) == data["sha256"] for name, data in provenance["course_runtime"].items())
    assert digest(ROOT / provenance["group_policy"]["file"]) == provenance["group_policy"]["sha256"]
    assert execution["all_result_directories_were_absent_before_run"] and all(step["returncode"] == 0 for step in execution["steps"])
    assert datetime.fromisoformat(cfg["declared_local"]) < datetime.fromisoformat(execution["steps"][0]["local_started"])
    assert "Checked 40 transition pairs; contract=group; failures=0" in execution["steps"][0]["stdout"]
    manifest_counts = {folder.name:check_manifest(folder) for folder in (RUNS, REPLAY)}
    report, outcomes = [], []
    aggregate = read_json(RUNS / "summary.json")
    for pair in cfg["pairs"]:
        expected_inputs = None
        for cond in pair["conditions"]:
            folder = RUNS / f"{cond}_r{pair['repeat']:02}"
            assert read_json(folder / "metrics.json") == next(r for r in aggregate if r["condition"] == cond and r["seed"] == pair["seed"])
            row, primary_rows, inputs = check_trial(folder, cfg, cfg["primary_expected_input_ids"], contract)
            assert row["pair"] == pair["repeat"] and row["seed"] == pair["seed"]
            if expected_inputs is None:
                expected_inputs = inputs
            else:
                assert inputs == expected_inputs
            report.append(row)
            outcomes.extend(primary_rows)
    original, replay = RUNS / "C1_r02", REPLAY / "C1_r01"
    matches = {}
    for name in cfg["replay_design"]["compare"]:
        assert (original/name).read_bytes() == (replay/name).read_bytes()
        matches[name] = digest(replay/name)
    rr = read_json(replay/"metrics.json")
    ot = read_json(original/"metrics.json")
    assert rr["seed"] == ot["seed"] == 42 and rr["repeat"] == 1 and ot["repeat"] == 2
    assert dict(rr, repeat=2) == ot
    c0, c1 = read_json(original/"config.json"), read_json(replay/"config.json")
    assert dict(c0, replay_trace_sha256=matches["input_trace.csv"]) == c1
    result = dict(group_checker_transition_pairs=40, group_checker_failures=0, matched_source_messages_per_pair=3303,
                  matched_seeds=[41,42,43], official_manifests_verified_file_counts=manifest_counts,
                  retained_source_outcomes=60, preregistered_primary_rows=len(outcomes), replay_condition="C1",
                  replay_seed=42, replay_byte_identical_sha256=matches, replay_metrics_equal_except_repeat_number=True)
    return {"transport_summary.csv":table_bytes(report), "primary_outcomes.csv":table_bytes(outcomes),
            "verification.json":(json.dumps(result, indent=2)+"\n").encode("utf-8")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--create-tables", action="store_true", help="Create derived tables into absent files once.")
    args = parser.parse_args()
    if not __debug__:
        parser.error("Run without -O so validation is active.")
    for name, blob in calculate().items():
        target = ROOT / name
        if args.create_tables:
            with target.open("xb") as stream:
                stream.write(blob)
        elif target.read_bytes() != blob:
            raise ValueError(f"Archived derived output differs: {name}")
    print("Verified 6 trials, 3 matched source streams, 60 source outcomes, 42 primary outcomes and the seed 42 replay.")


if __name__ == "__main__":
    main()

