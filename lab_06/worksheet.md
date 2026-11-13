# ใบงาน Lab06 — Student

ชื่อ นายจิรายุส พลอยพริ้ง   รหัสนักศึกษา 6752500401

> ทดลองใน simulator เท่านั้น ยังไม่ได้ต่อหรือสอบเทียบกับหุ่นจริง prediction เขียนหลังจากรันโปรแกรมแล้ว คำตอบเต็มอยู่ใน Week06_Student_Worksheet_TH.docx

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
| C0/41 | 10 | 7 | 7 | 3: discarded_priority 1, no_state_change 2 | 0.24 | 67 |
| C1/41 | 10 | 7 | 7 | 3: policy_held 1, no_state_change 2 | 0.14 | 9 |
| C0/42 | 10 | 6 | 6 | 4: filtered_not_recognized 1, preempted_before_apply 1, no_state_change 2 | 0.18 | 72 |
| C1/42 | 10 | 7 | 7 | 3: policy_held 1, no_state_change 2 | 0.14 | 10 |
| C0/43 | 10 | 6 | 6 | 4: discarded_priority 1, no_state_change 3 | 0.04 | 63 |
| C1/43 | 10 | 7 | 7 | 3: policy_held 1, no_state_change 2 | 0.14 | 9 |

| Input ID | Source s | Recognized s | Decision s | Actual apply s | Motion onset s | RGB onset s | Both latency s | Status/reason |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| button_01 (C1/41) | 1.00 | 1.10 | 1.10 | 1.14 | 1.14 | 1.14 | 0.14 | responded (bounce + debounce 0.06 s + scheduler 0.04 s) |
| touch_conflict (C1/41) | 7.00 | 7.06 | 7.06 | - | - | - | N/A | policy_held (afraid hold ทุก event อื่น) |

ก่อนส่งตรวจ: ทุก state/movement/input ครบ; bounds/slewไม่ถูกปิด; latencyใช้ออนเซ็ตจริงของmodel; missingไม่แทน0; ระบุ3seedsเป็นsynthetic replications; ส่งpolicy/config/raw/events/metrics; student filesไม่มีเฉลยหรือข้อมูลผู้สอน

Expected set ของ group: ประกาศ input IDs ก่อนรัน ใช้ชุดเดียวกัน C0/C1 แล้วนับ pass/misses จาก source_outcomes ใน metrics.json ตามชุดนั้น ค่า primary_* ที่ runner สร้างใช้ baseline 7 IDs เสมอ; รายงาน all 10 sources พร้อมเหตุผลไว้ครบ ห้ามปรับ subset หลังเห็นผล

## บันทึกผลของนักศึกษา

- prediction (เขียนหลังรัน, เชิงคุณภาพ): C0 ไม่มี debounce/hysteresis จึงจะสลับ state บ่อยเมื่อ distance มี noise ใกล้เกณฑ์ และปุ่มที่เด้งอาจถูกนับหลายครั้ง C1 จะนิ่งกว่าแต่ช้ากว่าเล็กน้อย input ที่ไม่ควรมี onset ใหม่คือ touch ขณะ afraid และ fault ตอน output neutral อยู่แล้ว
- FSM: `figures/state_diagram.png` ตาราง 5×8 พิมพ์จาก policy จริงใน `figures/replay_table.png`
- checker: starter เดิม FAIL 7 คู่ (เช่น `normal + touch: returned None`) หลังแก้ PASS 40 คู่ทั้ง baseline และ group (`figures/check_starter_fail.png`, `figures/check_pass.png`) ใช้ baseline mapping
- replay C1 r01: `raw_C1_r01.csv` และ `events_C1_r01.csv` ตรงกับต้นฉบับทุก byte
- ข้อสังเกต: ช่วง approach 4.80–6.60 s seed 41 C0 สลับ interested/normal 32 ครั้ง C1 เปลี่ยน 2 ครั้ง แลกกับ latency ปุ่ม 0.04 → 0.14 s
- negative result: C0 r02 พลาด clear_01 (filtered_not_recognized) และ r03 พลาด clear_02 (no_state_change) ใน primary set
- ข้อจำกัด: latency เป็น simulated command onset ไม่ใช่ physical latency ยังไม่ได้วัดกับหุ่นจริง รายงาน 1–2 หน้าอยู่ใน Week06_Report_TH.docx
