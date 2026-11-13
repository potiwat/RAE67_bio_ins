"""Deterministic 180 s LampBio-Inpire AHM–CPG replay. Python standard library only."""
from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import io
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import NamedTuple

HERE = Path(__file__).resolve().parent
DT = 0.05
DURATION = 180
STEPS = 3600
ALPHA = 1.1
HAPPY_LOW = 0.11798049926757813
PHI_HIGH = 0.13
SCALES = {"body": 0.5, "happy": 3.402 / 3.8, "afraid": 0.5}
STATES = ("normal", "interested", "happy", "angry", "afraid", "sleepy")
BANK = {s: (s if s in ("happy", "afraid") else "body") for s in STATES}
MASKED_ROUTES = {"look", "return", "lean", "tilt"}
BLOCKS = {
    "button": ((320, 480),),
    "touch": ((840, 1180), (1560, 1564), (1568, 1572), (1576, 1580)),
    "near": ((2160, 2720),),
}


def stimulus(k):
    return tuple(int(any(a <= k < b for a, b in spans)) for spans in BLOCKS.values())


def hormone_step(h, s):
    return min(1.0, max(0.0, h + DT * (0.8 * s - 0.6 * h - 0.2 * h)))


def oscillator_step(o1, o2, phi):
    c, s = math.cos(phi), math.sin(phi)
    return math.tanh(ALPHA * (c * o1 + s * o2)), math.tanh(ALPHA * (-s * o1 + c * o2))


class Context(NamedTuple):
    fsm: str
    behavior: str
    bank: str
    route: str
    full_envelope: bool
    episode: int


class Timeline(NamedTuple):
    times: list
    contexts: list

    def at(self, t):
        return self.contexts[bisect.bisect_right(self.times, t) - 1]


def load_pair(robot_data, pair, manifest):
    prefix = f"P{pair}/C0/"
    digests = {}

    def verified_bytes(name):
        key = prefix + name
        raw = (robot_data / key).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != manifest[key]:
            raise ValueError(f"Input checksum differs from real_robot/SHA256.json: {key}")
        digests[key] = digest
        return raw

    ident = json.loads(verified_bytes("original/identity.json"))
    summary = json.loads(verified_bytes("original/summary.json"))
    window = json.loads(verified_bytes("original/window_review.json"))
    profile = json.loads(verified_bytes("original/shortcut_profile.json"))
    expected_script = {ch: [[a / 20, b / 20] for a, b in spans] for ch, spans in BLOCKS.items()}
    assert ident["pair"] == pair and ident["effective_condition"] == "C0"
    assert ident["protocol"] == ("conditioned_tof_v2" if pair == 1 else "conditioned_tof_v2_portrait")
    assert ident["script"] == expected_script
    assert (ident["happy_phi_low"], ident["happy_phi_high"]) == (HAPPY_LOW, PHI_HIGH)
    assert profile["cpg_time_scale"] == 0.5 and profile["small_happy_expanded_trial"]
    assert profile["happy_taught_fast_period_s"] == 3.8 and profile["ahm_scope"] == "all_states"
    assert window["eligible"] and window["analysis_window_s"] == [0, 180]
    assert summary["complete"] and summary["dropped"] == 0 and not summary["aborted"]
    seed = summary["seed_at_start"]
    assert seed["h"] == 0 and seed["r_condition"] == "C0" and seed["driver"] == "AcceptedRhythms"
    assert set(seed["banks"]) == set(SCALES)

    # Retain only labels and the binary full-output mask. No post-start oscillator,
    # stimulus, hormone, encoder, camera or other response series feeds the model.
    controls = verified_bytes("control.csv").decode("utf-8-sig")
    times = [0.0]
    contexts = [Context("normal", "normal", "body", "pre_observation", False, 0)]
    previous_t, episode_id, n_rows = 0.0, 0, 0
    for row in csv.DictReader(io.StringIO(controls)):
        t = float(row["t"])
        assert 0 <= t < DURATION and 0 <= t - previous_t <= 0.30
        assert n_rows == 0 or t > previous_t
        assert row["valid"] == "1" and row["reason"] == "tracking"
        state, behavior, bank, route = (row[k] for k in ("fsm", "behavior", "selected", "route"))
        assert state in STATES and bank in SCALES
        full = float(row[bank + "_envelope"]) >= 1.0 - 1e-9
        active = state == behavior and bank == BANK[state] and route not in MASKED_ROUTES and full
        old = contexts[-1]
        if active and (not old.episode or (state, bank) != (old.fsm, old.bank)):
            episode_id += 1
        context = Context(state, behavior, bank, route, full, episode_id if active else 0)
        if context != old:
            times.append(t)
            contexts.append(context)
        previous_t = t
        n_rows += 1
    assert n_rows and DURATION - previous_t <= 0.30
    assert {c.fsm for c in contexts} == set(STATES)
    metadata = dict(pair=pair, seed_origin=prefix + "original/summary.json#seed_at_start",
                    H0=seed["h"], bank_seeds=seed["banks"], protocol=ident["protocol"],
                    C0_context_rows=n_rows, input_sha256=digests)
    return Timeline(times, contexts), metadata


