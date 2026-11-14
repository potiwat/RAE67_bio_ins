# Lab 07 — Seven-topic Interface and Offline Transport

## ข้อมูลผู้จัดทำและขอบเขต

- ชื่อ: ภาณุพร มาศรี
- รหัสนักศึกษา: 6752500118
- กลุ่ม: —
- Python: 3.12.10
- วันที่บันทึกคำทำนาย: 2026-11-14
- สถานะตอนบันทึกส่วนนี้: ยังไม่ได้รัน offline paired trials หรือเปิด metrics

การรันในรายงานนี้เป็น Python process เดียวบน Windows ใช้เวลาเสมือน ไม่ใช่ ROS/DDS benchmark และไม่ใช่ผลจากหุ่นยนต์จริง ทุก application topic ใช้ QoS `RELIABLE, KEEP_LAST depth 10, VOLATILE` ตาม interface รายวิชา

| Topic | Type | หน่วย/ความหมาย |
|---|---|---|
| `/lamp/input/button` | `Bool` | true/false |
| `/lamp/input/touch` | `Bool` | true/false |
| `/lamp/input/distance` | `Float32` | เมตร |
| `/lamp/interaction` | `String` | event หรือค่าว่าง |
| `/lamp/emotion` | `String` | normal/interested/happy/afraid/sleepy |
| `/lamp/servo_command` | `Float32MultiArray` | rad; `[tilt, extend, nod]` |
| `/lamp/rgb_command` | `ColorRGBA` | RGB normalized 0–1, alpha=1 |

เวลามีหลาย boundary ที่ห้ามรวมกัน: acquisition คือ sensor สร้างข้อมูล, receipt คือ adapter รับ message, decision คือ FSM เลือก state, applied software output คือ command ผ่าน scheduler แล้ว ส่วน physical onset ต้องวัดการเคลื่อนจริง/แสงจริงด้วยอุปกรณ์ภายนอก การทดลอง offline วัดได้ถึง applied software output เท่านั้น

Primary denominator ประกาศไว้ 7 IDs เหมือน Lab 06: `button_01`, `touch_01`, `approach_01`, `clear_01`, `near_01`, `clear_02`, `button_02` โดยเก็บ all 10 sources และ missing reasons ไว้ด้วย

## คำทำนายก่อนทดลอง

1. C1 ที่รวม modeled delay, random drop และ burst drop น่าจะเพิ่ม software-output latency/ความแปรปรวน และเพิ่ม missing responses เมื่อเทียบกับ C0 ideal transport
2. C0/C1 ใช้ policy และ paired source stimuli เดียวกัน จึงควรรักษากฎ transition เดิม แต่ message ที่มาช้าหรือหายอาจทำให้เวลาหรือ state sequence ที่สังเกตได้ต่างกัน
3. invalid/stale probes ที่ตั้งใจใส่ทั้งสอง condition ต้องแยกจาก communication stress และ dropped, censored, out-of-order ต้องไม่ถูกรวมเป็นสถานะเดียว
4. C1 เปลี่ยน jitter และ drop พร้อมกัน จึงสรุปได้เฉพาะผลของ combined profile ไม่สามารถชี้สาเหตุแยกว่ามาจาก jitter หรือ drop
5. Offline 22 s ใช้ตรวจ protocol/replay เท่านั้น ไม่ได้ validate proposal AHM–CPG, ROS transport หรือ human–robot scenario 600 s

## วิธีทดลองและผล

Policy checker ผ่านทั้ง baseline/group แบบ 40/40 และ `check_proposal.py` รายงานว่า fields complete จากนั้นรัน

```powershell
py -3 offline_lab.py --condition all --repeats 3 --output-dir results\double_completed
py -3 offline_lab.py --condition C1 --repeats 1 --replay results\double_completed\C1_r02\input_trace.csv --output-dir results\double_replay
```

แต่ละ trial publish 3,303 messages และมี 1,101 ticks ตารางคง dropped, censored และ received/out-of-order แยกกัน โดย `received = accepted + out-of-order`

| condition / seed | received | dropped | censored | accepted | out-of-order | mean age (s) | fault ticks | transitions |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| C0 / 41 | 3303 | 0 | 0 | 3303 | 0 | 0.0000 | 20 | 9 |
| C1 / 41 | 3031 | 257 | 15 | 1618 | 1413 | 0.0769 | 54 | 17 |
| C0 / 42 | 3303 | 0 | 0 | 3303 | 0 | 0.0000 | 20 | 10 |
| C1 / 42 | 3007 | 287 | 9 | 1586 | 1421 | 0.0779 | 81 | 36 |
| C0 / 43 | 3303 | 0 | 0 | 3303 | 0 | 0.0000 | 20 | 9 |
| C1 / 43 | 2991 | 300 | 12 | 1598 | 1393 | 0.0765 | 56 | 17 |

