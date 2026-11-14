# Lab 03 — SO(2) CPG และการเดินของหุ่นยนต์หกขา

## คำถามวิจัยและ prediction

ศึกษาว่า phase increment `φ` และ recurrent gain `α` เปลี่ยนความถี่ของ CPG และตัวชี้วัดการเดินใน kinematic simulator อย่างไร ก่อนรันคาดว่าเพิ่ม `φ` จาก 0.20 เป็น 0.40 rad จะเพิ่มความถี่และความเร็ว; เพิ่ม `α` จาก 1.10 เป็น 1.30 จะเพิ่ม amplitude และ foot clearance; tripod A/B ควรต่างเฟสกันประมาณ π rad เพราะใช้สัญญาณตรงข้ามกัน

## วิธีการ

เติม `student_cpg.py` ให้ใช้สมการ SO(2) แบบ simultaneous update, decoder สลับ tripod และ bounded mapping สำหรับ `φ`/stride ผล checker ผ่าน 5/5 ข้อ รวมการตรวจ simultaneous update และ bounds

รัน controlled comparison ที่ `dt=0.05 s`, duration `30 s`, warmup `10 s`, stride half `0.055 m`, lift height `0.030 m` และ initial condition เดียวกัน เปลี่ยน `φ` อย่างเดียวใน `fast` และเปลี่ยน `α` อย่างเดียวใน `high_gain` ตาม protocol จากนั้นรัน Week 4 bridge ที่กำหนด `m(t)=0,1,0` ช่วงละ 10 วินาที

## ผลการทดลอง

| Condition | α | φ (rad) | Speed (m/s) | Frequency (Hz) | Duty factor | Min support (ขา) | Clearance (mm) |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | 1.10 | 0.20 | 0.077756 | 0.625000 | 0.494176 | 3 | 17.095 |
| fast | 1.10 | 0.40 | 0.155511 | 1.267123 | 0.500832 | 3 | 17.113 |
| high_gain | 1.30 | 0.20 | 0.094457 | 0.544218 | 0.494176 | 3 | 24.637 |

เมื่อเพิ่ม `φ` เป็น 0.40 rad ความถี่เพิ่มประมาณ 2.03 เท่า และ speed เพิ่มประมาณ 2.00 เท่า ขณะที่ clearance ใกล้เดิม เมื่อเพิ่ม `α` เป็น 1.30 clearance เพิ่ม 7.542 mm จาก baseline และ speed เพิ่ม แต่ความถี่ลดลงเป็น 0.544218 Hz ผลนี้แสดงว่า `φ` ไม่ใช่ความถี่ที่วัดได้โดยตรง และ gain ที่สูงขึ้นไม่ได้รับประกันความถี่สูงขึ้น

ทั้งสาม condition มี support ต่ำสุดและสูงสุดเท่ากับ 3 ขา ซึ่งเป็นผลของ decoder ในแบบจำลอง ไม่ใช่หลักฐานด้าน dynamic stability

กราฟจากข้อมูล batch (เปิด SVG ได้โดยตรง):

- [baseline](results/lab03_complete_20261111/gait_comparison/baseline.svg)
- [fast](results/lab03_complete_20261111/gait_comparison/fast.svg)
- [high_gain](results/lab03_complete_20261111/gait_comparison/high_gain.svg)

## Week 4 handoff และอภิปราย

| ช่วงเวลา (s) | m(t) | φ command (rad) | stride half (m) | Speed (m/s) | Frequency (Hz) |
|---|---:|---:|---:|---:|---:|
| 0–10 | 0 | 0.20 | 0.055 | 0.077632 | 0.625000 |
| 10–20 | 1 | 0.40 | 0.065 | 0.183294 | 1.263158 |
| 20–30 | 0 | 0.20 | 0.055 | 0.077387 | 0.625000 |

การเปลี่ยน `m` กลับเป็น 0 ทำให้ mapping กลับค่าฐานที่ช่วง 20–30 s; oscillator ยังคงมีสถานะและค่าความเร็วช่วงนั้นใกล้ baseline แต่ไม่ตรงกันทุกหลักเพราะเป็น segment ของ trajectory ต่อเนื่อง ไม่ใช่การ reset gait ใหม่ การ mapping มี bounds เพื่อจำกัดคำสั่งพารามิเตอร์ ไม่ใช่การรับรอง mechanical/actuator safety; ใน Week 4 `m(t)` จะถูกแทนด้วย receptor output จาก hormone state

## ข้อจำกัดและสรุป

ผลสนับสนุน prediction ว่า `φ` เพิ่มแล้วความถี่เพิ่ม และ `α` เพิ่มแล้ว clearance เพิ่ม แต่ `α` ที่สูงขึ้นกลับลดความถี่ที่วัดได้ ผลเป็น deterministic kinematic teaching simulation ที่ใช้ foot-placement/contact rule ไม่ได้จำลอง rigid-body dynamics, contact force, friction, torque, energy หรือ actuator tracking จึงใช้สรุปการทรงตัวหรือสมรรถนะหุ่นยนต์จริงไม่ได้

คำสั่งรัน:

```powershell
python grade_submission.py --student-file student_cpg.py --out results\lab03_complete_20261111\my_grade.json
python cpg_walk_sim.py --condition all --output-dir results\lab03_complete_20261111\gait_comparison
python week4_bridge.py --output-dir results\lab03_complete_20261111\week4_bridge
```

ผลดิบ, summary, SVG, JSON และ handoff contract อยู่ใน `results/lab03_complete_20261111/`; configuration คือค่าที่ระบุใน protocol ข้างต้น
