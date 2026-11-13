"""Read the recorder's SHA-256 identities without importing the Pi runtime."""
import ast
import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath

from .window_quality import review


HARDWARE = Path(__file__).resolve().parents[1] / "hardware"
SHORTCUT = "shared/experiments/presentation_safety_play_20261110"
STUDY = "bio_inspire/experiments/lab07_present_safety_pair1_20261112"
GROUPS = ("own_sha256", "protected_sha256", "dependency_sha256")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(path.read_bytes())


def local_source(name):
    path = PurePosixPath(name)
    if path.is_absolute():
        if path.parent != PurePosixPath("/home/menulis/Desktop"):
            raise ValueError(f"Unrecognized recorded desktop location {name}")
        path = path.relative_to("/")
    if ".." in path.parts or "\\" in name or ":" in name:
        raise ValueError(f"Invalid recorded project path {name}")
    return HARDWARE.joinpath(*path.parts)


def verify_source(reference):
    identity = read_json(reference / "identity.json")
    manifest_path = HARDWARE / SHORTCUT / "manifest.json"
    if digest(manifest_path.read_bytes()) != identity["manifest_sha256"]:
        raise ValueError("Bundled hardware manifest differs from the real recording.")
    manifest = read_json(manifest_path)
    coverage = read_json(HARDWARE / "manifest_coverage.json")
    if coverage["manifest_sha256"] != identity["manifest_sha256"]:
        raise ValueError("Source coverage was recorded against a different manifest.")
    unavailable = {r["path"]: r["sha256"] for r in coverage["unavailable"]}
    verified = 0
    observed_missing = set()
    for group in GROUPS:
        if len(manifest[group]) != identity["verified_groups"][group]:
            raise ValueError(f"Recorded manifest count mismatch in {group}")
        linked = 0
        for name, expected in manifest[group].items():
            path = local_source(name)
            if not path.is_file() and unavailable.get(name) == expected:
                observed_missing.add(name)
                continue
            if not path.is_file() or digest(path.read_bytes()) != expected:
                raise ValueError(f"Hardware source checksum mismatch for {name}")
            verified += 1
            linked += 1
        if coverage["groups"][group] != {"recorded": len(manifest[group]), "present": linked}:
            raise ValueError(f"Source coverage count mismatch in {group}")
    if observed_missing != set(unavailable):
        raise ValueError("Guard-file inventory differs from source snapshot.")
    for name, info in read_json(HARDWARE / "supplemental_sources.json").items():
        if digest(local_source(name).read_bytes()) != info["sha256"]:
            raise ValueError(f"Supplemental source checksum mismatch for {name}")
    return verified, tuple(sorted(observed_missing))


def verify_record(folder, pair, condition):
    identity = read_json(folder / "identity.json")
    summary = read_json(folder / "summary.json")
    protocol = "conditioned_tof_v2" if pair == 1 else "conditioned_tof_v2_portrait"
    if (identity["protocol"], identity["pair"], identity["effective_condition"]) != (protocol, pair, condition):
        raise ValueError(f"Identity mismatch for P{pair}/{condition}")
    paths = {
        "study_sha256": f"{STUDY}/instrument.py",
        "desktop_sha256": "/home/menulis/Desktop/Present Safety.desktop",
        "entry_sha256": f"{SHORTCUT}/present_safety_start.py",
        "launcher_sha256": f"{SHORTCUT}/launch.py",
        "config_sha256": f"{SHORTCUT}/config.json",
        "profile_sha256": f"{SHORTCUT}/profile.json",
        "manifest_sha256": f"{SHORTCUT}/manifest.json",
    }
    if pair > 1:
        paths["portrait_sha256"] = f"{STUDY}/portrait_study.py"
        closed = read_json(folder / "portrait_close.json")
        if not all(closed[k] for k in ("native_cleanup_confirmed", "study_done", "live_face_at_measurement")):
            raise ValueError(f"Missing portrait close evidence for P{pair}/{condition}")
    for key, name in paths.items():
        if digest(local_source(name).read_bytes()) != identity[key]:
            raise ValueError(f"Acquisition source mismatch for {key} in P{pair}/{condition}")
    for key, filename in (("desktop", "shortcut.desktop"), ("config", "shortcut_config.json"),
                          ("profile", "shortcut_profile.json"), ("manifest", "shortcut_manifest.json")):
        if digest((folder / filename).read_bytes()) != identity[f"{key}_sha256"]:
            raise ValueError(f"Recorded {filename} checksum mismatch in P{pair}/{condition}")
    adapter_tree = ast.parse(local_source(paths["study_sha256"]).read_text(encoding="utf-8-sig"))
    blocks = next(node.value for node in adapter_tree.body if isinstance(node, ast.Assign)
                  and any(isinstance(target, ast.Name) and target.id == "BLOCKS" for target in node.targets))
    schedule_bytes = json.dumps(ast.literal_eval(blocks), sort_keys=True).encode()
    if digest(schedule_bytes) != identity["script_sha256"] or json.loads(schedule_bytes) != identity["script"]:
        raise ValueError(f"Scripted input mismatch in P{pair}/{condition}")
    trace = gzip.decompress((folder / "trace.jsonl.gz").read_bytes())
    window = review(summary, trace, protocol)
    if pair > 1:
        window["native_cleanup_confirmed"] = closed["native_cleanup_confirmed"]
    if not window["eligible"] or window != read_json(folder / "window_review.json"):
        raise ValueError(f"180-second acceptance review differs in P{pair}/{condition}")
    tof = gzip.decompress((folder / "tof_frames.jsonl.gz").read_bytes())
    if digest(tof) != summary["tof_frames_sha256"] or len(tof.splitlines()) != summary["tof_published_frames"]:
        raise ValueError(f"Recorded ToF stream mismatch in P{pair}/{condition}")
    return identity, summary, window
