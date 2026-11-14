# Lab 07 — Seven-topic interface and offline transport experiment

## Scope and research question

Lab07 pairs a seven-topic ROS 2 interface specification with an offline experiment and a forward-looking project proposal. The experiment run here is the **offline proposed course model**, a single-process replay with virtual time. It is not a ROS/DDS run, a physical robot test, the proposed AHM–CPG experiment, or a 600-second human-interaction trial.

The offline question is whether the modeled transport profile C1 changes delivery, ordering, fault handling, and observed simulated command onsets relative to ideal delivery C0. C1 combines variable delay, random drops, and a burst-drop interval; the design cannot attribute an effect to jitter or drop alone.

## Interface graph and contract

```text
Input source / scripted or calibrated sensors
  ├─ /lamp/input/button      std_msgs/Bool
  ├─ /lamp/input/touch       std_msgs/Bool
  └─ /lamp/input/distance    std_msgs/Float32 [m]
                  │
                  ▼
       Interaction / policy node
         FSM + guarded inputs
  ├─ /lamp/interaction       std_msgs/String
  ├─ /lamp/emotion           std_msgs/String
  ├─ /lamp/servo_command     std_msgs/Float32MultiArray
  └─ /lamp/rgb_command       std_msgs/ColorRGBA
                  │
                  ▼
        Output collector / driver boundary
                  │
        [future hardware extension]
       ROS 2 ↔ micro-ROS Agent ↔ ESP32
                  │
          calibrated servo + RGB lamp
```

The ROS package provides source, interaction, and collector roles, but this workspace has not run ROS 2 and does not provide an ESP32 firmware, micro-ROS Agent, motor driver, or calibrated robot. The graph's hardware-extension boundary is therefore a proposed architecture, not a tested connection.

| Topic | Message | Unit / meaning |
|---|---|---|
| `/lamp/input/button` | `std_msgs/msg/Bool` | true/false |
| `/lamp/input/touch` | `std_msgs/msg/Bool` | true/false |
| `/lamp/input/distance` | `std_msgs/msg/Float32` | m |
| `/lamp/interaction` | `std_msgs/msg/String` | recognized event name |
| `/lamp/emotion` | `std_msgs/msg/String` | normal/interested/happy/afraid/sleepy |
| `/lamp/servo_command` | `std_msgs/msg/Float32MultiArray` | rad, `[tilt, extend, nod]` |
| `/lamp/rgb_command` | `std_msgs/msg/ColorRGBA` | RGB channels integer/255 normalized to [0,1], alpha=1 |

The specified ROS endpoints use RELIABLE, KEEP_LAST depth 10, VOLATILE QoS. `extend` is a semantic joint name whose command is still radians; the physical linkage is not specified. None of the seven messages contains a Header, source ID, or acquisition timestamp. The offline sidecar can track identities and planned delivery, but that identity is not carried on the ROS wire.

## Protocol

Three paired source schedules used seeds 41, 42, and 43; each C0/C1 pair reuses its seed's same inputs. Each trial is 22 s, 0.02-s virtual ticks (1,101 ticks), and a 0.04-s modeled output scheduler delay.

- **C0:** ideal modeled delivery, no transport delay or drops.
- **C1:** delays selected from 0/.02/.04/.06/.10/.14/.18 s, random drop probability .08, and a burst-drop interval from 12.50 to 12.70 s.
- Both conditions share the policy, guarded sensor behavior, bounds/slew, scripted source inputs, and invalid/stale probes.
- Ten source input IDs are retained per run. The primary expected subset declared by the baseline is seven: `button_01`, `touch_01`, `approach_01`, `clear_01`, `near_01`, `clear_02`, `button_02`. `touch_conflict`, `invalid_01`, and `stale_01` are also retained but do not require a new expression onset.
- A both-onset is measured only when both simulated applied motion and RGB output change. Missing/censored events remain missing; they are not assigned zero latency.

## Results

