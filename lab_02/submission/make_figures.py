"""Build every Lab 02 figure from the raw trial CSVs in this folder.

Run from lab_02/:  python submission/make_figures.py

Crossing and first-correct-response times come from the same helpers that
lab02.py uses for summary_trials.csv, so the markers match the metrics.
No raw CSV is modified.
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
sys.path.insert(0, str(HERE.parent))
from lab02 import LabConfig, _crossing_time, _first_correct_latency  # noqa: E402

OUT = HERE / "figures"
CFG = LabConfig()

# Validated categorical order (same as Lab03-05): one hue per controller.
COND_COLOUR = {"C0": "#2a78d6", "C1": "#eb6834", "C2": "#1baf7a", "C3": "#eda100"}
INK, MUTED, GRID = "#1f2328", "#6e7781", "#d0d7de"
RAW = "#9aa3ab"
FILT = "#2a78d6"

plt.rcParams.update({
    "font.size": 9, "axes.edgecolor": MUTED, "axes.labelcolor": INK,
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False,
    "axes.spines.right": False, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.6, "legend.frameon": False, "lines.linewidth": 2,
})


def load(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def num(value: str) -> float:
    return math.nan if value == "" else float(value)


def events(rows):
    out = {}
    for kind, direction, state in (("enter", "down", "NEAR"), ("exit", "up", "FAR")):
        cross = _crossing_time(rows, direction, CFG.threshold_m)
        lat = _first_correct_latency(rows, cross, state)
        out[kind] = (cross, lat, None if lat is None else cross + lat)
    return out


def mark(ax, ev, legend):
    for kind, ls in (("enter", "-"), ("exit", "-")):
        cross, _, resp = ev[kind]
        ax.axvline(cross, color=INK, ls="--", lw=1.1,
                   label="physical crossing of 0.35 m" if legend and kind == "enter" else None)
        if resp is not None:
            ax.axvline(resp, color="#8250df", ls=ls, lw=1.5,
                       label="first correct response" if legend and kind == "enter" else None)


def trial_figure(csv_path: Path, out_path: Path) -> None:
    rows = load(csv_path)
    cond = rows[0]["condition"]
    ev = events(rows)
    t = [float(r["time_s"]) for r in rows]
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 5.6), sharex=True, constrained_layout=True,
                                   gridspec_kw={"height_ratios": [2.2, 1]})
    ax1.plot(t, [num(r["raw_distance_m"]) for r in rows], color=RAW, lw=1, label="raw (sensor)")
    ax1.plot(t, [float(r["true_distance_m"]) for r in rows], color=INK, lw=2, label="true distance")
    if cond != "C1":
        ax1.plot(t, [num(r["filtered_distance_m"]) for r in rows], color=FILT, lw=1.6, label="filtered (beta 0.25)")
    ax1.axhline(CFG.threshold_m, color=MUTED, ls=":", lw=1.3, label="T = 0.35 m")
    if cond == "C2":
        for y, name in ((CFG.enter_threshold_m, "T_enter 0.32"), (CFG.exit_threshold_m, "T_exit 0.38")):
            ax1.axhline(y, color=COND_COLOUR["C2"], ls=":", lw=1.1)
            ax1.text(19.9, y + 0.004, name, ha="right", va="bottom", fontsize=7.5, color=INK)
    mark(ax1, ev, legend=True)
    ax1.set_ylabel("distance (m)")
    ax1.set_ylim(0.18, 0.80)
    ax1.legend(loc="lower left", ncol=2, fontsize=8)

    ax2.step(t, [1 if r["state"] == "NEAR" else 0 for r in rows], where="post",
             color=COND_COLOUR[cond], lw=1.6)
    mark(ax2, ev, legend=False)
    ax2.set_yticks([0, 1], ["FAR", "NEAR"])
    ax2.set_ylim(-0.15, 1.15)
    ax2.set_xlabel("time (s)")
    ax2.set_ylabel(f"{cond} state")
    switches = sum(1 for r in rows if r["event_label"] in ("ENTER_NEAR", "EXIT_NEAR"))
    fmt = lambda v: "n/a" if v is None else f"{v:.3f} s"  # noqa: E731
    fig.suptitle(f"{rows[0]['trial_id']}: sigma {rows[0]['noise_sigma_m']} m, delay {rows[0]['delay_ms']} ms  |  "
                 f"latency enter {fmt(ev['enter'][1])}, exit {fmt(ev['exit'][1])}  |  switches {switches}",
                 fontsize=9.5, color=INK)
    fig.savefig(out_path, dpi=160)
    plt.close(fig)


def zoom_figure(c1_csv: Path, c2_csv: Path, out_path: Path) -> None:
    trials = {"C1": load(c1_csv), "C2": load(c2_csv)}
    windows = {"enter": (6.4, 7.7), "exit": (12.7, 14.0)}
    fig, axes = plt.subplots(4, 2, figsize=(10, 6.2), constrained_layout=True,
                             gridspec_kw={"height_ratios": [2.4, 1, 2.4, 1]})
    for col, (kind, (w0, w1)) in enumerate(windows.items()):
        for block, cond in enumerate(("C1", "C2")):
            rows = trials[cond]
            ev = events(rows)
            ax_d, ax_s = axes[2 * block][col], axes[2 * block + 1][col]
            sel = [r for r in rows if w0 <= float(r["time_s"]) <= w1]
            t = [float(r["time_s"]) for r in sel]
            ax_d.plot(t, [num(r["raw_distance_m"]) for r in sel], color=RAW, lw=1.1, label="raw")
            ax_d.plot(t, [float(r["true_distance_m"]) for r in sel], color=INK, lw=2, label="true")
            if cond == "C2":
                ax_d.plot(t, [num(r["filtered_distance_m"]) for r in sel], color=FILT, lw=1.6, label="filtered")
                ax_d.axhline(CFG.enter_threshold_m, color=COND_COLOUR["C2"], ls=":", lw=1.1)
                ax_d.axhline(CFG.exit_threshold_m, color=COND_COLOUR["C2"], ls=":", lw=1.1)
            ax_d.axhline(CFG.threshold_m, color=MUTED, ls=":", lw=1.2)
            ax_s.step(t, [1 if r["state"] == "NEAR" else 0 for r in sel], where="post",
                      color=COND_COLOUR[cond], lw=1.6)
            cross, lat, resp = ev[kind]
            for ax in (ax_d, ax_s):
                ax.axvline(cross, color=INK, ls="--", lw=1.1)
                if resp is not None:
                    ax.axvline(resp, color="#8250df", lw=1.5)
                ax.set_xlim(w0, w1)
            n_sw = sum(1 for r in sel if r["event_label"] in ("ENTER_NEAR", "EXIT_NEAR"))
            ax_d.set_title(f"{cond} {kind}: first correct after {lat:.3f} s, {n_sw} state switch(es) in window",
                           fontsize=8.5, color=INK, loc="left")
            ax_d.set_ylabel("m")
            ax_s.set_yticks([0, 1], ["FAR", "NEAR"])
            ax_s.set_ylim(-0.2, 1.2)
            if block == 1:
                ax_s.set_xlabel("time (s)")
            if col == 0 and block == 1:
                ax_d.legend(fontsize=7.5, loc="upper right", ncol=3)
    fig.suptitle("Same seed, sigma 0.01 m. Dashed = physical crossing; purple = first correct response; "
                 "dotted = T (grey), T_enter/T_exit (green)", fontsize=8.8, color=INK)
    fig.savefig(out_path, dpi=160)
    plt.close(fig)


def aggregate(folder: str) -> list[dict[str, str]]:
    return load(HERE / folder / "summary_aggregate.csv")


def noise_figure(out_path: Path) -> None:
    """Small multiples: extra switches and false trigger vs noise (delay 0)."""
    sets = {"C1": aggregate("c1_full"), "C2": aggregate("c2_full"), "C3": aggregate("c3_full")}
    metrics = (("extra_switches", "extra switches per trial"),
               ("false_trigger_rate_per_min", "false trigger (per min)"),
               ("recovery_time_s", "recovery time (s)"))
    fig, axes = plt.subplots(1, 3, figsize=(10, 3.1), constrained_layout=True)
    for ax, (key, title) in zip(axes, metrics):
        for cond, rows in sets.items():
            sel = [r for r in rows if r["delay_ms"] == "0"]
            x = [float(r["noise_sigma_m"]) for r in sel]
            y = [float(r[key + "_mean"]) for r in sel]
            e = [float(r[key + "_sd"]) for r in sel]
            ax.errorbar(x, y, yerr=e, color=COND_COLOUR[cond], marker="o", ms=5, lw=2, capsize=3,
                        label=cond)
            ax.annotate(f"{y[-1]:.1f}" if key != "recovery_time_s" else f"{y[-1]:.2f}",
                        (x[-1], y[-1]), xytext=(6, 0), textcoords="offset points",
                        va="center", fontsize=7.5, color=INK)
        ax.set_title(title, fontsize=9, color=INK, loc="left")
        ax.set_xticks([0, 0.01, 0.03])
        ax.set_xlim(-0.003, 0.037)
        ax.set_xlabel("noise sigma (m)")
    axes[0].legend(fontsize=8, loc="upper left")
    fig.suptitle("Noise sweep, delay 0 ms, 5 trials per point (mean ± SD)", fontsize=9.5, color=INK)
    fig.savefig(out_path, dpi=160)
    plt.close(fig)


def delay_figure(out_path: Path) -> None:
    """Latency enter vs delay: additive at sigma 0, broken for C1 under noise."""
    sets = {"C1": aggregate("c1_full"), "C2": aggregate("c2_full"), "C3": aggregate("c3_full")}
    fig, axes = plt.subplots(1, 3, figsize=(10, 3.2), constrained_layout=True, sharey=True)
    for ax, sigma in zip(axes, ("0.0", "0.01", "0.03")):
        for cond, rows in sets.items():
            sel = [r for r in rows if r["noise_sigma_m"] == sigma]
            x = [int(r["delay_ms"]) for r in sel]
            y = [float(r["latency_enter_s_mean"]) for r in sel]
            e = [float(r["latency_enter_s_sd"]) for r in sel]
            ax.errorbar(x, y, yerr=e, color=COND_COLOUR[cond], marker="o", ms=5, capsize=3, label=cond)
            ax.plot([0, 300], [y[0], y[0] + 0.3], color=COND_COLOUR[cond], ls=":", lw=1.2)
        ax.set_title(f"sigma = {float(sigma):.2f} m", fontsize=9, color=INK, loc="left")
        ax.set_xticks([0, 100, 300])
        ax.set_xlabel("sensor delay (ms)")
    axes[0].set_ylabel("latency enter (s)")
    axes[0].legend(fontsize=8, loc="upper left")
    fig.suptitle("Latency enter vs delay (mean ± SD, n = 5); dotted = latency at 0 ms + delay (pure shift)",
                 fontsize=9.5, color=INK)
    fig.savefig(out_path, dpi=160)
    plt.close(fig)


def c3_figure(csv_path: Path, out_path: Path) -> None:
    rows = load(csv_path)
    t = [float(r["time_s"]) for r in rows]
    u = [float(r["command"]) for r in rows]
    fig, ax = plt.subplots(figsize=(10, 2.9), constrained_layout=True)
    ax.plot(t, u, color=COND_COLOUR["C3"], lw=1.4, label="C3 command u")
    for y in (CFG.command_min, CFG.command_max):
        ax.axhline(y, color=MUTED, ls="--", lw=1.1)
    ax.text(0.2, 0.62, "clamp +0.6", fontsize=7.5, color=INK, va="bottom")
    ax.text(0.2, -0.62, "clamp -0.6", fontsize=7.5, color=INK, va="top")
    i_min = min(range(len(u)), key=lambda i: u[i])
    ax.annotate(f"min {u[i_min]:.4f} at {t[i_min]:.2f} s", (t[i_min], u[i_min]), xytext=(40, 26),
                textcoords="offset points", fontsize=7.5, color=INK,
                arrowprops={"arrowstyle": "-", "color": MUTED})
    ax.set_ylim(-0.75, 0.75)
    ax.set_xlabel("time (s)")
    ax.set_ylabel("u")
    ax.set_title(f"{rows[0]['trial_id']} (sigma {rows[0]['noise_sigma_m']} m, delay {rows[0]['delay_ms']} ms; "
                 "lowest u of all 45 C3 robustness trials)\nu = clamp(2(0.35 - filtered)) never reaches the clamp; "
                 "the minimum is the first valid sample, where the filter is initialised from one raw value", fontsize=9, color=INK, loc="left")
    fig.savefig(out_path, dpi=160)
    plt.close(fig)


def box(ax, x, y, w, h, text, face, edge="#57606a", fs=8.3):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08",
                                fc=face, ec=edge, lw=1.2))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, color=INK, linespacing=1.35)


def arrow(ax, pts, colour="#57606a", dashed=False):
    ls = "--" if dashed else "-"
    for p0, p1 in zip(pts[:-2], pts[1:-1]):
        ax.plot([p0[0], p1[0]], [p0[1], p1[1]], color=colour, lw=1.4, ls=ls)
    ax.add_patch(FancyArrowPatch(pts[-2], pts[-1], arrowstyle="-|>", mutation_scale=13, lw=1.4,
                                 color=colour, linestyle=ls, shrinkA=0, shrinkB=0))


def note(ax, x, y, text, colour=INK, ha="center", va="bottom", fs=7.5):
    ax.text(x, y, text, ha=ha, va=va, fontsize=fs, color=colour, linespacing=1.25)


def block_diagram(out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(15, 7))
    ax.set_xlim(0, 15)
    ax.set_ylim(0, 7)
    ax.axis("off")
    red, purple, grey = "#cf222e", "#8250df", "#6e7781"
    ax.text(0.3, 6.75, "Lab 02 sensorimotor loop (simulator, dt = 0.02 s, 1001 samples per 20 s trial)",
            fontsize=11, fontweight="bold", color=INK, va="center")
    y, h, w, gap = 4.2, 1.25, 2.45, 0.55
    xs = [0.3 + i * (w + gap) for i in range(5)]
    box(ax, xs[0], y, w, h, "Physical world\nhand approaches lamp\ntrue distance d(t)", "#e7f0fb")
    box(ax, xs[1], y, w, h, "Sensor model\n+ Gaussian noise sigma\n+ delay tau (FIFO)", "#fdf0e9")
    box(ax, xs[2], y, w, h, "Validity check\nmissing / non-finite /\noutside 0.02-4.0 m", "#f6f8fa")
    box(ax, xs[3], y, w, h, "Low-pass filter (TODO 1)\nd^[k] = b d[k] + (1-b) d^[k-1]\nb = 0.25", "#e8f7f1", fs=7.6)
    box(ax, xs[4], y, w, h, "Decision rule\nC1 / C2 / C3 (TODO 2-4)\nstate FAR / NEAR", "#e8f7f1")
    ym = y + h / 2
    for i, txt in enumerate(["d(t)", "d[k]", "valid", "d^[k]"]):
        arrow(ax, [(xs[i] + w, ym), (xs[i + 1], ym)])
        note(ax, xs[i] + w + gap / 2, ym + 0.08, txt)
    yb, hb = 2.2, 1.15
    box(ax, xs[4], yb, w, hb, "Actuator (lamp)\nnormalized command u\nclamp [-0.6, 0.6]", "#fdf6e3")
    arrow(ax, [(xs[4] + w / 2, y), (xs[4] + w / 2, yb + hb)])
    note(ax, xs[4] + w / 2 + 0.08, 3.6, "state, u", ha="left")
    box(ax, xs[2], yb, w, hb, "invalid sample\nsafe_command() = 0\nstate held, INVALID", "#ffebe9", edge=red, fs=8)
    arrow(ax, [(xs[2] + w / 2, y), (xs[2] + w / 2, yb + hb)], colour=red)
    note(ax, xs[2] + w / 2 + 0.08, 3.6, "valid = 0", colour=red, ha="left")
    arrow(ax, [(xs[2] + w, yb + hb / 2), (xs[4], yb + hb / 2)], colour=red)
    note(ax, (xs[2] + w + xs[4]) / 2, yb + hb / 2 + 0.06, "u = 0", colour=red)
    box(ax, 0.3, yb, 5.1, hb, "C0 open loop: timer only\nNEAR for 4 <= t < 16 s, u = 0.6\nno sensor, no feedback",
        "#f6f8fa", fs=8)
    arrow(ax, [(2.85, yb), (2.85, 1.8), (xs[4] + w * 0.8, 1.8), (xs[4] + w * 0.8, yb)], colour=grey)
    note(ax, 8.0, 1.83, "C0 bypasses sensor, validity check and filter", colour=grey)
    yc, hc, wc = 0.15, 1.25, 4.65
    rules = ["C1 single threshold (TODO 2)\nraw d < 0.35 m -> NEAR, u = 0.6\nelse FAR, u = 0",
             "C2 hysteresis (TODO 3)\nFAR -> NEAR if d^ < 0.32 m\nNEAR -> FAR if d^ > 0.38 m, else hold",
             "C3 proportional (TODO 4)\nu = clamp(2 (0.35 - d^), -0.6, 0.6)\nstate NEAR if d^ < 0.35 m"]
    for i, txt in enumerate(rules):
        box(ax, 0.3 + i * (wc + 0.25), yc, wc, hc, txt, "#ffffff", fs=8)
    arrow(ax, [(xs[4] + w, yb + hb / 2), (14.8, yb + hb / 2), (14.8, 6.2), (xs[0] + w / 2, 6.2),
               (xs[0] + w / 2, y + h)], colour=purple, dashed=True)
    note(ax, 7.6, 6.27, "feedback on a real robot: lamp motion changes what the sensor sees. "
         "NOT simulated here: d(t) is a fixed trajectory, so u never changes the next sample",
         colour=purple, fs=8)
    fig.savefig(out_path, dpi=170, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    cmp_dir = HERE / "student_comparison" / "trials"
    trial_figure(cmp_dir / "C1_n0.01_d000_r01.csv", OUT / "fig1_C1_trial.png")
    trial_figure(cmp_dir / "C2_n0.01_d000_r01.csv", OUT / "fig2_C2_trial.png")
    zoom_figure(cmp_dir / "C1_n0.01_d000_r01.csv", cmp_dir / "C2_n0.01_d000_r01.csv", OUT / "fig3_C1_vs_C2_zoom.png")
    noise_figure(OUT / "fig4_noise_sweep.png")
    delay_figure(OUT / "fig5_delay_sweep.png")
    c3_figure(HERE / "c3_full" / "trials" / "C3_n0.03_d100_r02.csv", OUT / "fig6_C3_command.png")
    block_diagram(OUT / "block_diagram.png")
    print("figures written to:", OUT)


if __name__ == "__main__":
    main()
