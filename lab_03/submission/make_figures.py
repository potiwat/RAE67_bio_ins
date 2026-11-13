"""Analysis and figures for Lab 03, built only from the raw CSVs in this folder.

Run from lab_03/:  python submission/make_figures.py

1. Checks that student_cpg.py reproduces the reference run sample by sample
   (so2_step against the o1/o2 columns, decode_tripod against lift/contact).
2. Computes the extra quantities the report quotes (amplitude, rotation per
   step, period in steps, tripod phase relation, bridge transients).
3. Draws the figures into submission/figures/.

Nothing here changes a raw CSV.
"""

from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

HERE = Path(__file__).resolve().parent
LAB = HERE.parent
sys.path.insert(0, str(LAB))
import student_cpg  # noqa: E402
from cpg_walk_sim import LEGS, rising_crossings  # noqa: E402

GAIT = HERE / "gait_comparison"
BRIDGE = HERE / "week4_bridge"
OUT = HERE / "figures"
DT = 0.05
NAMES = ("baseline", "fast", "high_gain")
COND_COLOUR = {"baseline": "#2a78d6", "fast": "#eb6834", "high_gain": "#1baf7a"}
INK, MUTED, GRID = "#161616", "#6b6b6b", "#e4e4e4"
TRIPOD_A, TRIPOD_B = ("LF", "RM", "LH"), ("RF", "LM", "RH")

plt.rcParams.update({
    "font.size": 9, "axes.edgecolor": MUTED, "axes.labelcolor": INK,
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.grid": True,
    "grid.color": GRID, "grid.linewidth": 0.6, "axes.spines.top": False,
    "axes.spines.right": False, "legend.frameon": False, "axes.axisbelow": True,
})


