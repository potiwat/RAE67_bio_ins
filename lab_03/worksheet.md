# ใบงาน Lab 03 SO(2) CPG และการเดินของหุ่นยนต์หกขา

ชื่อกลุ่ม: กลุ่ม 1  สมาชิก: ____________________ วันที่: 11/11/2026

## ส่วนที่ 1 Prediction ก่อนรัน

1. เมื่อเพิ่ม `φ` จาก 0.20 เป็น 0.40 rad ความถี่ที่วัดได้จะ เพิ่มขึ้น เพราะ การหมุน SO(2) เร็วขึ้น จึงลดช่วงเวลา/รอบของ oscillation และ shortening cycle period ทำให้เดินเร็วและมี frequency สูงขึ้น
2. เมื่อเพิ่ม `α` จาก 1.10 เป็น 1.30 แอมพลิจูดและ foot clearance จะ เพิ่มขึ้น เพราะ recurrent gain มากขึ้นทำให้ `a₁`, `a₂` เกินค่า `tanh` มากขึ้น ส่งผลให้ output สูงขึ้น และยกเท้าขึ้นมากกว่าเดิม
3. ขา Tripod A และ Tripod B ควรมี phase relation เท่ากับ 180° (π rad) หรือ opposite phase sign เพราะทั้งสอง tripod ต้องสลับกันเพื่อให้มี 3 ขารองรับเสมอ (alternating tripod)

## ส่วนที่ 2 ตรวจสมการหนึ่งรอบเวลา

กำหนด `o₁=0.10`, `o₂=−0.20`, `α=1.10`, `φ=0.20 rad`

คำนวณ:
- `c = cos(0.20) = 0.9800665778`
- `s = sin(0.20) = 0.1986693308`

| ตัวแปร | วิธีคำนวณ | ค่าที่ได้ |
|---|---|---:|
| `a₁(t+1)` | `1.10 * (0.9800666 * 0.10 + 0.1986693 * (-0.20))` | `0.06410007` |
| `a₂(t+1)` | `1.10 * (-0.1986693 * 0.10 + 0.9800666 * (-0.20))` | `-0.23746827` |
| `o₁(t+1)` | `tanh(0.06410007)` | `0.06401242` |
| `o₂(t+1)` | `tanh(-0.23746827)` | `-0.23310301` |

## ส่วนที่ 3 ผล gait comparison

| Condition | Speed (m/s) | Frequency (Hz) | Duty factor | Min support | Clearance (mm) |
|---|---:|---:|---:|---:|---:|
| baseline | 0.077756 | 0.625000 | 0.494176 | 3 | 17.095 |
| fast | 0.155511 | 1.267123 | 0.500832 | 3 | 17.113 |
| high_gain | 0.094457 | 0.544218 | 0.494176 | 3 | 24.637 |

ข้อสรุปที่อ้างจากข้อมูล: `fast` มี speed และ frequency สูงกว่าพื้นฐานประมาณ 2 เท่า เนื่องจาก `φ` เพิ่มขึ้นจาก 0.20 เป็น 0.40 rad ส่วน `high_gain` เพิ่ม foot clearance อย่างชัดเจน แต่ frequency ลดลงเล็กน้อยจาก 0.625 เป็น 0.544 Hz เพราะกฎ `tanh` ทำให้ output เกิน saturates และระยะ cycle ยาวขึ้นเล็กน้อย แม้ว่า clearances จะเพิ่มขึ้น แต่ minimum support ยังคง 3 ขาเสมอ เพราะ decoder ของ alternating tripod ยังคงบังคับให้มี 3 ขาใน stance ตลอดเวลา

ข้อจำกัดของ kinematic model: แบบจำลองนี้เป็น kinematic teaching model เท่านั้น ไม่ได้คำนึงถึง contact force, friction, motor torque, body dynamics หรือ dynamic stability ของหุ่นยนต์จริง จึงใช้ได้แค่การตรวจตรรกะของ timing, phase, and foot placement ไม่ใช่การยืนยันความมั่นคงหรือประสิทธิภาพจริงของหุ่นยนต์

## ส่วนที่ 4 Week 4 handoff

รัน `python week4_bridge.py --output-dir results\week4_bridge`

| ช่วงเวลา | `m(t)` | `φ command` | `stride command` | Speed | Frequency |
|---|---:|---:|---:|---:|---:|
| 0–10 s | 0.0 | 0.200000 | 0.055000 | 0.077632 | 0.625000 |
| 10–20 s | 1.0 | 0.400000 | 0.065000 | 0.183294 | 1.263158 |
| 20–30 s | 0.0 | 0.200000 | 0.055000 | 0.077387 | 0.625000 |

1. เหตุใด mapping ต้องมี bounds? เพราะค่า `m` อาจเกินช่วงที่เหมาะสมและหากไม่ clamp จะส่ง `φ` และ stride ให้เกิน operating envelope จน gait เป็นอันตรายหรือผิดจากแบบจำลอง จึงต้องมี bounds เพื่อให้ส่งต่อ Week 4 เป็น stable bounded interface
2. ใน Week 4 ตัวแปรใดจะมาแทน `m(t)`? hormone concentration หรือ receptor output จาก dynamics ของ production/decay/receptor จะเข้ามาแทนชุดคำสั่ง slow modulator `m(t)`
3. ถ้า hormone concentration เปลี่ยนช้ากว่า CPG คาดว่าจะเห็น transient อย่างไร? จะเห็น transient/lag แบบต่อเนื่อง: เมื่อ concentration เพิ่มขึ้น output จะค่อยๆ เปลี่ยนไปตามสัดส่วนและเมื่อลดลง output จะค่อยกลับสู่ baseline อย่างช้าๆ แทนที่จะสลับทันที
