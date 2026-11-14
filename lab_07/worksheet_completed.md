# Lab 07 — Completed worksheet

**Group/date:** Not inferred from the repository; fill in before submission.  
**Policy:** `lamp_week07/student_policy.py`, validated under baseline and group contracts (40/40 transition pairs each).

## 1. Architecture, roles, and seven topics

```text
Input source/sensors
   → interaction + policy/FSM node
   → output collector / driver boundary
   → proposed ROS 2–micro-ROS Agent–ESP32 extension
   → calibrated servos and RGB lamp
```

The hardware-extension path is a proposal only. The offline runner is not ROS and no ESP32, Agent, motor driver, or physical lamp test was performed.

| Topic | ROS type | Unit / value |
|---|---|---|
| `/lamp/input/button` | `std_msgs/msg/Bool` | true/false |
| `/lamp/input/touch` | `std_msgs/msg/Bool` | true/false |
| `/lamp/input/distance` | `std_msgs/msg/Float32` | m |
| `/lamp/interaction` | `std_msgs/msg/String` | event name |
| `/lamp/emotion` | `std_msgs/msg/String` | normal/interested/happy/afraid/sleepy |
| `/lamp/servo_command` | `std_msgs/msg/Float32MultiArray` | rad `[tilt,extend,nod]` |
| `/lamp/rgb_command` | `std_msgs/msg/ColorRGBA` | RGB/255 normalized, alpha=1 |

Specified QoS is RELIABLE, KEEP_LAST depth 10, VOLATILE. Example conversion: RGB `(40,220,80)` becomes `(40/255, 220/255, 80/255, 1)`. `extend` is semantic; its radians cannot be mapped to a physical linkage until calibrated.

## 2–4. Question, protocol, results, and denominator

Offline question: how does the modeled combined transport profile C1 compare with ideal delivery C0? The primary IDs were fixed as `button_01`, `touch_01`, `approach_01`, `clear_01`, `near_01`, `clear_02`, `button_02`; all ten source outcomes, including the three non-primary conflict/fault inputs, were retained.

| Pair/seed | C0 received/dropped/out-of-order | C1 received/dropped/out-of-order | C0/C1 primary pass / 7 | C0/C1 missing / 7 | C0/C1 transitions | C0/C1 median / max latency (s) |
|---|---|---|---|---|---|---|
| 1/41 | 3303/0/0 | 3031/257/1413 | 7 / 6 | 0 / 1 | 9 / 17 | .04/.14 · .15/.20 |
| 2/42 | 3303/0/0 | 3007/287/1421 | 7 / 6 | 0 / 1 | 10 / 36 | .06/.14 · .14/.22 |
| 3/43 | 3303/0/0 | 2991/300/1393 | 7 / 7 | 0 / 0 | 9 / 17 | .04/.14 · .10/.18 |

Totals: C0 21/21 primary deadlines passed, no primary missing; C1 19/21 passed, two missing. C1 received 9,029/9,909 publishes, with 844 transport drops and 4,227 out-of-order discards. Accepted = received minus out-of-order discards. C1 additionally had 15/9/12 messages censored after the trial window by seed; these are not drops.

**Interpretation:** C1's combined delay/drop profile had lower acceptance and two primary missing onsets in this sample. Because jitter, random drop, and burst drop change together, this run cannot determine which transport factor caused the difference. These are three synthetic paired seeds, not independent human or hardware trials.

## 5. Invalid/stale probe versus transport stress

The invalid and stale acquisition probes are shared inputs in both conditions; in offline mode acquisition sample time is known from the fixture, so they contribute fault ticks. The C1 transport profile separately models variable delivery delay, random drops, and a burst-drop interval. Since C1 changes delay and loss together, separate delay-only/drop-only runs are needed for causal attribution. C1's accepted count also excludes out-of-order deliveries; a delayed older sample is not allowed to roll back the latest accepted value.

## 6. Timestamp and measurement limitations

The seven ROS messages have no Header or source input ID. ROS receipt freshness does not reveal the original sensor acquisition time; repeated old sensor values can arrive recently and appear fresh. The offline sidecar knows fixture IDs/times, but this does not prove the ROS wire carries them. Future measurement plan: add a source/logging wrapper with stable IDs, keep timestamps on one monotonic host clock where possible, record synchronization markers before/after trials for MCU/video clocks, estimate offset/drift/error bounds, and measure physical servo onset via encoder or synchronized video. If identity/clock error exceeds the preregistered tolerance, mark latency unavailable rather than infer across clocks or ordinal events.

## 7. Proposal and study-status checklist

- [x] Seven-topic contract, units, and QoS described.
- [x] Policy checker passed under both baseline and group contracts (40 transition pairs each).
- [x] Offline config, raw traces, metrics, source snapshot, SHA-256 manifest, HTML, and screenshot retained.
- [x] Three paired synthetic seeds; all misses and censored messages retained.
- [x] Proposal JSON checker passed, including two conditions, two metrics, at least three repeats, and human scenario duration 600 s.
- [ ] ROS 2/DDS execution, micro-ROS/ESP32 integration, robot calibration, physical latency, and safety-stop bench test remain unperformed.
- [ ] Proposed 600-s human scenario remains unperformed and requires approval/consent and safety review.
- [ ] Integrated AHM–SO(2)-CPG implementation and its proposed simulation comparison are not part of this Lab07 offline transport run.

The readable proposal is in [proposal.md](proposal.md); the machine-readable plan is [proposal.json](proposal.json).
