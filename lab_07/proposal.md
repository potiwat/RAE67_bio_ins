# Proposal — Bounded AHM modulation of an SO(2) CPG

## Research question and hypothesis

**Question.** For the same predeclared button, touch, and approach inputs, does coupling a bounded hormone-inspired artificial hormone mechanism (AHM) to an SO(2) central pattern generator (CPG) change mean servo-command total variation without increasing median source-to-command onset latency by more than 0.10 s, compared with a fixed-parameter CPG?

**Prospective hypothesis.** In the proposed model, AHM-to-CPG coupling will reduce mean per-step servo-command total variation by at least 10% versus baseline C0, while paired median source-to-command onset latency is no more than 0.10 s slower. These are thresholds to evaluate, not results from the Lab07 offline transport experiment.

## Biological inspiration and model equations

The project is conceptually inspired by hormone-mediated modulation of locomotion in Ngamkajornwiwat et al. (2020), *IEEE Access* 8, 91587–91602, DOI `10.1109/ACCESS.2020.2992794`. The proposed project does not claim to reproduce that paper's MNLC, hormone equations, terrain adaptation, or results. The AHM is the Week04 proposed course model:

```text
R_old = clamp((H_old - H_min)/(H_max - H_min), 0, 1)
P = k_prod S
C = k_clear H_old
B = k_bind R_old
H_new = clamp(H_old + dt(P - C - B), 0, 1)
R_new = H_new
```

Use the Week03 SO(2) course recurrence with both old outputs read before either is updated:

```text
a1_next = alpha (cos(phi) o1 + sin(phi) o2)
a2_next = alpha (-sin(phi) o1 + cos(phi) o2)
o1_next = tanh(a1_next)
o2_next = tanh(a2_next)
```

The integration maps receptor state to bounded CPG phase and amplitude:

```text
phi = clamp(0.20 + 0.20 R, 0.10, 0.45) rad
amplitude_scale = 0.75 + 0.25 R
```

The CPG decoder supplies bounded semantic servo targets `[tilt, extend, nod]`; the FSM remains responsible for safety priority and emotion state. Hormone state does not directly command a motor. RGB integer channels are normalized by `/255` with alpha 1.

## Conditions and controls

| Condition | Role | Controller change | Planned repeats |
|---|---|---|---:|
| C0 | Baseline | Fixed CPG `alpha=1.10`, `phi=.20 rad`; compute/log AHM state but do not feed it to CPG parameters | 3 |
| C1 | Coupled | Connect the same AHM receptor to the bounded `phi` and amplitude mapping above; change no other factor | 3 |

Controls within each paired run: identical FSM transition table, input waveform and predeclared source IDs; same initial oscillator and hormone state, `dt`, scheduler, bounds, RGB/state map, and observation window. For robot trials, keep the same robot, sensor placement, firmware/driver version, and calibration within each pair, recording deviations. Balance order as C0–C1, C1–C0, C0–C1; reset to neutral and re-calibrate between trials.

Initial parameter candidates, all explicitly proposed pending code review/calibration:

| Parameter | Candidate | Unit / provenance |
|---|---:|---|
| `k_prod` | .8 | normalized H/s, Week04 proposed model |
| `k_clear` | .6 | s⁻¹, Week04 proposed model |
| `k_bind` | .2 | normalized H/s per normalized receptor, Week04 proposed model |
| `dt` | .05 | s, proposed simulation step; validate stability |
| `alpha` | 1.10 | dimensionless, Week03 course baseline |
| `phi` in C0 | .20 | rad/update, Week03 course baseline |
| `phi` bounds in C1 | [.10,.45] | rad/update, Week04 proposed mapping |
| semantic servo bounds | [.35,.25,.30] | rad for `[tilt,extend,nod]`; not hardware-certified |

The predeclared primary input set is `button_01`, `touch_01`, `approach_01`, `clear_01`, `near_01`, `clear_02`, and `button_02`. Freeze positive-response mapping and protocol version before collection; use the same denominator in C0 and C1 and report every source outcome.

