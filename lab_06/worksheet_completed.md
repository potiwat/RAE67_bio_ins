# Lab 06 — Completed worksheet

## 1. Prediction

Prediction: C0 (no debounce/hysteresis) would change state more often from button bounce and noisy distance. C1 could respond later because of debounce but should suppress repeated state changes. A fault while already neutral and a touch conflicting with near were expected to have no new motion/RGB onset. This prediction is recorded in the results report, not preregistered before the runs.

## 2–3. FSM and transition matrix

Priority for simultaneous recognized events is `fault > near > clear > touch > button > approach > timeout > idle`. Fault, near, and clear override state; after those, afraid holds every event. Timeout is recovery from interested/happy to normal; normal idle transitions to sleepy.

| State \ event | fault | near | clear | touch | button | approach | timeout | idle |
|---|---|---|---|---|---|---|---|---|
| normal | normal | afraid | normal | happy | interested | interested | hold | sleepy |
| interested | normal | afraid | normal | happy | interested | interested | normal | hold |
| happy | normal | afraid | normal | happy | interested | interested | normal | hold |
| afraid | normal | afraid | normal | hold | hold | hold | hold | hold |
| sleepy | normal | afraid | normal | happy | interested | interested | hold | hold |

The course model uses active timeout 2 s and normal inactivity timeout 6 s. Near thresholds in C1 are enter=.20 m / exit=.28 m; approach thresholds are enter=.80 m / exit=.95 m. Button/touch debounce is .06 s.

## 4. Implementation and checker

Completed `student_policy.py` under the baseline contract. Checker result: `Checked 40 transition pairs; contract=baseline; failures=0`. The boundary case `afraid + button → hold` is a useful regression check: applying the general button rule before the afraid guard would incorrectly transition to interested. This was not a failure in the final checker run; the final implementation returns hold.

## 5. Paired C0/C1 runs

All 10 external inputs are retained per run. `Both onset` is count with observed motion and RGB; the ≤1 s column is among observed only. `No both onset` and primary missing counts are reported separately; missing is not zero latency.

| Condition/seed | All inputs | Both onset | ≤1 s observed | No both onset | Max latency (s) | State transitions |
|---|---:|---:|---:|---:|---:|---:|
| C0/41 | 10 | 7 | 7 | 3 | .240 | 67 |
| C1/41 | 10 | 7 | 7 | 3 | .140 | 9 |
| C0/42 | 10 | 6 | 6 | 4 | .180 | 72 |
| C1/42 | 10 | 7 | 7 | 3 | .140 | 10 |
| C0/43 | 10 | 6 | 6 | 4 | .040 | 63 |
| C1/43 | 10 | 7 | 7 | 3 | .140 | 9 |

Primary expected set is seven IDs: `button_01`, `touch_01`, `approach_01`, `clear_01`, `near_01`, `clear_02`, `button_02`. C0 passes 19/21 with two missing; C1 passes 21/21. Across all 10 IDs, C0 has 19/30 both onsets and 11/30 no both onset; C1 has 21/30 and 9/30.

## 6. Event trace and independent latency calculation

| Condition / source | Source | Recognized | Decision | Actual apply | Motion onset | RGB onset | Both latency | Status |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| C0/41 `button_01` | 1.00 | 1.00 | 1.00 | 1.04 | 1.04 | 1.04 | .04 s | responded |
| C1/41 `button_01` | 1.00 | 1.10 | 1.10 | 1.14 | 1.14 | 1.14 | .14 s | responded |

Manual check C1: `max(1.14,1.14)−1.00=.14 s`, same as CSV `both_latency_s`. The extra .10 s before recognition is consistent with the .06 s debounce plus discrete .02 s model ticks. These are simulated command outputs, not hardware response times.

## 7. Conflict, fallback, and no-onset cases

- `touch_conflict` has no both onset in all six runs: C0 reports discarded priority (seeds 41/43) or preempted (42); C1 reports policy held in all seeds because afraid holds touch after near.
- `invalid_01` and `stale_01` yield `no_state_change` while neutral in all runs; thus there is no new onset.
- C0 `clear_01` at seed 42 is `filtered_not_recognized`; C0 `clear_02` at seed 43 is `no_state_change`.
- `discarded_priority`, `policy_held`, `preempted_before_apply`, `filtered_not_recognized`, and `no_state_change` identify different stages/causes. They are missing outcomes, not latency 0.
- Normal inactivity leads to sleepy in the model; active timeout returns interested/happy to normal. All five states were observed in every run.

## 8. Replay/source comparison

The original and rerun manifests agree for config, source inputs, raw CSVs, events, metrics, and traces; checked output hashes are identical. The source snapshot hashes also match the original manifest, so the re-run does not indicate a policy/config/source-version difference.

## 9. Limitations and deliverables

All results are deterministic proposed course-model simulations using three synthetic seeds, not independent physical trials. Motion/RGB onset means a simulated command changed after application; there was no robot/LED/actuator, torque or collision measurement, hardware safety certification, gait test, or learning.

Raw input, config, policy snapshot, metrics, raw/event CSVs, plots, and HTML report are preserved under `results/lab06_complete_20261111/`. The transition checker passed all 40 baseline pairs.
