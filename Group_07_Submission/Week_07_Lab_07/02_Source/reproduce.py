"""Rebuild Lab 7 figures and tables from the six archived 180-second lamp records."""
import argparse
import csv
from itertools import zip_longest
import math
from pathlib import Path
from tempfile import TemporaryDirectory

from analysis.hormone_response import (
    CONDITIONS, identity_key, read_csv, study_run, write_csv
)
from analysis.hormone_response_figures import make_figures
from analysis.integrity import digest, read_json, verify_record, verify_source
from analysis.review_pair import decode_record, write_export
from analysis.transition_review import encoder_periods


def run_index_row(pair, condition, audit, identity, summary, window):
    if (audit["invalid_hormone_rows"] or audit["max_phi_model_error"] != 0
            or not audit["PID_readback_equal"] or audit["H_at_gate"] != 0):
        raise ValueError(f"Unmatched controls in P{pair}/{condition}")
    return dict(
        pair=pair, condition=condition, order="C1>C0" if pair == 2 else "C0>C1",
        camera_target="person" if pair == 1 else "displayed portrait",
        duration_s=summary["last_elapsed_s"], raw_rows=summary["written"],
        in_window_phi_rows=audit["verified_phi_rows"], states=len(summary["states"]),
        excluded_input_rows=audit["invalid_hormone_rows"], pid_readback_equal=audit["PID_readback_equal"],
        H_at_start=audit["H_at_gate"], safety_interruptions=len(summary["interruptions"]),
        post_window_handoff=bool(window["boundary_handoff_s"]), trace_sha256=summary["trace_sha256"],
        study_sha256=identity["study_sha256"], manifest_sha256=identity["manifest_sha256"],
        portrait_adapter_sha256=identity.get("portrait_sha256",""), native_log_id=audit["run_id"],
    )


def rebuild(records, destination):
    archive_hashes = read_json(records / "SHA256.json")
    runs, index = [], []
    raw_paths = 0
    for pair in (1, 2, 3):
        pair_name = f"P{pair}"
        pair_output = destination / "real_robot" / pair_name
        pair_edges, pair_events, pair_checks = [], [], []
        identities = {}
        print(f"Processing {pair_name}/C0 and {pair_name}/C1 ...", flush=True)
        for condition in CONDITIONS:
            folder = records / pair_name / condition / "original"
            raw_files = {p.relative_to(records).as_posix(): p for p in folder.iterdir() if p.is_file()}
            expected = {key for key in archive_hashes if key.startswith(f"{pair_name}/{condition}/original/")}
            if not expected or set(raw_files) != expected:
                raise ValueError(f"Original file list differs for {pair_name}/{condition}")
            for key, path in raw_files.items():
                if digest(path.read_bytes()) != archive_hashes[key]:
                    raise ValueError(f"Archive checksum mismatch for {key}")
            raw_paths += len(raw_files)
            identity, summary, window = verify_record(folder, pair, condition)
            edges, events, audit = decode_record(folder, condition, pair_output / condition)
            identities[condition] = identity, summary, audit
            pair_edges.extend(edges)
            pair_events.extend(events)
            pair_checks.append(audit)
            index.append(run_index_row(pair, condition, audit, identity, summary, window))
        write_export(pair_output / "response_edges.csv", pair_edges)
        write_export(pair_output / "FSM_events.csv", pair_events)
        write_export(pair_output / "run_quality.csv", pair_checks)
        # Match the logged export's eight-decimal CSV precision at this boundary.
        events = read_csv(pair_output / "FSM_events.csv")
        for condition, (identity, summary, audit) in identities.items():
            output = pair_output / condition
            controls = read_csv(output / "control.csv")
            joints = read_csv(output / "five_joint_feedback.csv")
            periods = encoder_periods(condition, controls, joints, events)
            run = study_run(records / pair_name / condition / "original", pair, condition,
                            controls, audit, periods, identity, summary, events)
            if pair == 1:
                run["feedback"] = joints
            runs.append(run)
    if len({identity_key(run["id"]) for run in runs}) != 1:
        raise ValueError("Controller or scripted input differs across the three pairs.")
    folder = destination / "real_robot" / "summary"
    folder.mkdir()
    for key, name in (("cycles","CPG_cycles"), ("stats","Worksheet_M1_M2"),
                      ("swings","Happy_dance_cycles"), ("levels","Happy_H_phi_samples")):
        write_csv(folder / f"{name}.csv", [row for run in runs for row in run[key]])
    write_csv(folder / "Run_index.csv", index)
    make_figures(destination, runs)
    print(f"Checked {raw_paths} original files, {sum(row['raw_rows'] for row in index):,} raw rows, "
          f"{sum(row['in_window_phi_rows'] for row in index):,} in-window phi readings.")