C0 มี fault ticks 20 จาก invalid/stale probes ที่ใส่เหมือนกันทุก condition ไม่ใช่ communication fault. C1 มีเพิ่มจาก combined transport profile และมี max modeled transport age 0.18 s ทุก seed

ผล primary seven-ID denominator และ applied software-output latency เป็นดังนี้

| condition / seed | pass ≤1 s | missing | median both latency (s) | max both latency (s) | primary missing reason |
|---|---:|---:|---:|---:|---|
| C0 / 41 | 7/7 | 0 | 0.04 | 0.14 | — |
| C1 / 41 | 6/7 | 1 | 0.15 | 0.20 | `clear_02` ไม่ถูก recognize |
| C0 / 42 | 7/7 | 0 | 0.06 | 0.14 | — |
| C1 / 42 | 6/7 | 1 | 0.14 | 0.22 | `button_02` ไม่ถูก recognize |
| C0 / 43 | 7/7 | 0 | 0.04 | 0.14 | — |
| C1 / 43 | 7/7 | 0 | 0.10 | 0.18 | — |

All 10 sources ยังรวม `touch_conflict`, `invalid_01` และ `stale_01`; ค่า both latency ของรายการที่ไม่สร้าง expression ใหม่เก็บเป็น N/A ไม่ใช่ศูนย์ ผล C1 seed 42 เช่น `touch_01` มี applied both latency 0.22 s ขณะที่ `button_02` เป็น N/A เพราะไม่มี recognized event

### Replay

Replay อ่าน input/config ของ C1 seed 42 และได้ trace ตรงกันแบบ byte-for-byte:

| file | SHA-256 | result |
|---|---|---|
| `input_trace.csv` | `e9e6f18065ad9ea07c987f36616950259920861f5c75289623c11a06b7a45878` | match |
| `command_trace.csv` | `95706888882f4cf1cf2d7aac7ed3d5c65e8a2ea9661ecc5c7c6aed46de0f54b2` | match |
| `events.csv` | `52041baedac19711d654078306c5d281b9d8058ff749e2540044392623d1569d` | match |

`metrics.json` มีเนื้อหาผลเท่ากันหลังตัด field `repeat`: ต้นฉบับระบุ repeat 2 แต่ output replay เป็น repeat 1 ตามตำแหน่งใน run ใหม่ จึงเป็น metadata difference ที่คาดไว้ ไม่ใช่ความต่างของ simulation

### Proposal ที่ยังไม่ได้ทดลองจริง

`proposal.json` วางแผน AHM → SO(2) CPG → nod ภายใต้ ideal เทียบ combined jitter/drop, 12 paired repeats ต่อ condition และ human scenario 600 s พร้อม UUID/clock error bound, calibration, consent, counterbalancing และ hardware emergency stop. ส่วนนี้เป็น future plan; offline runner ข้างต้นไม่มี AHM/CPG, ROS/DDS, participant หรือ physical lamp

## อภิปรายผลและข้อจำกัด

C1 มี median applied latency 0.10–0.15 s เทียบ C0 0.04–0.06 s และเกิด primary miss 2 จาก 21 paired expected responses ขณะที่ C0 ไม่มี miss จึงสนับสนุนคำทำนายว่าผลรวมของ stress profile ทำให้ช้าหรือหายมากขึ้นใน scaffold นี้ State transitions ของ C1 เพิ่มเป็น 17–36 แม้ใช้ policy เดียวกัน เพราะลำดับ message ที่ accepted/stale เปลี่ยน; กฎ FSM ไม่เปลี่ยนแต่ event sequence ที่ป้อนเข้าเปลี่ยน

อย่างไรก็ตาม C1 seed 43 ยังผ่าน 7/7 เป็น negative/null result ว่า combined profile ไม่ได้ทำให้ primary response หายทุก repeat และจำนวนเพียงสาม synthetic paired seeds ไม่พอประมาณผลบนระบบจริง ที่สำคัญคือ C1 เปลี่ยน delay และ drop พร้อมกัน จึงห้ามสรุปว่าตัวใดเป็นสาเหตุเฉพาะ ต้องเพิ่ม delay-only และ drop-only conditions หากต้องการแยกผล

เวลาที่รายงานเป็น virtual source-to-applied-command onset ใน process เดียว ไม่ใช่ ROS source latency หรือ physical response time. Topic types ไม่มี Header/UUID จึงห้ามจับคู่ข้าม node จาก payload/ลำดับโดยเดา และ source latency ต้องเป็น N/A เมื่อไม่มี identity/clock map การทดลองจริงต้องมี stamped wrapper/sidecar, clock correlation พร้อม error bound, camera/encoder สำหรับ motion และ photodiode สำหรับ RGB ตาม proposal ก่อนอ้าง latency ของหุ่นยนต์
