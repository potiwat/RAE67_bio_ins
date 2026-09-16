"""Lab 02 simulator: Robust Reactive Lamp.

The model is intentionally simple and deterministic enough for teaching.  It is
not a hardware driver and its parameters are not safety limits for a real robot.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import shutil
import statistics
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence


CONDITIONS = ("C0", "C1", "C2", "C3")


@dataclass(frozen=True)
class LabConfig:
    dt: float = 0.02
    duration_s: float = 20.0
    threshold_m: float = 0.35
    enter_threshold_m: float = 0.32
    exit_threshold_m: float = 0.38
    beta: float = 0.25
    target_distance_m: float = 0.35
    kp: float = 2.0
    command_min: float = -0.6
    command_max: float = 0.6
    sensor_min_m: float = 0.02
    sensor_max_m: float = 4.0
    stable_duration_s: float = 0.5


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def true_distance_m(time_s: float) -> float:
    """Twenty-second reference trajectory used by every simulated trial."""
    if time_s < 4.0:
        return 0.60
    if time_s < 8.0:
        return 0.60 - 0.35 * ((time_s - 4.0) / 4.0)
    if time_s < 12.0:
        return 0.25 + 0.015 * math.sin(2.0 * math.pi * 1.2 * (time_s - 8.0))
    if time_s < 16.0:
        return 0.25 + 0.35 * ((time_s - 12.0) / 4.0)
    return 0.60


class Controller:
    def __init__(self, condition: str, config: LabConfig) -> None:
        if condition not in CONDITIONS:
            raise ValueError(f"unknown condition: {condition}")
        self.condition = condition
        self.config = config
        self.state = "FAR"
        self.filtered_distance: float | None = None

    def _filter(self, raw_distance: float) -> float:
        if self.filtered_distance is None:
            self.filtered_distance = raw_distance
        else:
            beta = self.config.beta
            self.filtered_distance = (
                beta * raw_distance + (1.0 - beta) * self.filtered_distance
            )
        return self.filtered_distance

    def step(self, time_s: float, raw_distance: float | None, valid: bool) -> tuple[str, float, float | None]:
        """Return state, normalized command and filtered distance."""
        if self.condition == "C0":
            self.state = "NEAR" if 4.0 <= time_s < 16.0 else "FAR"
            return self.state, (0.6 if self.state == "NEAR" else 0.0), None

        if not valid or raw_distance is None:
            return self.state, 0.0, self.filtered_distance

        filtered = self._filter(raw_distance)

        if self.condition == "C1":
            # C1 deliberately uses the unfiltered value so noise can cause chatter.
            self.state = "NEAR" if raw_distance < self.config.threshold_m else "FAR"
            command = 0.6 if self.state == "NEAR" else 0.0
        elif self.condition == "C2":
            if self.state == "FAR" and filtered < self.config.enter_threshold_m:
                self.state = "NEAR"
            elif self.state == "NEAR" and filtered > self.config.exit_threshold_m:
                self.state = "FAR"
            command = 0.6 if self.state == "NEAR" else 0.0
        else:  # C3
            error = self.config.target_distance_m - filtered
            command = clamp(
                self.config.kp * error,
                self.config.command_min,
                self.config.command_max,
            )
            self.state = "NEAR" if filtered < self.config.target_distance_m else "FAR"

        return self.state, command, filtered


def _is_valid_sample(raw: float | None, config: LabConfig) -> tuple[bool, str]:
    if raw is None:
        return False, "MISSING_OR_DELAY_BUFFER"
    if not math.isfinite(raw):
        return False, "NON_FINITE"
    if not config.sensor_min_m <= raw <= config.sensor_max_m:
        return False, "OUT_OF_RANGE"
    return True, ""


def simulate_trial(
    condition: str,
    noise_sigma_m: float,
    delay_ms: int,
    seed: int,
    config: LabConfig | None = None,
    invalid_rate: float = 0.0,
) -> list[dict[str, object]]:
    """Simulate one trial and return rows ready for CSV output."""
    config = config or LabConfig()
    rng = random.Random(seed)
    controller = Controller(condition, config)
    delay_steps = max(0, round((delay_ms / 1000.0) / config.dt))
    sensor_buffer: deque[tuple[float, float | None]] = deque()
    rows: list[dict[str, object]] = []
    previous_state = controller.state
    sample_count = int(round(config.duration_s / config.dt)) + 1

    for sample_index in range(sample_count):
        time_s = round(sample_index * config.dt, 10)
        physical_distance = true_distance_m(time_s)
        raw_now: float | None = physical_distance + rng.gauss(0.0, noise_sigma_m)
        if invalid_rate > 0.0 and rng.random() < invalid_rate:
            raw_now = None

        sensor_buffer.append((time_s, raw_now))
        if len(sensor_buffer) > delay_steps:
            sensor_time_s, delivered_raw = sensor_buffer.popleft()
        else:
            sensor_time_s, delivered_raw = time_s, None

        sample_age_s = time_s - sensor_time_s if delivered_raw is not None else math.nan
        valid, invalid_reason = _is_valid_sample(delivered_raw, config)
        state, command, filtered = controller.step(time_s, delivered_raw, valid)

        if not valid and condition != "C0":
            event_label = "INVALID"
        elif state != previous_state:
            event_label = "ENTER_NEAR" if state == "NEAR" else "EXIT_NEAR"
        else:
            event_label = ""

        expected_state = "NEAR" if physical_distance < config.threshold_m else "FAR"
        rows.append(
            {
                "trial_id": "",
                "condition": condition,
                "seed": seed,
                "time_s": time_s,
                "sensor_time_s": sensor_time_s,
                "sample_age_s": sample_age_s,
                "true_distance_m": physical_distance,
                "raw_distance_m": delivered_raw,
                "filtered_distance_m": filtered,
                "expected_state": expected_state,
                "state": state,
                "command": command,
                "valid": int(valid),
                "event_label": event_label,
                "invalid_reason": invalid_reason,
                "noise_sigma_m": noise_sigma_m,
                "delay_ms": delay_ms,
            }
        )
        previous_state = state

    return rows


def _crossing_time(rows: Sequence[dict[str, object]], direction: str, threshold: float) -> float | None:
    for previous, current in zip(rows, rows[1:]):
        y0 = float(previous["true_distance_m"])
        y1 = float(current["true_distance_m"])
        crossed = (direction == "down" and y0 >= threshold > y1) or (
            direction == "up" and y0 <= threshold < y1
        )
        if crossed:
            t0 = float(previous["time_s"])
            t1 = float(current["time_s"])
            fraction = (threshold - y0) / (y1 - y0)
            return t0 + fraction * (t1 - t0)
    return None


def _first_correct_latency(
    rows: Sequence[dict[str, object]], event_time: float | None, desired_state: str
) -> float | None:
    if event_time is None:
        return None
    for row in rows:
        time_s = float(row["time_s"])
        if time_s >= event_time and row["state"] == desired_state and int(row["valid"]):
            return max(0.0, time_s - event_time)
    return None


def _stable_recovery_latency(
    rows: Sequence[dict[str, object]],
    event_time: float | None,
    desired_state: str,
    stable_samples: int,
) -> float | None:
    if event_time is None:
        return None
    for index, row in enumerate(rows):
        time_s = float(row["time_s"])
        if time_s < event_time:
            continue
        window = rows[index : index + stable_samples]
        if len(window) < stable_samples:
            break
        if all(item["state"] == desired_state and int(item["valid"]) for item in window):
            return max(0.0, time_s - event_time)
    return None


def calculate_metrics(rows: Sequence[dict[str, object]], config: LabConfig | None = None) -> dict[str, object]:
    config = config or LabConfig()
    enter_time = _crossing_time(rows, "down", config.threshold_m)
    exit_time = _crossing_time(rows, "up", config.threshold_m)
    stable_samples = max(1, math.ceil(config.stable_duration_s / config.dt))

    enter_latency = _first_correct_latency(rows, enter_time, "NEAR")
    exit_latency = _first_correct_latency(rows, exit_time, "FAR")
    enter_recovery = _stable_recovery_latency(rows, enter_time, "NEAR", stable_samples)
    exit_recovery = _stable_recovery_latency(rows, exit_time, "FAR", stable_samples)

    state_changes = [row for row in rows if row["event_label"] in ("ENTER_NEAR", "EXIT_NEAR")]
    false_activations = sum(
        1
        for row in state_changes
        if row["event_label"] == "ENTER_NEAR" and row["expected_state"] == "FAR"
    )
    valid_count = sum(int(row["valid"]) for row in rows)
    valid_minutes = valid_count * config.dt / 60.0
    commands = [float(row["command"]) for row in rows]
    smoothness = statistics.fmean(
        abs(current - previous) for previous, current in zip(commands, commands[1:])
    )
    recovery_values = [value for value in (enter_recovery, exit_recovery) if value is not None]

    first = rows[0]
    return {
        "trial_id": first["trial_id"],
        "condition": first["condition"],
        "seed": first["seed"],
        "noise_sigma_m": first["noise_sigma_m"],
        "delay_ms": first["delay_ms"],
        "latency_enter_s": enter_latency,
        "latency_exit_s": exit_latency,
        "recovery_time_s": max(recovery_values) if recovery_values else None,
        "false_trigger_count": false_activations,
        "false_trigger_rate_per_min": false_activations / valid_minutes if valid_minutes else None,
        "switching_count": len(state_changes),
        "extra_switches": max(0, len(state_changes) - 2),
        "mean_abs_command_change": smoothness,
        "invalid_sample_count": len(rows) - valid_count,
    }


def _mean(values: Iterable[object]) -> float | None:
    numeric = [float(value) for value in values if value not in (None, "")]
    return statistics.fmean(numeric) if numeric else None


def _sd(values: Iterable[object]) -> float | None:
    numeric = [float(value) for value in values if value not in (None, "")]
    return statistics.stdev(numeric) if len(numeric) >= 2 else 0.0 if numeric else None


def aggregate_metrics(trial_metrics: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[object, object, object], list[dict[str, object]]] = {}
    for item in trial_metrics:
        key = (item["condition"], item["noise_sigma_m"], item["delay_ms"])
        grouped.setdefault(key, []).append(item)

    output: list[dict[str, object]] = []
    fields = (
        "latency_enter_s",
        "latency_exit_s",
        "recovery_time_s",
        "false_trigger_rate_per_min",
        "extra_switches",
        "mean_abs_command_change",
        "invalid_sample_count",
    )
    for (condition, noise, delay), items in sorted(grouped.items()):
        row: dict[str, object] = {
            "condition": condition,
            "noise_sigma_m": noise,
            "delay_ms": delay,
            "trials": len(items),
        }
        for field in fields:
            row[f"{field}_mean"] = _mean(item[field] for item in items)
            row[f"{field}_sd"] = _sd(item[field] for item in items)
        output.append(row)
    return output


def _write_csv(path: Path, rows: Sequence[dict[str, object]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def build_protocol(
    protocol: str,
    condition: str,
    trials: int | None,
) -> list[tuple[str, float, int, int]]:
    if protocol == "controller-comparison":
        repeat = trials or 5
        return [(item, 0.01, 0, repeat) for item in CONDITIONS]
    if protocol == "robustness-short":
        repeat = trials or 3
        combinations = [(0.00, 0), (0.01, 0), (0.03, 0), (0.01, 100), (0.01, 300)]
        return [(condition, noise, delay, repeat) for noise, delay in combinations]
    if protocol == "robustness-full":
        repeat = trials or 5
        return [
            (condition, noise, delay, repeat)
            for noise in (0.00, 0.01, 0.03)
            for delay in (0, 100, 300)
        ]
    raise ValueError(f"unknown protocol: {protocol}")


def run_protocol(
    protocol: str,
    output_dir: Path,
    condition: str = "C2",
    trials: int | None = None,
    seed_base: int = 202602,
    config: LabConfig | None = None,
    overwrite: bool = False,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    config = config or LabConfig()
    if output_dir.exists() and any(output_dir.iterdir()):
        if not overwrite:
            raise FileExistsError(f"output directory is not empty: {output_dir}")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    trials_dir = output_dir / "trials"
    trials_dir.mkdir()

    plan = build_protocol(protocol, condition, trials)
    all_metrics: list[dict[str, object]] = []
    trial_number = 0
    for planned_condition, noise, delay, repeat in plan:
        for repeat_index in range(repeat):
            trial_number += 1
            seed = seed_base + trial_number
            trial_id = f"{planned_condition}_n{noise:.2f}_d{delay:03d}_r{repeat_index + 1:02d}"
            rows = simulate_trial(planned_condition, noise, delay, seed, config)
            for row in rows:
                row["trial_id"] = trial_id
            _write_csv(trials_dir / f"{trial_id}.csv", rows)
            all_metrics.append(calculate_metrics(rows, config))

    aggregate = aggregate_metrics(all_metrics)
    _write_csv(output_dir / "summary_trials.csv", all_metrics)
    _write_csv(output_dir / "summary_aggregate.csv", aggregate)
    manifest = {
        "protocol": protocol,
        "robustness_condition": condition,
        "seed_base": seed_base,
        "trial_count": trial_number,
        "config": asdict(config),
        "plan": [
            {"condition": item[0], "noise_sigma_m": item[1], "delay_ms": item[2], "trials": item[3]}
            for item in plan
        ],
        "claim_boundary": "Proposed course model; validate all limits before real-hardware use.",
    }
    (output_dir / "run_config.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return all_metrics, aggregate


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--protocol",
        choices=("controller-comparison", "robustness-short", "robustness-full"),
        default="controller-comparison",
    )
    parser.add_argument("--condition", choices=CONDITIONS, default="C2")
    parser.add_argument("--trials", type=int, default=None, help="override trials per combination")
    parser.add_argument("--seed-base", type=int, default=202602)
    parser.add_argument("--out", type=Path, default=Path("results/controller_comparison"))
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    _, aggregate = run_protocol(
        protocol=args.protocol,
        output_dir=args.out,
        condition=args.condition,
        trials=args.trials,
        seed_base=args.seed_base,
        overwrite=args.overwrite,
    )
    print(f"wrote results to: {args.out.resolve()}")
    print(f"aggregate rows: {len(aggregate)}")


if __name__ == "__main__":
    main()
