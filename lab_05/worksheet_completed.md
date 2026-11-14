# Lab 05 — Worksheet answers from recorded runs

## 1. Hypothesis and architecture

Signal flow: `S → hormone/controller → R_used → φ/stride → SO(2) CPG → tripod decoder → kinematic body`. Main-runner contact comes from the decoder; no independent terrain/contact sensing feeds back into the controller.

Before running, expected B2 to respond after hormone accumulates while B1 responds directly at the stimulus boundary; expected B3 (no binding term) to recover more slowly than B2. Expected phi-only to change CPG frequency and stride-only to change commanded step length without changing φ.

B3 removes only the `k_bind R` term from the proposed Euler hormone model; H still has memory through its state and clearance term. Provenance: SO(2) update and decoder are carried from Lab 03; Euler hormone update and bounded `R→φ/stride` are proposed course equations; timing, command variation, and kinematic body displacement are measured by this runner. Paper stability/harmony and physical energy are not measured.

## 2. Timing check

Values below are from `comparison/B2_intervals.csv`, using command/input at `t_k` and state at `t_(k+1)`.

| command/input time (s) | state end time (s) | H_start | H_end | R_used | φ (rad) | stride_half (m) |
|---:|---:|---:|---:|---:|---:|---:|
| 10.00 | 10.05 | 0.000000 | 0.040000 | 0.000000 | 0.200000 | 0.055000 |
| 10.05 | 10.10 | 0.040000 | 0.078400 | 0.040000 | 0.208000 | 0.055400 |
| 20.00 | 20.05 | 0.999715 | 0.959727 | 0.999715 | 0.399943 | 0.064997 |

B1 uses direct `S_k`, so its command latency is 0 s; the first logged post-update state occurs at 10.05 s, giving a 0.05 s state-log offset. The initial oscillator in `config.json` is the same warmup output for every condition (`alpha=1.10`, `phi=.20`, 10 s warmup); H/R and body/log origins are reset after warmup.

## 3. Comparison results

| condition | φ TV (rad) | max Δφ/step (rad) | stride TV (m) | command latency (s) | command recovery (s) | on frequency (Hz) | on distance (m) |
|---|---:|---:|---:|---:|---:|---:|---:|
| B0 | 0.000000 | 0.000 | 0.000000 | N/A | N/A | 0.624877 | 0.778743 |
| B1 | 0.400000 | 0.200 | 0.020000 | 0.000 | 0.000 | 1.268366 | 1.825152 |
| B2 | 0.399827 | 0.008 | 0.019991 | 0.150 | 2.850 | 1.202760 | 1.706250 |
| B3 | 0.399534 | 0.008 | 0.019977 | 0.150 | 3.800 | 1.225791 | 1.727498 |

The slower per-step command change in B2/B3 is visible in `max Δφ/step`; total variation across the whole run is still close to direct B1, so TV alone does not establish smoothness or quality. Each condition has 3 decoded support legs, which does not demonstrate body stability or low energy. Bounds are shared, but command traces differ: B1 jumps to φ=.40 at stimulus onset; B2 approaches a peak φ=.399943 progressively. The on segment has transient dynamics, so the 30 s average frequency would hide pre/on/off differences.

The phi-only run held `stride_half=.055 m` constant; stride-only held `φ=.20 rad`. For B2, total mean speeds were 0.103911 m/s (phi-only), 0.082451 m/s (stride-only), and 0.112753 m/s (both mapping). These are model outputs, not a causal claim about a physical robot.

## 4. Fault

In the B2 fault run, the NaN stimulus at input/command 15.00 s was handled before command: `fault=1`, `R_used=0`, `φ=.20 rad`, `stride_half=.055 m`, and H/R reset to 0 at state time 15.05 s. The next valid input at 15.05 s generated H=R=.04 at 15.10 s. This fallback is software behavior in a proposed model; it does not certify hardware safety.

## 5. Contact mini-lab

| case | SI by leg (general) | SIF | absolute error | cannot infer |
|---|---|---:|---:|---|
| matched | all 6 ≈ +1 | 0 | 0 | physical contact or terrain stability |
| gain-offset | all 6 ≈ +1 | ≈0 | 0.162844 | amplitude agreement from correlation alone |
| mixed-delay | first 3 ≈ +1, delayed 3 ≈ 0 | 0.499995 | 0.226007 | terrain-level stability or paper MI output |
| all-inverted | all 6 ≈ −1 | ≈0 | 0.631375 | correctness from SIF alone |
| constant | N/A (zero variance) | N/A | 0 | correlation; it is not SI=0 |
| fault | five unaffected legs ≈ +1; LF windows unavailable around fault | 0 when valid | 0 | effect on a real sensor/controller |

Positive gain/offset preserves Pearson correlation although absolute error is nonzero. All-inverted produces the same negative SI on every leg, so population SD SIF is approximately zero; the release equation at SIF=0 yields 0.5. Constant input has zero variance, so SI is unavailable. The fault case has 99 unavailable SIF rows: 49 startup-window rows plus 50 rolling windows affected by the one-sample fault. The paired-product Pearson is a proposed course definition; this demo does not run Cg/MI_H.

## 6. Limitations

All data are deterministic synthetic model runs with a scheduled input; there are no independent trials. The kinematic decoder does not model force, slip, terrain feedback, body dynamics, actuator response, energy, or physical RGB/motor outputs. These results cannot be described as robot or paper results.