def episode_rows(pair, timeline):
    episodes = {}
    for i, c in enumerate(timeline.contexts):
        if not c.episode:
            continue
        end = timeline.times[i + 1] if i + 1 < len(timeline.times) else DURATION
        if c.episode not in episodes:
            episodes[c.episode] = dict(pair=pair, episode=c.episode, state=c.fsm, bank=c.bank,
                                       start_s=timeline.times[i], end_s=end)
        episodes[c.episode]["end_s"] = end
    return list(episodes.values())


def complete_cycles(pair, condition, nodes):
    result = []
    for (state, bank, episode), samples in sorted(nodes.items(), key=lambda item: item[0][2]):
        crossings = []
        for i, ((t0, a), (t1, b)) in enumerate(zip(samples, samples[1:])):
            assert t1 > t0
            if a < 0 <= b:
                crossings.append(t0 + (t1 - t0) * (-a) / (b - a))
            elif i == 0 and a == 0 and b > 0:
                crossings.append(t0)
        previous = None
        for start, end in zip(crossings, crossings[1:]):
            period = end - start
            result.append(dict(pair=pair, condition=condition, state=state, bank=bank,
                               episode=episode, start_s=start, end_s=end, T_s=period,
                               frequency_Hz=1.0 / period,
                               delta_T_s=None if previous is None else abs(period - previous)))
            previous = period
    return result


def state_metrics(pair, condition, cycles):
    result = []
    for state in STATES:
        state_cycles = [c for c in cycles if c["state"] == state]
        periods = [c["T_s"] for c in state_cycles]
        deltas = [c["delta_T_s"] for c in state_cycles if c["delta_T_s"] is not None]
        result.append(dict(pair=pair, condition=condition, state=state, complete_cycles=len(periods),
                           adjacent_pairs=len(deltas), M1_Hz=(1.0 / mean(periods) if periods else None),
                           M2_s=(mean(deltas) if deltas else None)))
    return result


def simulate(pair, condition, timeline, seeds):
    assert condition in ("C0", "C1")
    # Phase is carried continuously. Unknown sub-tick offsets at t=0 are set
    # to zero in both members. The integer count below is since simulation start.
    states = {bank: (values[0], values[1]) for bank, values in seeds.items()}
    count = dict.fromkeys(SCALES, 0)
    previous_phi = dict.fromkeys(SCALES, 0.10)
    h = 0.0
    trace, nodes = [], defaultdict(list)
    for k in range(STEPS + 1):
        t = k / 20
        ctx = timeline.at(t)
        for bank, scale in SCALES.items():
            due = math.floor(k * scale + 1e-10)
            if due != count[bank]:
                assert due == count[bank] + 1
                states[bank] = oscillator_step(*states[bank], previous_phi[bank])
                count[bank] = due
                # The worksheet timestamps crossing nodes on the bank's nominal
                # output clock (model update * .05 / scale), not on the polling clock.
                node_t = due * DT / scale
                at_node = timeline.at(node_t)
                if node_t < DURATION and at_node.episode and at_node.bank == bank:
                    nodes[at_node.fsm, bank, at_node.episode].append((node_t, states[bank][0]))

        row = dict(pair=pair, condition=condition, t_s=t, fsm=ctx.fsm, behavior=ctx.behavior,
                   selected=ctx.bank, route=ctx.route, full_envelope=int(ctx.full_envelope),
                   eligible_episode=ctx.episode, button=None, touch=None, near=None, S=None,
                   H=h, R=None, phi_ordinary=None, phi_happy_bank=None, phi_selected=None)
        if k < STEPS:
            button, touch, near = stimulus(k)
            s = max(button, touch, near)
            drive = float(s) if condition == "C0" else h
            ordinary = 0.10 + 0.03 * drive
            happy = HAPPY_LOW + (PHI_HIGH - HAPPY_LOW) * drive if ctx.behavior == "happy" else ordinary
            previous_phi = {"body": ordinary, "happy": happy, "afraid": ordinary}
            row.update(button=button, touch=touch, near=near, S=s, R=drive, phi_ordinary=ordinary,
                       phi_happy_bank=happy, phi_selected=previous_phi[ctx.bank])
            h = hormone_step(h, s)
        for bank, scale in SCALES.items():
            row[bank + "_step"] = count[bank]
            row[bank + "_node_s"] = count[bank] * DT / scale
            row[bank + "_o1"], row[bank + "_o2"] = states[bank]
        trace.append(row)
    return trace, complete_cycles(pair, condition, nodes)