def load(path: Path) -> list[dict[str, float]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return [{k: float(v) for k, v in row.items()} for row in csv.DictReader(handle)]


def col(rows, key):
    return [r[key] for r in rows]


# ---------------------------------------------------------------- analysis
def verify_student(rows, alpha, phi_of, stride_of, lift_height=0.030):
    """Max |difference| between student functions and the reference CSV."""
    d_cpg = d_lift = 0.0
    contact_mismatch = 0
    for k, r in enumerate(rows):
        if k + 1 < len(rows):
            o1n, o2n = student_cpg.so2_step(r["o1"], r["o2"], alpha, phi_of(r))
            d_cpg = max(d_cpg, abs(o1n - rows[k + 1]["o1"]), abs(o2n - rows[k + 1]["o2"]))
        state = student_cpg.decode_tripod(r["o1"], r["o2"], stride_of(r), lift_height)
        for leg in LEGS:
            d_lift = max(d_lift, abs(state[leg]["lift"] - r[f"{leg}_lift_m"]))
            contact_mismatch += int(bool(state[leg]["contact"]) != bool(r[f"{leg}_contact"]))
    return {"max_abs_diff_o1_o2": d_cpg, "max_abs_diff_lift_m": d_lift,
            "contact_mismatches": contact_mismatch, "samples": len(rows)}


def rotation_per_step(rows):
    th = [math.atan2(r["o2"], r["o1"]) for r in rows]
    steps = []
    for a, b in zip(th, th[1:]):
        d = a - b                      # the map rotates clockwise in (o1, o2)
        d = (d + math.pi) % (2 * math.pi) - math.pi
        steps.append(d)
    return steps


def gait_analysis(summaries):
    result = {}
    for name in NAMES:
        rows = load(GAIT / f"{name}.csv")
        s = summaries[name]
        o1, o2 = col(rows, "o1"), col(rows, "o2")
        cross = rising_crossings(o1)
        periods = [cross[i] - cross[i - 1] for i in range(1, len(cross))]
        rot = rotation_per_step(rows)
        a_contact = [all(r[f"{l}_contact"] for l in TRIPOD_A) for r in rows]
        b_contact = [all(r[f"{l}_contact"] for l in TRIPOD_B) for r in rows]
        a_same = all(len({r[f"{l}_contact"] for l in TRIPOD_A}) == 1 for r in rows)
        b_same = all(len({r[f"{l}_contact"] for l in TRIPOD_B}) == 1 for r in rows)
        complementary = sum(a != b for a, b in zip(a_contact, b_contact))
        hip_sum = max(abs(r["LF_hip_rad"] + r["RF_hip_rad"]) for r in rows)
        result[name] = {
            "alpha": s["alpha"], "phi_rad": s["phi_rad"],
            "amplitude_o1_max": max(o1), "amplitude_o1_min": min(o1),
            "amplitude_o2_max": max(o2),
            "mean_rotation_per_step_rad": sum(rot) / len(rot),
            "min_rotation_per_step_rad": min(rot), "max_rotation_per_step_rad": max(rot),
            "predicted_period_s_from_phi": 2 * math.pi / s["phi_rad"] * DT,
            "period_steps_list": periods,
            "mean_period_s": sum(periods) / len(periods) * DT,
            "distance_per_cycle_m": s["distance_m"] / (s["duration_s"] * s["oscillation_frequency_hz"]),
            "tripod_A_legs_identical_contact": a_same,
            "tripod_B_legs_identical_contact": b_same,
            "samples_A_and_B_complementary": complementary,
            "samples": len(rows),
            "max_abs_LF_hip_plus_RF_hip_rad": hip_sum,
            "student_vs_reference": verify_student(
                rows, s["alpha"], lambda r, p=s["phi_rad"]: p, lambda r: 0.055),
        }
    return result


def bridge_analysis():
    rows = load(BRIDGE / "week4_bridge.csv")
    o1 = col(rows, "o1")
    cross = rising_crossings(o1)
    cycles = [{"start_s": round(cross[i - 1] * DT, 2), "end_s": round(cross[i] * DT, 2),
               "period_s": round((cross[i] - cross[i - 1]) * DT, 3)}
              for i in range(1, len(cross))]
    x = col(rows, "body_x_m")
    dx = [b - a for a, b in zip(x, x[1:])]
    jumps = {}
    for t_switch in (10.0, 20.0):
        k = round(t_switch / DT)
        jumps[f"t={t_switch:.0f}s"] = {
            "body_dx_at_switch_m": dx[k - 1],
            "body_dx_previous_step_m": dx[k - 2],
            "body_dx_next_step_m": dx[k],
            "o1_at_switch": o1[k],
            "phi_before": rows[k - 1]["phi_rad"], "phi_after": rows[k]["phi_rad"],
        }
    amp = {}
    for a, b in ((0, 10), (10, 20), (20, 30)):
        seg = [r["o1"] for r in rows if a <= r["time_s"] < b]
        amp[f"{a}-{b}s"] = {"o1_max": max(seg), "o1_min": min(seg)}
    return {
        "cycles": cycles, "switch_steps": jumps, "o1_range_per_segment": amp,
        "min_support_legs": min(col(rows, "support_legs")),
        "max_support_legs": max(col(rows, "support_legs")),
        "student_vs_reference": verify_student(
            rows, 1.10, lambda r: r["phi_rad"], lambda r: r["stride_half_m"]),
        "student_bounded_modulation": {
            str(m): student_cpg.bounded_modulation(m) for m in (-99.0, -1.0, 0.0, 1.0, 1.25, 2.0, 99.0)},
    }


# ---------------------------------------------------------------- figures
def fig_gait(data):
    """o1/o2 and gait diagram, one column per condition (shared time window)."""
    t0, t1 = 0.0, 5.0
    fig, axes = plt.subplots(2, 3, figsize=(10, 4.6), sharex=True,
                             gridspec_kw={"height_ratios": [1.3, 1]})
    for j, name in enumerate(NAMES):
        rows = [r for r in data[name] if t0 <= r["time_s"] <= t1]
        t = col(rows, "time_s")
        ax = axes[0, j]
        ax.plot(t, col(rows, "o1"), color=INK, lw=1.6, label="o₁")
        ax.plot(t, col(rows, "o2"), color=MUTED, lw=1.6, ls="--", label="o₂")
        ax.axhline(0, color=MUTED, lw=0.6)
        ax.set_ylim(-1.0, 1.0)
        a = data["_summary"][name]
        ax.set_title(f"{name}  (α = {a['alpha']:.2f}, φ = {a['phi_rad']:.2f} rad)\n"
                     f"f = {a['oscillation_frequency_hz']:.3f} Hz, clearance = "
                     f"{a['maximum_foot_clearance_m'] * 1000:.1f} mm",
                     fontsize=9, color=COND_COLOUR[name])
        if j == 0:
            ax.set_ylabel("CPG output")
            ax.legend(loc="lower left", ncol=2, fontsize=8)
        ax = axes[1, j]
        for i, leg in enumerate(LEGS):
            y = len(LEGS) - 1 - i
            on = [r[f"{leg}_contact"] for r in rows]
            start = None
            for k, v in enumerate(on + [0.0]):
                if v and start is None:
                    start = k
                if not v and start is not None:
                    ax.barh(y, t[k - 1] - t[start] + DT, left=t[start], height=0.7,
                            color=INK if leg in TRIPOD_A else MUTED, linewidth=0)
                    start = None
        ax.set_yticks(range(len(LEGS)))
        ax.set_yticklabels(list(reversed(LEGS)))
        ax.grid(axis="y", visible=False)
        ax.set_xlabel("time after warmup (s)")
        if j == 0:
            ax.set_ylabel("stance (bar)\nA = dark, B = gray")
    fig.suptitle("SO(2) CPG output and alternating tripod contact (first 5 s of 30 s)", fontsize=10)
    fig.tight_layout()
    fig.savefig(OUT / "fig1_gait_three_conditions.png", dpi=200)
    plt.close(fig)


def fig_phase(data):
    fig, ax = plt.subplots(figsize=(4.4, 4.2))
    style = {"fast": dict(lw=2.6, ms=0), "baseline": dict(lw=0, ms=3.2),
             "high_gain": dict(lw=1.4, ms=2.2)}
    for name in ("fast", "baseline", "high_gain"):
        rows = data[name]
        ax.plot(col(rows, "o1"), col(rows, "o2"), color=COND_COLOUR[name], marker="o",
                label=name, **style[name])
    ax.set_aspect("equal")
    ax.set_xlabel("o₁")
    ax.set_ylabel("o₂")
    ax.set_xlim(-0.95, 0.95)
    ax.set_ylim(-0.95, 0.95)
    ax.legend(loc="center", fontsize=8)
    ax.set_title("Limit cycle in (o₁, o₂); baseline = dots (samples),\nfast = line (same cycle), high_gain = larger, squarer", fontsize=9)
    fig.tight_layout()
    fig.savefig(OUT / "fig2_phase_portrait.png", dpi=200)
    plt.close(fig)


def fig_metrics(summary):
    metrics = [("oscillation_frequency_hz", "frequency (Hz)", 1),
               ("mean_speed_m_s", "mean speed (m/s)", 1),
               ("maximum_foot_clearance_m", "max clearance (mm)", 1000),
               ("duty_factor_LF", "duty factor LF", 1)]
    fig, axes = plt.subplots(1, 4, figsize=(10, 2.6))
    for ax, (key, label, scale) in zip(axes, metrics):
        vals = [summary[n][key] * scale for n in NAMES]
        ax.bar(range(3), vals, color=[COND_COLOUR[n] for n in NAMES], width=0.62)
        for i, v in enumerate(vals):
            ax.text(i, v, f"{v:.3g}", ha="center", va="bottom", fontsize=8, color=INK)
        ax.set_xticks(range(3))
        ax.set_xticklabels(NAMES, fontsize=8)
        ax.set_title(label, fontsize=9)
        ax.grid(axis="x", visible=False)
        ax.set_ylim(0, max(vals) * 1.2)
    fig.suptitle("Gait comparison (conditions_summary.csv; only one parameter changed per condition)", fontsize=10)
    fig.tight_layout()
    fig.savefig(OUT / "fig3_metrics.png", dpi=200)
    plt.close(fig)


def fig_bridge(rows, bridge):
    t = col(rows, "time_s")
    fig, axes = plt.subplots(4, 1, figsize=(9, 6.6), sharex=True,
                             gridspec_kw={"height_ratios": [0.8, 1, 1.2, 1]})
    ax = axes[0]
    ax.step(t, col(rows, "modulator_m"), where="post", color=INK, lw=1.6)
    ax.set_ylabel("m(t)")
    ax.set_ylim(-0.2, 1.3)
    ax = axes[1]
    ax.step(t, col(rows, "phi_rad"), where="post", color=INK, lw=1.6, label="φ_cmd (rad)")
    ax.step(t, [s * 10 for s in col(rows, "stride_half_m")], where="post", color=MUTED,
            lw=1.6, ls="--", label="stride_cmd × 10 (m)")
    for b in (0.10, 0.45):
        ax.axhline(b, color="#b84a4a", lw=0.8, ls=":")
        ax.text(29.8, b + 0.012, f"φ bound {b:.2f}", fontsize=7, color="#b84a4a", ha="right")
    ax.set_ylabel("command")
    ax.legend(loc="center left", fontsize=8, ncol=2, bbox_to_anchor=(0.0, 0.62))
    ax = axes[2]
    ax.plot(t, col(rows, "o1"), color=INK, lw=1.0)
    ax.set_ylabel("o₁")
    ax2 = axes[3]
    cyc = bridge["cycles"]
    ax2.plot([(c["start_s"] + c["end_s"]) / 2 for c in cyc], [1 / c["period_s"] for c in cyc],
             color=INK, marker="o", ms=4, lw=1.2, label="1 / period of each o₁ cycle (Hz)")
    ax2.set_ylabel("cycle freq (Hz)")
    ax2.set_xlabel("time (s)")
    ax2.legend(loc="upper left", fontsize=8)
    for a in axes:
        for ts in (10, 20):
            a.axvline(ts, color=MUTED, lw=0.8, ls=":")
    segs = json.loads((BRIDGE / "handoff_contract.json").read_text(encoding="utf-8"))["segments"]
    fig.suptitle("Week 4 bridge: manual m(t) → bounded mapping → CPG.  Segment speed "
                 + " / ".join(f"{s['mean_speed_m_s']:.3f}" for s in segs) + " m/s", fontsize=10)
    fig.tight_layout()
    fig.savefig(OUT / "fig4_week4_bridge.png", dpi=200)
    plt.close(fig)


def _box(ax, x, y, w, h, text, fc="#ffffff", ec=INK, fs=8.5):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.05",
                                fc=fc, ec=ec, lw=1.2))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, linespacing=1.35)


