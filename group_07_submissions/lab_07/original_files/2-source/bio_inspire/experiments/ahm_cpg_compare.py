"""Hardware-free Lab07 direct-vs-hormone experiment using retained course code.

The source model is reviewed Lab05 Python stored as text for provenance.
No servo, camera, GPIO, ROS, serial or hardware-runtime imports are permitted.
"""
from __future__ import annotations

import csv
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import runpy
import statistics

ROOT = Path(__file__).resolve().parents[2]
SOURCES = ROOT / 'Lab07/worksheet_review/section4_sources'
COURSE_PATH = SOURCES / 'Week_05_Lab_05__02_Source__course_model.py.txt'
CONTRACT_PATH = SOURCES / 'Week_03_Lab_03__03_Results__Week4_Bridge__handoff_contract.json'
REFERENCE_PATH = SOURCES / 'Week_05_Lab_05__03_Results__phi_only__config.json'
DT = .05
DURATION = 30.
STEPS = 600
ALPHA = 1.1
RATES = (.8, .6, .2)
SEGMENTS = {'pre': (0., 10.), 'on': (10., 20.), 'off': (20., 30.)}


@lru_cache(maxsize=1)
def course_model():
    return runpy.run_path(str(COURSE_PATH))


def contract():
    return json.loads(CONTRACT_PATH.read_text(encoding='utf-8'))


def source_hashes():
    return {str(p.relative_to(ROOT)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (COURSE_PATH, CONTRACT_PATH, REFERENCE_PATH)}


def warmup():
    a, b = .1, 0.
    step = course_model()['step_cpg']
    for _ in range(200):
        a, b = step(a, b, ALPHA, .2)
    return a, b


def simulate(condition, stimulus=None):
    """601 state rows; the first 600 also contain interval commands/next states.

    C1 R_used=H_k; CPG and hormone both consume state at t_k. C0 uses S_k.
    Final row has state only and no fictional command or input at t=30.
    Invalid stimulus resets hormone and uses baseline phi for that interval.
    """
    values = list(stimulus) if stimulus is not None else [float(200 <= k < 400) for k in range(STEPS)]
    if len(values) != STEPS:
        raise ValueError('stimulus must contain exactly 600 intervals at dt=.05s')
    return simulate_samples(condition, values)


def simulate_samples(condition, stimulus):
    """Same teacher model for a finite sequence, at the unchanged dt=.05s."""
    if condition not in ('C0', 'C1'):
        raise ValueError('condition must be C0 (direct) or C1 (hormone)')
    values = list(stimulus)
    if not 1 <= len(values) <= 12000:
        raise ValueError('1..12000 input intervals required (max600 simulated seconds)')
    course, mapping = course_model(), contract()
    a, b = warmup()
    h = 0. if condition == 'C1' else None
    rows = []
    for k, value in enumerate(values):
        valid = type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1
        r = (h if condition == 'C1' else float(value)) if valid else 0.
        parameters = course['mapped_parameters'](r, mapping, 'phi-only')
        phi = parameters['phi_rad']
        a_next, b_next = course['step_cpg'](a, b, ALPHA, phi)
        hormone = course['hormone_step'](h, float(value) if valid else math.nan, DT, RATES) if condition == 'C1' else None
        h_next = hormone['h'] if hormone is not None else None
        rows.append(dict(t_s=k*DT, t_next_s=(k+1)*DT, condition=condition,
                         stimulus=float(value) if valid else None, fault=int(not valid),
                         h=h, r_used=r, phi_rad_per_update=phi, alpha=ALPHA,
                         o1=a, o2=b, h_next=h_next, o1_next=a_next, o2_next=b_next))
        a, b, h = a_next, b_next, h_next
    rows.append(dict(t_s=len(values)*DT, t_next_s=None, condition=condition, stimulus=None,
                     fault=None, h=h, r_used=None, phi_rad_per_update=None, alpha=ALPHA,
                     o1=a, o2=b, h_next=None, o1_next=None, o2_next=None))
    return rows


def output_periods(samples):
    """Rising zero crossings, linear time interpolation, complete periods only."""
    crossings = []
    for index, ((ta, a), (tb, b)) in enumerate(zip(samples, samples[1:])):
        if not all(math.isfinite(v) for v in (ta, a, tb, b)) or tb <= ta:
            raise ValueError('finite samples with strictly increasing times required')
        if a < 0 <= b:
            crossings.append(ta + (-a)/(b-a)*(tb-ta))
        elif index == 0 and a == 0 and b > 0:
            crossings.append(ta)
    return [dict(start_s=a, end_s=b, period_s=b-a, midpoint_s=(a+b)/2,
                 frequency_hz=1/(b-a)) for a, b in zip(crossings, crossings[1:])]


def segment_periods(periods, start, end):
    return [row for row in periods if row['start_s'] >= start and row['end_s'] <= end]


def period_metrics(periods):
    ts = [p['period_s'] for p in periods]
    changes = [abs(b-a) for a, b in zip(ts, ts[1:])]
    return dict(period_count=len(ts), frequency_hz=1/statistics.mean(ts) if ts else None,
                delta_t_count=len(changes), delta_t_mean_s=statistics.mean(changes) if changes else None,
                delta_t_max_s=max(changes) if changes else None)


def analyze(rows):
    commands = rows[:-1]
    periods = output_periods([(r['t_s'], r['o1']) for r in rows])
    phi = [r['phi_rad_per_update'] for r in commands]
    jumps = [abs(b-a) for a, b in zip(phi, phi[1:])]
    latency = next((r['t_s']-10 for r in commands if 10 <= r['t_s'] < 20
                    and r['phi_rad_per_update'] >= .22-1e-12), None)
    recovery = None
    # Require one full second of interval commands inside the 10%-of-step band.
    for k, r in enumerate(commands):
        if r['t_s'] < 20 or k+20 > len(commands):
            continue
        if all(abs(v['phi_rad_per_update']-.2) <= .02+1e-12 for v in commands[k:k+20]):
            recovery = r['t_s']-20
            break
    return dict(**period_metrics(periods),
                segments={name: period_metrics(segment_periods(periods, a, b))
                          for name, (a, b) in SEGMENTS.items()},
                phi_max_step_rad=max(jumps, default=0.), phi_total_variation_rad=sum(jumps),
                command_latency_10pct_s=latency, command_recovery_10pct_s=recovery,
                fault_count=sum(r['fault'] for r in commands),
                physical_motion_smoothness=None, physical_measurement_reason='simulation only; no actuator model')


def write_csv(path, rows, fieldnames=None):
    fields = fieldnames or list(rows[0])
    with Path(path).open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