def check_pair(traces, cycle_groups, episodes, seeds):
    direct, filtered = traces
    assert len(direct) == len(filtered) == STEPS + 1 and direct[-1]["t_s"] == DURATION
    for name, values in seeds.items():
        for run in traces:
            assert (run[0][name + "_o1"], run[0][name + "_o2"]) == tuple(values[:2])
    assert direct[0]["H"] == filtered[0]["H"] == 0.0
    match = ("t_s", "fsm", "behavior", "selected", "route", "full_envelope", "eligible_episode",
             "button", "touch", "near", "S", "H", *(b + "_step" for b in SCALES))
    for a, b in zip(direct[:-1], filtered[:-1]):
        assert all(a[field] == b[field] for field in match)
        assert a["R"] == a["S"] and b["R"] == b["H"] and 0 <= b["R"] <= 1
        for row in (a, b):
            assert 0.1 <= row["phi_selected"] <= PHI_HIGH
            if row["behavior"] == "happy":
                assert HAPPY_LOW <= row["phi_happy_bank"] <= PHI_HIGH
    assert [sum(row[ch] for row in direct[:-1]) for ch in BLOCKS] == [160, 352, 560]
    assert direct[1180]["S"] == 0 and direct[1180]["R"] == 0
    assert filtered[1180]["behavior"] == "happy" and filtered[1180]["H"] > .99
    assert math.isclose(filtered[1200]["H"], filtered[1180]["H"] * 0.96**20, abs_tol=1e-12)
    for run in traces:
        assert run[-1]["S"] is None and run[-1]["phi_selected"] is None
    limits = {e["episode"]: e for e in episodes}
    for cycles in cycle_groups:
        for c in cycles:
            e = limits[c["episode"]]
            assert c["state"] == e["state"] and e["start_s"] <= c["start_s"] < c["end_s"] <= e["end_s"]


def csv_bytes(rows):
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: ("N/A" if v is None else format(v, ".12g") if isinstance(v, float) else v)
                         for k, v in row.items()})
    return out.getvalue().encode("utf-8")


def calculate(robot_data):
    manifest = json.loads((robot_data / "SHA256.json").read_bytes())
    files = {}
    cycles, metrics, all_episodes, metadata = [], [], [], []
    for pair in range(1, 4):
        timeline, source = load_pair(robot_data, pair, manifest)
        seeds = source["bank_seeds"]
        metadata.append(source)
        episodes = episode_rows(pair, timeline)
        all_episodes.extend(episodes)
        traces, cycle_groups = [], []
        for condition in ("C0", "C1"):
            trace, trial_cycles = simulate(pair, condition, timeline, seeds)
            traces.append(trace)
            cycle_groups.append(trial_cycles)
            files[f"traces/P{pair}_{condition}.csv"] = csv_bytes(trace)
            cycles.extend(trial_cycles)
            metrics.extend(state_metrics(pair, condition, trial_cycles))
        check_pair(traces, cycle_groups, episodes, seeds)
    files["CPG_cycles.csv"] = csv_bytes(cycles)
    files["Worksheet_M1_M2.csv"] = csv_bytes(metrics)
    files["C0_context_episodes.csv"] = csv_bytes(all_episodes)
    provenance = dict(mode="offline_recorded_context_replay", duration_s=DURATION, dt_s=DT,
                      SO2_alpha=ALPHA, bank_clock_scales=SCALES, phi_happy_low=HAPPY_LOW,
                      phi_happy_high=PHI_HIGH, pairs=metadata)
    files["simulation_inputs.json"] = (json.dumps(provenance, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    return files, metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=HERE.parent / "real_robot",
                        help="Extracted 03_Results/real_robot containing P1, P2, P3 and SHA256.json")
    parser.add_argument("--output", type=Path, default=HERE, help="Where to write or verify simulation files")
    parser.add_argument("--verify", action="store_true", help="Recalculate into memory and compare with stored results")
    options = parser.parse_args()
    if not __debug__:
        parser.error("Run Python without -O to keep the experimental assertions active")
    files, metrics = calculate(options.data)
    for name, content in files.items():
        path = options.output / name
        if options.verify:
            if not path.is_file() or path.read_bytes() != content:
                raise ValueError(f"Stored output differs: {name}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    print(("Verified" if options.verify else "Wrote"), len(files), "simulation files; 6 traces, 180 s each.")
    for m in metrics:
        if m["state"] == "happy":
            print(f"P{m['pair']} {m['condition']} Happy: n={m['complete_cycles']}, "
                  f"adj={m['adjacent_pairs']}, M1={m['M1_Hz']:.7f} Hz, M2={m['M2_s']:.7f} s")


if __name__ == "__main__":
    main()