| Pair / seed | Condition | Published | Received | Dropped | Out of order | Accepted | Fault ticks / 1,101 | State transitions | Primary pass ≤1 s / 7 | Missing / 7 | Median primary latency (s) | Max primary latency (s) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 / 41 | C0 | 3,303 | 3,303 | 0 | 0 | 3,303 | 20 | 9 | 7 | 0 | .04 | .14 |
| 1 / 41 | C1 | 3,303 | 3,031 | 257 | 1,413 | 1,618 | 54 | 17 | 6 | 1 | .15 | .20 |
| 2 / 42 | C0 | 3,303 | 3,303 | 0 | 0 | 3,303 | 20 | 10 | 7 | 0 | .06 | .14 |
| 2 / 42 | C1 | 3,303 | 3,007 | 287 | 1,421 | 1,586 | 81 | 36 | 6 | 1 | .14 | .22 |
| 3 / 43 | C0 | 3,303 | 3,303 | 0 | 0 | 3,303 | 20 | 9 | 7 | 0 | .04 | .14 |
| 3 / 43 | C1 | 3,303 | 2,991 | 300 | 1,393 | 1,598 | 56 | 17 | 7 | 0 | .10 | .18 |
| **Total** | **C0** | **9,909** | **9,909** | **0** | **0** | **9,909** | **60** | **9–10/run** | **21/21** | **0** | — | **.14** |
| **Total** | **C1** | **9,909** | **9,029** | **844** | **4,227** | **4,802** | **191** | **17–36/run** | **19/21** | **2** | — | **.22** |

In C1, received = accepted + out-of-order-discarded. A further 15, 9, and 12 deliveries were censored after the trial in seeds 41, 42, and 43 respectively; these are not counted as transport drops. Thus the raw trace distinguishes dropped, received-but-discarded, accepted, and post-window censored messages.

Latency outcomes for the seven primary IDs, in seconds (`N/A` means no both-onset observation):

| Seed | Condition | button_01 | touch_01 | approach_01 | clear_01 | near_01 | clear_02 | button_02 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 41 | C0 | .14 | .10 | .04 | .04 | .04 | .04 | .10 |
| 41 | C1 | .18 | .18 | .12 | .10 | .04 | N/A | .20 |
| 42 | C0 | .14 | .10 | .04 | .04 | .06 | .04 | .10 |
| 42 | C1 | .16 | .22 | .20 | .04 | .06 | .12 | N/A |
| 43 | C0 | .14 | .10 | .04 | .04 | .04 | .04 | .10 |
| 43 | C1 | .18 | .14 | .04 | .08 | .10 | .14 | .10 |

Across these paired synthetic runs, C1 had 844 dropped messages and 4,227 out-of-order discards; it had two missing primary outcomes compared with none in C0. The output shows behavior of this **combined synthetic profile** only, not a guarantee or benchmark for reliable ROS 2 QoS. Separate delay-only and drop-only experiments are needed to distinguish causes. Three deterministic synthetic seeds are not independent physical trials.

## Measurement boundary and limitations

Offline source-to-command latency uses known fixture identity/time and the first applied simulated servo and RGB changes. Real ROS messages have no Header or input ID, and the offline acquisition timestamp is not present on the ROS wire. A future real setup must propagate identity in a logging wrapper, record clock synchronization markers and drift/error bounds across host/MCU/video clocks, and directly measure physical actuator onset (for example encoder or synchronized video). Message receipt or ROS bag time alone is not physical motion latency.

The C0/C1 transport run does **not** implement the future proposal's AHM–CPG comparison. The proposed 600-s human scenario, ROS 2 Jazzy nodes, ESP32/micro-ROS integration, hardware calibration, actuator/LED response, and emergency-stop tests were not performed. All poses, thresholds, delay/drop parameters, and motion outputs are proposed course model values, not certified hardware values.

## Proposal status

The existing [proposal.json](proposal.json) covers a future bounded AHM-to-SO(2)-CPG integration with two conditions, two metrics, three paired repeats per condition, clock/safety plans, and a 600-s human scenario. The proposal checker passes; its output explicitly leaves scientific validity for lecturer review. The robot, human, and integrated AHM–CPG studies remain planned, not observed results. See [proposal.md](proposal.md) for the readable protocol.

## Reproducibility and files

- [HTML experiment report](results/lab07_redo_20261111/report.html)
- [Saved report screenshot](results/lab07_redo_20261111/report_screenshot.png)
- [Summary metrics](results/lab07_redo_20261111/summary.json)
- [SHA-256 manifest](results/lab07_redo_20261111/manifest.json)
- Per-trial directories contain `input_trace.csv`, `command_trace.csv`, `events.csv`, `metrics.json`, `config.json`, and source snapshots.

The existing results and their manifest were preserved. Do not edit them; rerun only to a new output directory.
