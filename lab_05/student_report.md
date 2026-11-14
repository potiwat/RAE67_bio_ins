# Lab 05 — Hormone → SO(2) CPG → Kinematic Walking

## ข้อมูลผู้จัดทำและขอบเขต

- ชื่อ: ภาณุพร มาศรี
- รหัสนักศึกษา: 6752500118
- กลุ่ม: —
- Python: 3.12.10
- วันที่บันทึกคำทำนาย: 2026-11-14
- สถานะตอนบันทึกส่วนนี้: ยังไม่ได้เปิดผล comparison, one-factor, fault หรือ contact demo

โครงสร้างที่ศึกษาเป็น `S → controller → R_used → phi/stride → SO(2) CPG → tripod decoder → kinematic body` โดย contact ใน main runner มาจากเครื่องหมายของ CPG ไม่ใช่ sensor feedback อิสระ ทุก parameter และสมการ Euler เป็น proposed course model ที่ใช้ทดสอบแนวคิดจากงานอ้างอิง ไม่ใช่การจำลอง MNLC หรือผลหุ่นยนต์ในบทความซ้ำ

ค่าควบคุมที่ตรึงไว้ทุก condition คือ `dt=0.05 s`, `duration=30 s`, `alpha=1.10`, `lift=0.03 m`, oscillator เริ่มจาก `(0.10,0)` และใช้ warmup เดียวกัน 10 s. Stimulus เป็น 0 ช่วง 0–10 s, เป็น 1 ช่วง 10–20 s แล้วกลับเป็น 0 ช่วง 20–30 s

## คำทำนายก่อนทดลอง

1. B1 เป็น direct path จึงควรเปลี่ยน command ที่เวลา 10.00 s ทันที ส่วน B2/B3 ควรมี command latency, ค่อย ๆ เพิ่ม และค่อย ๆ recovery หลัง 20 s
2. B3 ตัด binding แต่ยังมี hormone state และ clearance จึงยังมี memory และน่าจะทำให้ hormone influence สูงหรือนานกว่า B2
3. เลือก `phi-only` เป็น one-factor run โดยตรึง stride_half ที่ 0.055 m คาดว่าความถี่และระยะจะเปลี่ยนตาม phi แต่ stride TV ต้องเป็นศูนย์
4. Contact demo: matched น่าจะมี SI สูงและ absolute error ต่ำ; gain-offset ยังมี SI สูงแต่ error ไม่เป็นศูนย์; mixed-delay น่าจะทำให้ SI ลดลง/ต่างกันระหว่างขา; all-inverted น่าจะมี SI ติดลบแต่ population dispersion ต่ำ; constant ต้องเป็น N/A เพราะ variance เป็นศูนย์ ไม่ใช่ SI=0

ตัวชี้วัดหลักคือ command latency/recovery, max command step, on-segment frequency/distance และ contact SI/SIF/error โดยไม่ใช้ TV หรือ support count แทน stability/energy ซึ่งไม่ได้วัดในแบบจำลองนี้

## วิธีทดลองและผล

รันจากโฟลเดอร์ `lab_05` ด้วยคำสั่งต่อไปนี้ ผลทุกชุดเก็บ config, raw CSV, metrics, report และ manifest แยกกัน

```powershell
py -3 lab05.py --condition all --profile step --mapping both --output-dir results\double_comparison
py -3 lab05.py --mapping phi-only --output-dir results\double_phi_only
py -3 lab05.py --condition all --profile fault --output-dir results\double_fault
py -3 contact_demo.py --output-dir results\double_contact
```

### Comparison และเวลา

ทุก condition เริ่ม CPG ที่ `o1=-0.0269653, o2=-0.560863` เหมือนกัน มี 601 state rows และ 600 intervals. ผลช่วง on ใช้เฉพาะ [10,20) ไม่เฉลี่ยรวม transient ของทั้ง 30 s

| condition | TV phi (rad) | max Δphi/step (rad) | TV stride (m) | cmd latency (s) | cmd recovery (s) | on frequency (Hz) | on distance (m) |
|---|---:|---:|---:|---:|---:|---:|---:|
| B0 | 0.0000 | 0.000 | 0.0000 | N/A | N/A | 0.6249 | 0.7787 |
| B1 | 0.4000 | 0.200 | 0.0200 | 0.00 | 0.00 | 1.2684 | 1.8252 |
| B2 | 0.3998 | 0.008 | 0.0200 | 0.15 | 2.85 | 1.2028 | 1.7063 |
| B3 | 0.3995 | 0.008 | 0.0200 | 0.15 | 3.80 | 1.2258 | 1.7275 |

การตรวจ B2 จาก interval CSV แสดงลำดับคำนวณดังนี้

| command/input time (s) | state end (s) | H start | H end | R used | phi (rad) | stride half (m) |
|---:|---:|---:|---:|---:|---:|---:|
| 10.00 | 10.05 | 0.0000 | 0.0400 | 0.0000 | 0.2000 | 0.0550 |
| 10.05 | 10.10 | 0.0400 | 0.0784 | 0.0400 | 0.2080 | 0.0554 |
| 20.00 | 20.05 | 0.9997 | 0.9597 | 0.9997 | 0.3999 | 0.0650 |