def _arrow(ax, p, q, label=None, dy=0.12):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=12, lw=1.2, color=INK))
    if label:
        ax.text((p[0] + q[0]) / 2, (p[1] + q[1]) / 2 + dy, label, ha="center", fontsize=7.5, color=MUTED)


def fig_block():
    fig, ax = plt.subplots(figsize=(11, 2.8))
    ax.set_xlim(0, 12.4)
    ax.set_ylim(0, 2.8)
    ax.axis("off")
    _box(ax, 0.1, 1.0, 1.6, 0.9, "slow input m(t)\nWeek 3: manual\nWeek 4: hormone", fc="#f3f3f3")
    _box(ax, 2.3, 1.0, 2.9, 0.9, "bounded mapping\nφ = clamp(0.20+0.20m, 0.10, 0.45)\n"
         "stride = clamp(0.055+0.010m, 0.040, 0.070)", fs=7.5)
    _box(ax, 5.8, 1.0, 1.8, 0.9, "SO(2) CPG\nα fixed = 1.10\nsimultaneous update")
    _box(ax, 8.2, 1.0, 1.8, 0.9, "tripod decoder\nA: LF RM LH (+)\nB: RF LM RH (−)")
    _box(ax, 10.6, 1.0, 1.7, 0.9, "kinematic body\nbody x = mean of\nstance constraints", fc="#f3f3f3")
    _arrow(ax, (1.7, 1.45), (2.3, 1.45), "m")
    _arrow(ax, (5.2, 1.45), (5.8, 1.45), "φ")
    _arrow(ax, (7.6, 1.45), (8.2, 1.45), "o₁, o₂")
    _arrow(ax, (10.0, 1.45), (10.6, 1.45))
    ax.text(10.3, 2.05, "x_rel, lift, contact", ha="center", fontsize=7.5, color=MUTED)
    ax.add_patch(FancyArrowPatch((4.6, 1.0), (9.0, 1.0), connectionstyle="arc3,rad=0.25",
                                 arrowstyle="-|>", mutation_scale=12, lw=1.0, color=MUTED, ls="--"))
    ax.text(6.8, 0.2, "stride_cmd → decoder (a gait parameter, not a motor command)", ha="center", fontsize=7.5, color=MUTED)
    ax.text(6.2, 2.5, "Open loop: no feedback from the body to the CPG in this kinematic model",
            ha="center", fontsize=8, color=INK)
    fig.tight_layout()
    fig.savefig(OUT / "block_diagram.png", dpi=200)
    plt.close(fig)


def main():
    OUT.mkdir(exist_ok=True)
    summary = {}
    with (GAIT / "conditions_summary.csv").open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            summary[r["condition"]] = {k: (v if k in ("condition", "model_scope") else float(v))
                                       for k, v in r.items()}
    gait = gait_analysis(summary)
    bridge = bridge_analysis()
    (HERE / "analysis.json").write_text(json.dumps({"gait": gait, "week4_bridge": bridge},
                                                   ensure_ascii=False, indent=2), encoding="utf-8")
    data = {n: load(GAIT / f"{n}.csv") for n in NAMES}
    data["_summary"] = summary
    fig_gait(data)
    fig_phase(data)
    fig_metrics(summary)
    fig_bridge(load(BRIDGE / "week4_bridge.csv"), bridge)
    fig_block()
    print(json.dumps({n: {k: v for k, v in g.items() if k != "period_steps_list"} for n, g in gait.items()},
                     ensure_ascii=False, indent=1))
    print(json.dumps({k: v for k, v in bridge.items() if k != "cycles"}, ensure_ascii=False, indent=1))
    print(bridge["cycles"])
    print({n: g["period_steps_list"] for n, g in gait.items()})


if __name__ == "__main__":
    main()
