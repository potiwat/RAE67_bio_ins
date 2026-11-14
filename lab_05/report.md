# Lab 05 — Hormone → SO(2) CPG → Kinematic Walking

## คำถามและ prediction ก่อนรัน

คำถามคือ scheduled hormone path ใน B2/B3 เปลี่ยน command, CPG และการเคลื่อนที่เทียบกับ fixed B0 และ direct B1 อย่างไร โดยใช้ timing convention เดียวกัน คาดว่า B1 จะเปลี่ยน command ทันทีที่ stimulus เข้า ส่วน B2/B3 จะตอบสนองหลัง H สะสม; การตัด binding ใน B3 อาจทำให้ H คงอยู่/ฟื้นช้ากว่า B2 คาดว่า mapping แบบ phi-only จะเปลี่ยนความถี่มากกว่า stride-only ส่วน stride-only จะเปลี่ยนระยะก้าวโดยไม่เปลี่ยน phase increment

## วิธีการและ provenance

ใช้ proposed course model ใน `course_model.py` ไม่ใช่การทำซ้ำ MNLC, hormone-to-MI recurrence, terrain dynamics หรือผลหุ่นยนต์จาก paper ไม่มี random noise; แต่ละ condition เป็น deterministic run เดียว ไม่ใช่ independent repeated trials

ค่าคงที่: `dt=0.05 s`, duration `30 s`, warmup `10 s`, `α=1.10`, lift `0.03 m`; stimulus `0,1,0` ช่วงละ 10 s. B0 ใช้ fixed `R=0`, B1 ใช้ direct `R=S`, B2 ใช้ hormone rates `(k_prod,k_clear,k_bind)=(0.8,0.6,0.2)`, B3 ตัด binding (`k_bind=0`). รัน comparison, phi-only, stride-only, zero/one/spike/fault profiles และ contact mini-lab ทุก output เก็บ source/config/metrics/CSV และ HTML ไว้ใน `results/lab05_complete_20261111/`.

## ผล comparison

| Condition | Distance (m) | Mean speed (m/s) | Peak H | Command latency (s) | Recovery (s) | φ TV (rad) | max Δφ/step (rad) | stride TV (m) | on frequency (Hz) | on distance (m) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| B0 | 2.332679 | 0.077756 | N/A | N/A | N/A | 0.000000 | 0.000 | 0.000000 | 0.624877 | 0.778743 |
| B1 | 3.377516 | 0.112584 | N/A | 0.000 | 0.000 | 0.400000 | 0.200 | 0.020000 | 1.268366 | 1.825152 |
| B2 | 3.382580 | 0.112753 | 0.999715 | 0.150 | 2.850 | 0.399827 | 0.008 | 0.019991 | 1.202760 | 1.706250 |
| B3 | 3.460133 | 0.115338 | 1.000000 | 0.150 | 3.800 | 0.399534 | 0.008 | 0.019977 | 1.225791 | 1.727498 |

B1’s direct command latency is 0 by definition; logged state latency is 0.05 s because states are post-update. B2/B3 command latency is 0.15 s at the 0.05 s sampling resolution. B2 recovery is 2.85 s and B3 3.80 s. B3 reached its upper H clamp on 25.83% of updates; B2’s fraction was 0. Command clamps were 0 for all comparison conditions. All runs had 3 support legs in each reported segment, but decoder support count is not a stability test.

## One-factor and fault tests

| Mapping | B1 speed (m/s) | B2 speed (m/s) | B2 φ TV (rad) | B2 stride TV (m) |
|---|---:|---:|---:|---:|
| both | 0.112584 | 0.112753 | 0.399827 | 0.019991 |
| phi-only | 0.103310 | 0.103911 | 0.399827 | 0 |
| stride-only | 0.082283 | 0.082451 | 0 | 0.019991 |

This agrees with the parameter isolation: phi-only holds stride at baseline; stride-only holds φ at baseline. Both mappings use the same bounds, but the output trajectories and speed are not identical.

For B2, zero profile yielded peak H=0 and zero φ/stride total variation; one profile reached peak H≈1; a single-sample spike produced peak H=0.04, φ TV=0.016 rad and stride TV=0.0008 m. Fault profile logged one fault per condition; B2 reset before the command interval and recovered through the specified software policy. These are software-model observations, not safety certification.

## Contact mini-lab

| Case | Valid SIF rows / 600 | Mean SI (LF) | Mean SIF | Mean absolute error |
|---|---:|---:|---:|---:|
| matched | 551 | 1.000 | 0.000 | 0.000000 |
| gain-offset | 551 | 1.000 | ≈0 | 0.162844 |
| mixed-delay | 551 | 1.000 | 0.499995 | 0.226007 |
| all-inverted | 551 | −1.000 | ≈0 | 0.631375 |
| constant | 0 | N/A | N/A | 0.000000 |
| fault | 501 | 1.000 | 0.000 | 0.000000 |

Pearson correlation is invariant to positive affine gain/offset, so gain-offset still has SI=1 despite nonzero absolute error. All-inverted has SI=−1 for each leg, but SIF (population SD across legs) is approximately zero because every leg errs identically; Eq.(1) with CI=1 therefore releases `0.5`, not proof of correct contact. Constant signals have zero variance, so SI is unavailable rather than 0. The fault makes 50 additional rolling windows unavailable beyond the 49 startup rows. The paired-product Pearson definition is explicitly a proposed course definition; the demo does not run Cg/MI recurrence.

## อภิปรายและข้อจำกัด

ผลสนับสนุนความต่างของ timing ระหว่าง direct และ hormone path และแสดงว่า binding ablation ใน model นี้มี recovery ยาวขึ้นกว่ากรณี B2. อย่างไรก็ตาม B2/B3 ไม่ได้ให้ peak command หรือ TV ที่ลดลงชัดเจนจาก B1; max-step และ time trace แสดงว่าการเพิ่มแบบค่อยเป็นค่อยไปเกิดที่แต่ละ update มากกว่า ดังนั้น TV เพียงค่าเดียวใช้สรุปความ smoothness ไม่พอ. Distance และ support เป็นผลจาก kinematic decoder ไม่ใช่การวัด stability, terrain contact, energy หรือ actuator tracking. ตัวเลขทุกตัวเป็นผลของ proposed course model ไม่ใช่การทดสอบหุ่นยนต์หรือ reproduction ของ paper.

รายงาน HTML ที่สร้างจาก runner พร้อม time-series และข้อมูลทดลอง:

- [comparison B0–B3](results/lab05_complete_20261111/comparison/report.html)
- [contact mini-lab](results/lab05_complete_20261111/contact/report.html)
- [phi-only](results/lab05_complete_20261111/phi_only/report.html)
- [stride-only](results/lab05_complete_20261111/stride_only/report.html)

คำสั่งหลัก:

```powershell
python lab05.py --condition all --profile step --mapping both --output-dir results\lab05_complete_20261111\comparison
python lab05.py --mapping phi-only --output-dir results\lab05_complete_20261111\phi_only
python lab05.py --mapping stride-only --output-dir results\lab05_complete_20261111\stride_only
python lab05.py --condition all --profile fault --output-dir results\lab05_complete_20261111\fault
python contact_demo.py --output-dir results\lab05_complete_20261111\contact
```