B1 มี command latency=0 เพราะใช้ `S_k` โดยตรงที่ 10.00 s แต่ state log เป็น post-update จึงมี state latency=0.05 s. B2/B3 ใช้ hormone state ต้น interval จึงค่อยเปลี่ยนคำสั่งตาม R

### One-factor และ fault

ใน `phi-only` ค่า stride_half คงที่ 0.055 m และ stride TV เป็น 0 ทุก condition ตามที่ประกาศไว้ ความถี่ช่วง on ของ B1/B2/B3 ยังเป็น 1.2684/1.2028/1.2258 Hz เท่ากับ both-mapping เพราะ CPG รับ phi เหมือนเดิม แต่ระยะช่วง on ลดจาก 1.8252/1.7063/1.7275 m เป็น 1.5491/1.4672/1.4778 m เมื่อไม่มีการเพิ่ม stride

สำหรับ B2 fault ที่ command time 15.00 s พบ `fault=1`, `H_used=R_used=0`, phi=0.20 rad และ stride_half=0.055 m ก่อน CPG update; state ที่ 15.05 s มี H=0 และ interval 15.05–15.10 s จึงเริ่มสะสมใหม่จน H=0.0400. ลำดับนี้ยืนยันว่า fallback เกิดก่อน command ไม่ใช่หลังจากส่งค่าผิดไปแล้ว

### Contact mini-lab

SI เป็น paired Pearson แบบ proposed course definition บนหน้าต่าง 50 samples; แถวแรกที่ valid คือ 2.45 s. ค่า SI ในตารางเป็นค่าเฉลี่ยต่อขาโดยย่อ

| case | SI โดยทั่วไป | mean SIF | mean absolute error | valid rows | ข้อสังเกต |
|---|---|---:|---:|---:|---|
| matched | ทุกขา 1.000 | 0.000 | 0.000 | 551 | รูปร่างและขนาดตรงกัน |
| gain-offset | ทุกขา 1.000 | ≈0.000 | 0.1628 | 551 | correlation ไม่เห็น gain/offset error |
| mixed-delay | 3 ขา 1.000, 3 ขา ≈0 | 0.5000 | 0.2260 | 551 | ความล่าช้าทำให้ SI ระหว่างขาแยกกัน |
| all-inverted | ทุกขา -1.000 | ≈0.000 | 0.6314 | 551 | ทุกขาผิดเหมือนกันจึง dispersion ต่ำ |
| constant | N/A ทุกขา | N/A | 0.000 | 0 | variance เป็นศูนย์ จึงคำนวณ SI ไม่ได้ |
| fault | valid SI=1.000 | 0.000 | 0.000 | 501 | NaN หนึ่ง sample ทำให้เพิ่ม 50 unavailable windows |

กรณี all-inverted แสดงข้อจำกัดสำคัญ: SIF เป็น population dispersion ไม่ใช่ค่าความถูกต้องรวม เมื่อ SIF=0 สมการ release ให้ 0.5 แม้ทุกขาจะมี SI=-1 ส่วน constant ต้องเก็บเป็น N/A ไม่แทนด้วยศูนย์

## วิเคราะห์ผลและข้อจำกัด

ผลสนับสนุนคำทำนายเรื่องเวลา B1 เปลี่ยนทันที ขณะที่ B2/B3 มี latency 0.15 s และ max Δphi ต่อ step เพียง 0.008 rad เทียบกับ 0.2 rad ของ B1. B3 มี AUC H=10.7547 H·s และ recovery=3.80 s สูงกว่า B2 ที่ 9.9996 H·s และ 2.85 s จึงสนับสนุนว่าการตัด binding ทำให้อิทธิพลของ hormone อยู่นานขึ้นภายใต้ model นี้

อย่างไรก็ตามผลที่ไม่ต่างตามความเข้าใจแบบง่ายคือ phi TV รวมของ B1, B2 และ B3 ใกล้ 0.4 rad ทั้งหมด แม้ B2/B3 จะค่อย ๆ เปลี่ยน เพราะ TV วัดผลรวมของเส้นทางขึ้นและลง ไม่ได้วัดความกระชาก จึงต้องดู max step และ trace ร่วมกัน Contact demo ก็แสดง null/negative findings ชัดเจน: gain-offset มี SI=1 ทั้งที่ error ไม่เป็นศูนย์ และ constant ให้ SI=N/A

ระยะและความเร็วเป็นผลของ kinematic body เท่านั้น ส่วน support legs=3 ตลอดไม่ได้พิสูจน์ stability เพราะไม่มี CoM, support polygon, contact force, actuator dynamics หรือ terrain feedback. Metric Stability/Harmony/Displacement ของบทความจึงเป็น N/A และไม่ควรถูกแทนด้วย TV, support count หรือ distance ของ runner นี้ Fault policy เป็น software fallback ที่ deterministic; ก่อนใช้กับหุ่นจริงยังต้องมี independent sensor validation, actuator limits, watchdog และการทดสอบ hardware safety เพิ่มเติม
