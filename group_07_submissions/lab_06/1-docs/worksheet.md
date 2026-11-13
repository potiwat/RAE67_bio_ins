# ใบงาน Lab06 — Student

**แบบจำลองทั้งหมดใน runner เป็น proposed course model** โปรแกรมเป็น simulation ไม่ใช่ข้อมูลจาก robot และไม่มี learning

1. เขียน prediction ก่อนรัน: bounce/noise จะกระทบ C0 กับ C1 อย่างไร และ input ใดควรไม่มี onset ใหม่
2. วาด FSM ที่มี normal/interested/happy/afraid/sleepy พร้อม entry/exit guard timeout/recovery
3. ทำตาราง5 state ×8 event (fault, near, clear, touch, button, approach, timeout, idle) โดยเขียน next state หรือ hold ในแต่ละช่อง ตรวจ priority และเหตุการณ์พร้อมกันจาก README
4. เติม TODO ใน student_policy.py แล้วรัน checker จนผ่าน บันทึกหนึ่ง failed case ที่ช่วยแก้ logic

   เลือก `python3 check_submission.py` สำหรับ baseline หรือ `python3 check_submission.py --contract group` สำหรับ mapping ของกลุ่ม: positive button/touch/approach เลือก interested/happy ได้ แต่คง safety/recovery และทุกstateต้องreachable ตรวจ README ก่อนเลือก contract
5. รัน C0/C1 ด้วย3 paired seeds เก็บ all source inputs, both onset count, no-onset count และเหตุผล ไม่คัดเฉพาะ successes
6. ตรวจหนึ่ง event ตั้งแต่ source → debounce/filter → decision → queue → actual apply → motion/RGB onset เทียบ latency จาก CSV กับค่าที่คำนวณเอง
7. ตรวจ near+touch conflict, stale/invalid fallback, quiet-to-sleepy และ recovery button อธิบาย discarded/held/no state change/censored ต่างกันอย่างไร
8. เทียบ raw/event CSV ของ replay และต้นฉบับ หากต่าง ให้หา policy/config/source version ที่เปลี่ยน
9. รายงาน1–2หน้า: prediction, protocol, FSM/table,กราฟ,latency table,ผล C0/C1, negative result และ hardware limitation ห้ามเรียก simulated command onset ว่า physical latency

## ตารางบันทึกของนักศึกษา

| Condition/seed | All external inputs | Both onset | ≤1s both observed | No both onset/status | Max observed latency [s] | State transitions |
|---|---:|---:|---:|---|---:|---:|
| C0/41 | 10 | 7 | 7 | 3: no_state_change 2, discarded_priority 1 | 0.24 | 67 |
| C1/41 | 10 | 7 | 7 | 3: no_state_change 2, policy_held 1 | 0.14 | 9 |
| C0/42 | 10 | 6 | 6 | 4: no_state_change 2, filtered_not_recognized 1, preempted_before_apply 1 | 0.18 | 72 |
| C1/42 | 10 | 7 | 7 | 3: no_state_change 2, policy_held 1 | 0.14 | 10 |
| C0/43 | 10 | 6 | 6 | 4: no_state_change 3, discarded_priority 1 | 0.04 | 63 |
| C1/43 | 10 | 7 | 7 | 3: no_state_change 2, policy_held 1 | 0.14 | 9 |

| Input ID | Source s | Recognized s | Decision s | Actual apply s | Motion onset s | RGB onset s | Both latency s | Status/reason |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| button_02 | 18.00 | 18.06 | 18.06 | 18.10 | 18.10 | 18.10 | 0.10 | responded |
| touch_conflict | 7.00 | 7.06 | 7.06 | N/A | N/A | N/A | N/A | policy_held เพราะ afraid guard |

## บันทึกเพิ่มเติม
### ตรวจเวลาหนึ่ง event
button_02 ของ C1 รอบ 1 มี source 18.00 s ผ่าน filter ที่ 18.06 s
ตัดสินใจและ queued ที่ 18.06 s จากนั้น actual apply และ motion/RGB onset ที่ 18.10 s

Source latency = 18.10 - 18.00 = 0.10 s
Command latency = 18.10 - 18.06 = 0.04 s

### เหตุผลของ N/A
touch_conflict มี source ที่ 7.00 s และรับรู้ที่ 7.06 s ขณะอยู่ใน afraid
จึงถูก afraid guard ให้คงสถานะ มี status เป็น policy_held และไม่มีคำสั่งใหม่เข้า queue
ดังนั้น Actual apply, Motion onset, RGB onset และ Both latency จึงเป็น N/A
ไม่ใส่ 0 s เพราะไม่ได้เกิดการตอบสนองใหม่ทันที

### ความหมายของสถานะ
- discarded_priority: event ถูกตัดออกเพราะมี event ที่ priority สูงกว่าใน tick เดียวกัน
- policy_held: policy ให้คงสถานะ ไม่สร้าง expression ใหม่
- no_state_change: event เลือกสถานะเดิม จึงไม่มี expression ใหม่
- censored_end: จบ trial ก่อนวัด onset ได้ครบ จึงบันทึกค่าที่ยังวัดไม่ได้เป็น N/A

### ผล replay
Replay C1 รอบ 1 จาก inputs_r01.csv เดิม แล้วเทียบ raw_C1_r01.csv
และ events_C1_r01.csv ด้วย fc.exe /b พบว่าตรงกันแบบ byte-for-byte ทั้งสองไฟล์

### เอกสารประกอบ
Prediction, FSM diagram, ตาราง transition 5×8, expression mapping,
failed case และวิธีแก้ อยู่ในใบงาน Word และรายงานสรุปที่ส่งร่วมกัน

ก่อนส่งตรวจ: ทุก state/movement/input ครบ; bounds/slewไม่ถูกปิด; latencyใช้ออนเซ็ตจริงของmodel; missingไม่แทน0; ระบุ3seedsเป็นsynthetic replications; ส่งpolicy/config/raw/events/metrics; student filesไม่มีเฉลยหรือข้อมูลผู้สอน

Expected set ของ group: ประกาศ input IDs ก่อนรัน ใช้ชุดเดียวกัน C0/C1 แล้วนับ pass/misses จาก source_outcomes ใน metrics.json ตามชุดนั้น ค่า primary_* ที่ runner สร้างใช้ baseline 7 IDs เสมอ; รายงาน all 10 sources พร้อมเหตุผลไว้ครบ ห้ามปรับ subset หลังเห็นผล