def compare_csv(rebuilt, reference):
    """Require matching structure, labels and numeric values across NumPy versions."""
    with rebuilt.open(encoding="utf-8-sig", newline="") as a, reference.open(encoding="utf-8-sig", newline="") as b:
        for number, (left, right) in enumerate(zip_longest(csv.reader(a), csv.reader(b)), 1):
            if left == right:
                continue
            if left is None or right is None or len(left) != len(right):
                raise ValueError(f"{reference}: row count or column count differs at line {number}")
            for column, (u, v) in enumerate(zip(left, right), 1):
                if u == v:
                    continue
                try:
                    equal = math.isclose(float(u), float(v), rel_tol=1e-12, abs_tol=1e-12)
                except ValueError:
                    equal = False
                if not equal:
                    raise ValueError(f"{reference}: mismatch at row {number}, column {column}: {u!r} vs {v!r}")


def compare_results(output, reference):
    csvs = sorted(output.glob("real_robot/**/*.csv"))
    figures = sorted((output / "Figures").glob("*.png"))
    if len(csvs) != 33 or len(figures) != 3:
        raise ValueError(f"Expected 33 CSVs and 3 figures, produced {len(csvs)} and {len(figures)}.")
    exact = 0
    for path in csvs:
        expected = reference / path.relative_to(output)
        if digest(path.read_bytes()) == digest(expected.read_bytes()):
            exact += 1
        else:
            compare_csv(path, expected)
    print(f"All {len(csvs)} rebuilt CSVs match the submitted data; {exact} are byte-identical.")
    equal_figs = sum(path.read_bytes() == (reference / path.relative_to(output)).read_bytes() for path in figures)
    print(f"Rebuilt all {len(figures)} figures; {equal_figs} PNGs are byte-identical.")
    if equal_figs != len(figures):
        print("PNG rendering may vary by Matplotlib, FreeType and system fonts. See README.md.")
    return equal_figs


def main():
    if not __debug__:
        raise RuntimeError("Run Python without -O; the study routines use assertions for experimental checks.")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=Path(__file__).resolve().parents[1] / "03_Results",
                        help="submission's 03_Results directory")
    parser.add_argument("--output", type=Path, help="retain the 33 tables and 3 PNGs in this new directory")
    parser.add_argument("--strict-figures", action="store_true", help="require all rendered PNGs to match byte for byte")
    args = parser.parse_args()
    results = args.results.resolve()
    output = args.output.resolve() if args.output else None
    if output and output.exists():
        parser.error(f"--output must name a new directory. Already exists: {output}")
    if output and (output == results or results in output.parents):
        parser.error("--output must be outside the submitted results.")
    records = results / "real_robot"
    verified, missing = verify_source(records / "P1/C0/original")
    print(f"Verified {verified}/240 launch-manifest entries against the archived hardware sources.")
    if missing:
        print(f"{len(missing)} original guard files are listed in hardware/manifest_coverage.json.")
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="lab07-", dir=output.parent if output else None) as scratch:
        generated = Path(scratch) / "reproduced"
        generated.mkdir()
        rebuild(records, generated)
        equal_figs = compare_results(generated, results)
        if args.strict_figures and equal_figs != 3:
            raise ValueError("Rendered figures differ in strict mode.")
        if output:
            generated.rename(output)
            print(f"Saved to {output}")


if __name__ == "__main__":
    main()