## Outcomes and missing-data rules

1. **Mean servo-command total variation** (`rad per output interval`): for three commanded radian channels, sum absolute changes between adjacent samples and channels, divide by the number of intervals in the declared active-input window; also retain per-channel values.
2. **Source-to-servo onset latency** (`s`): for each predeclared expected ID, subtract source-event time from first servo-command change of at least .02 rad. Report simulation command onset separately from real-robot physical onset.

A trial with no complete timestamped command trace is missing, never zero. If no qualifying onset occurs during the observation window, record missing/censored with reason and retain it in the denominator. Report all three repeats and paired differences; do not combine software command latency with physical motion latency.

## Simulation and proposed real-robot methods

### Simulation

In a separate project branch/module, implement and unit-test the AHM, simultaneous SO(2) update, bounded decoder, and FSM handoff. Run C0 and C1 with paired seeds 41, 42, and 43, identical source inputs in each pair, and reset states. Log source IDs/times, H/R, oscillator states, commands, config and source hashes. The Lab07 offline runner currently tests ideal C0 versus modeled transport C1 only; it is not this AHM–CPG simulation.

### Real robot (planned; not run)

First identify the available robot, MCU/driver, and ROS 2 Jazzy host. Version and bench-test the seven-topic adapter. Calibrate semantic radian targets through the actual linkage; with actuators disabled, verify neutral pose, direction, per-joint bounds, slew/watchdog, and hardware emergency stop. Only after instructor/safety approval run three paired C0/C1 scripted trials. Record source IDs, calibrated physical onset (encoder or synchronized video), sensor/driver configuration, failures, and protocol deviations. Do not treat ROS bag receipt as physical movement.

### Human interaction (planned; not run)

Run one approved 600-s scripted interaction scenario only after safety review and required consent. Use coded participant IDs, no names in analysis files, and allow withdrawal at any time. Define neutral/rest periods and input schedule before the session; log source IDs and all missing events. Counterbalance condition order across paired blocks, reset/calibrate to neutral between conditions, and pause/stop for discomfort, unexpected motion, contact risk, communication loss, stale command, or limit violation. The offline 22-s replay is only a protocol pilot and does not substitute for this scenario.

## Clock correlation, safety, and analysis

The ROS messages do not contain Header/input IDs. Attach unique IDs in the source/logging wrapper and carry them in sidecars through decision, command, and physical observation. Use one host monotonic clock where possible. For host/MCU/video, record synchronization markers before and after each trial, estimate offset/drift, and report a conservative error bound. If identity or clock uncertainty exceeds the predeclared tolerance, latency is unavailable; do not infer it from ordinal order or subtract unsynchronized clocks.

A named operator supervises each robot trial with an immediately reachable hardware E-stop. Start with actuators disabled. Stop for unexpected motion, bounds violation, stale sensor/command, communication loss, discomfort, or contact risk; disable torque/power as appropriate, preserve logs, review the cause, and do not resume before approval. The software model's bounds do not certify hardware safety.

## Timeline and deliverables

| Week | Planned work |
|---|---|
| 1 | Freeze question, protocol, input IDs, consent/safety review, and interface graph |
| 2 | Implement AHM–CPG integration and unit tests; record code/config hashes |
| 3 | Run paired simulation pilot; verify metrics and missing-data rules without tuning to test outcomes |
| 4 | If hardware is available and approved, calibrate, bench-test safety, and run three paired robot trials per condition |
| 5 | If approved, run the 600-s human scenario; analyze paired data and submit report, raw traces, manifest, and deviations |

Dates, hardware availability, instructor approval, and human-study approvals must be confirmed by the group and instructor. The current Lab07 proposal checker passes its required structural fields; scientific validity remains for instructor review. No robot, human, or integrated AHM–CPG results are claimed here.
