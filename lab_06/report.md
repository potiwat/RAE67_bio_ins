# Lab 06 — Lamp Emotion and Interaction

## Prediction and protocol

Prediction (written in the results report; not a preregistered prediction): C0 without debounce/hysteresis would have more state transitions from button bounce and noisy distance; C1 may respond later because of debounce but should suppress repeated transitions. A fault while already neutral and a touch conflicting with near should not create a new output onset.

All values are from the proposed course simulation model, not a physical robot. Run C0 and C1 on paired input files for seeds 41, 42, and 43; each file has 1,101 samples over 22 s at `dt=.02 s`. Scheduler delay is .04 s. C1 uses .06 s button/touch debounce, near enter/exit thresholds .20/.28 m, and approach enter/exit .80/.95 m. Active-state timeout is 2 s and normal inactivity timeout is 6 s. Output bounds and slew constraints are held fixed between conditions.

The checker passed **40/40 transition pairs** using the baseline contract. `student_policy.py` preserves safety priority and hold behavior, then maps touch→happy, button/approach→interested, active timeout→normal, and normal idle→sleepy.

## FSM and event table

Priority for events recognized in the same tick: `fault > near > clear > touch > button > approach > timeout > idle`. The first three rules apply from every state. After those rules, `afraid` holds for every other event. `None` means hold the current state.

| State \ event | fault | near | clear | touch | button | approach | timeout | idle |
|---|---|---|---|---|---|---|---|---|
| normal | normal | afraid | normal | happy | interested | interested | hold | sleepy |
| interested | normal | afraid | normal | happy | interested | interested | normal | hold |
| happy | normal | afraid | normal | happy | interested | interested | normal | hold |
| afraid | normal | afraid | normal | hold | hold | hold | hold | hold |
| sleepy | normal | afraid | normal | happy | interested | interested | hold | hold |

C1 uses distance hysteresis/debounce as listed above. Entering `afraid` takes priority over a simultaneously recognized touch; a touch recognized on a later tick while still afraid is held by the policy. State outputs, joint bounds, and RGB mapping are those defined by the course model; they are simulated commands, not physical measurements.

## Results

| Condition / seed | All source inputs | Both onset | ≤1 s among observed | No both onset | Max observed latency (s) | State transitions | Primary pass / 7 (missing) |
|---|---:|---:|---:|---:|---:|---:|---:|
| C0 / 41 | 10 | 7 | 7 | 3 | .240 | 67 | 7 (0) |
| C1 / 41 | 10 | 7 | 7 | 3 | .140 | 9 | 7 (0) |
| C0 / 42 | 10 | 6 | 6 | 4 | .180 | 72 | 6 (1) |
| C1 / 42 | 10 | 7 | 7 | 3 | .140 | 10 | 7 (0) |
| C0 / 43 | 10 | 6 | 6 | 4 | .040 | 63 | 6 (1) |
| C1 / 43 | 10 | 7 | 7 | 3 | .140 | 9 | 7 (0) |
| **C0 total** | **30** | **19** | **19** | **11** | **.240** | — | **19 / 21 (2)** |
| **C1 total** | **30** | **21** | **21** | **9** | **.140** | — | **21 / 21 (0)** |

Across this fixed synthetic input set, C0 produced 63–72 state transitions per run versus 9–10 for C1. This is consistent with the prediction for bounce/noise handling, but three synthetic seeds do not establish general performance. The “≤1 s among observed” column is not an all-input success rate: its denominator excludes missing/no-onset sources. The separately reported primary denominator contains the seven predeclared IDs; C0 missed `clear_01` at seed 42 (`filtered_not_recognized`) and `clear_02` at seed 43 (`no_state_change`).

All 10 source IDs remain in each run's metrics. No-both statuses are:

| Seed | C0: no both onset | C1: no both onset |
|---|---|---|
| 41 | `touch_conflict` (`discarded_priority`); `invalid_01`, `stale_01` (`no_state_change`) | `touch_conflict` (`policy_held`); `invalid_01`, `stale_01` (`no_state_change`) |
| 42 | `clear_01` (`filtered_not_recognized`); `touch_conflict` (`preempted_before_apply`); `invalid_01`, `stale_01` (`no_state_change`) | `touch_conflict` (`policy_held`); `invalid_01`, `stale_01` (`no_state_change`) |
| 43 | `touch_conflict` (`discarded_priority`); `clear_02`, `invalid_01`, `stale_01` (`no_state_change`) | `touch_conflict` (`policy_held`); `invalid_01`, `stale_01` (`no_state_change`) |

`discarded_priority` means a higher-priority recognized event won; `policy_held` means the FSM returned no transition; `preempted_before_apply` means a queued command was replaced before application; `filtered_not_recognized` means the sensor event did not pass the filter; and `no_state_change` means the resulting output did not change. None of these missing outcomes is assigned a zero latency.

## Event trace and source-data check

For `button_01` in C0 seed 41, source=1.00 s, recognized/decision=1.00 s, apply=1.04 s, and motion/RGB onset=1.04 s; `1.04−1.00=.04 s`, matching `both_latency_s`. In C1 seed 41, debounce delays recognition/decision to 1.10 s; apply and both output onsets occur at 1.14 s; `1.14−1.00=.14 s`, also matching the event CSV. This is simulated command-onset latency, not physical actuator latency.

The stored re-run was compared against the original result manifest: config, inputs, all raw/event CSVs, metrics, and six traces match byte-for-byte; source snapshot hashes match the manifest. No source/config change explains the results. Re-run artifacts are in [rerun/](results/lab06_complete_20261111/rerun/).

Figures and source data:

- [C0 seed 41 trace](results/lab06_complete_20261111/trace_C0_r01.svg), [C1 seed 41 trace](results/lab06_complete_20261111/trace_C1_r01.svg)
- [event CSV C0 seed 41](results/lab06_complete_20261111/events_C0_r01.csv), [event CSV C1 seed 41](results/lab06_complete_20261111/events_C1_r01.csv)
- [metrics](results/lab06_complete_20261111/metrics.json), [HTML report](results/lab06_complete_20261111/report.html)

## Discussion and limitations

Results match the prediction that debounce/hysteresis reduces state-transition count in these simulated noisy inputs, while C1 button response is later in the example because of debounce. Fault and stale/invalid inputs while already neutral do not produce a new command onset; this is a negative result, not a zero-latency success. All trials are deterministic course-model simulations with synthetic repetitions. No actuator, LED, torque, linkage, collision, clock/camera calibration, gait, or hardware-safety behavior was tested. The FSM is not learning and does not update persistent parameters.

Reproduce from the lab directory:

```powershell
python check_submission.py --contract baseline
python lab06.py --policy student --condition all --repeats 3 --output-dir results\lab06_complete_20261111\new_run
```

The runner requires a new output directory; existing raw data are retained. Data and plot files for all six runs are in `results/lab06_complete_20261111/`.
