# ใบงาน Lab06 — Student

**แบบจำลองทั้งหมดใน runner เป็น proposed course model** โปรแกรมเป็น simulation ไม่ใช่ข้อมูลจาก robot และไม่มี learning

1. Prediction ก่อนรัน: คาดว่า C1 debounce/hysteresis จะลดการรับรู้ bounce/noise ซ้ำเมื่อเทียบ C0 แต่ debounce อาจเพิ่มเวลา recognized บาง event; expected both count อาจไม่เพิ่มเพราะการกรองไม่ได้สร้าง onset ให้ event ที่ไม่มี state/output change. touch ขณะ afraid และ fault ขณะ output เป็น neutral คาดว่าไม่มี onset ใหม่.
2. FSM: normal --button/approach--> interested; normal/other non-afraid --touch--> happy; near จากทุก state --> afraid; clear/fault จากทุก state --> normal; interested/happy --timeout--> normal; normal --idle--> sleepy; afraid hold event ที่ไม่ใช่ near/clear/fault.
3. Transition table baseline (fault/near/clear มี priority ก่อน; `hold` หมายถึง `None`):

| State \ Event | fault | near | clear | touch | button | approach | timeout | idle |
|---|---|---|---|---|---|---|---|---|
| normal | normal | afraid | normal | happy | interested | interested | hold | sleepy |
| interested | normal | afraid | normal | happy | interested | interested | normal | hold |
| happy | normal | afraid | normal | happy | interested | interested | normal | hold |
| afraid | normal | afraid | normal | hold | hold | hold | hold | hold |
| sleepy | normal | afraid | normal | happy | interested | interested | hold | hold |
4. เติม TODO ใน student_policy.py แล้วรัน checker จนผ่าน บันทึกหนึ่ง failed case ที่ช่วยแก้ logic: starter ไม่ได้จัดการ `(normal, touch)` จึงคืน None แทน happy; เพิ่ม touch transition หลัง guard afraid แล้ว checker ผ่าน baseline ครบ 40 คู่

   เลือก `python3 check_submission.py` สำหรับ baseline หรือ `python3 check_submission.py --contract group` สำหรับ mapping ของกลุ่ม: positive button/touch/approach เลือก interested/happy ได้ แต่คง safety/recovery และทุกstateต้องreachable ตรวจ README ก่อนเลือก contract
5. รัน C0/C1 ด้วย3 paired seeds เก็บ all source inputs, both onset count, no-onset count และเหตุผล ไม่คัดเฉพาะ successes
6. ตรวจหนึ่ง event ตั้งแต่ source → debounce/filter → decision → queue → actual apply → motion/RGB onset เทียบ latency จาก CSV กับค่าที่คำนวณเอง
7. ตรวจ near+touch conflict, stale/invalid fallback, quiet-to-sleepy และ recovery button อธิบาย discarded/held/no state change/censored ต่างกันอย่างไร
8. เทียบ raw/event CSV ของ replay และต้นฉบับ หากต่าง ให้หา policy/config/source version ที่เปลี่ยน
9. รายงาน1–2หน้า: prediction, protocol, FSM/table,กราฟ,latency table,ผล C0/C1, negative result และ hardware limitation ห้ามเรียก simulated command onset ว่า physical latency

## ตารางบันทึกของนักศึกษา

| Condition/seed | All external inputs | Both onset | ≤1s both observed | No both onset/status | Max observed latency [s] | State transitions |
|---|---:|---:|---:|---|---:|---:|
| C0/41 | 10 | 7 | 7 | 3 (2 neutral no_state_change, 1 conflict) | 0.240 | 67 |
| C1/41 | 10 | 7 | 7 | 3 (2 neutral no_state_change, 1 afraid policy_held) | 0.140 | 9 |
| C0/42 | 10 | 6 | 6 | 4 (faults, filtered clear, conflict) | 0.180 | 72 |
| C1/42 | 10 | 7 | 7 | 3 (2 neutral no_state_change, 1 afraid policy_held) | 0.140 | 10 |
| C0/43 | 10 | 6 | 6 | 4 (fault/filtered/conflict; see source_outcomes) | 0.040 | 63 |
| C1/43 | 10 | 7 | 7 | 3 (2 neutral no_state_change, 1 afraid policy_held) | 0.140 | 9 |

| Input ID | Source s | Recognized s | Decision s | Actual apply s | Motion onset s | RGB onset s | Both latency s | Status/reason |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| button_01 (C1/41) | 1.00 | 1.10 | 1.10 | 1.14 | 1.14 | 1.14 | 0.14 | responded |
| touch_conflict (C1/41) | 7.00 | 7.06 | 7.06 | N/A | N/A | N/A | N/A | policy_held: afraid guard |

ก่อนส่งตรวจ: ทุก state/movement/input ครบ; bounds/slewไม่ถูกปิด; latencyใช้ออนเซ็ตจริงของmodel; missingไม่แทน0; ระบุ3seedsเป็นsynthetic replications; ส่งpolicy/config/raw/events/metrics; student filesไม่มีเฉลยหรือข้อมูลผู้สอน

Expected set ของ group: ประกาศ input IDs ก่อนรัน ใช้ชุดเดียวกัน C0/C1 แล้วนับ pass/misses จาก source_outcomes ใน metrics.json ตามชุดนั้น ค่า primary_* ที่ runner สร้างใช้ baseline 7 IDs เสมอ; รายงาน all 10 sources พร้อมเหตุผลไว้ครบ ห้ามปรับ subset หลังเห็นผล

## ผลการรันและการทำซ้ำ

ตรวจด้วย Python 3.13.7; `check_submission.py --contract baseline` ผ่าน 40 transition pairs. C1 มี primary pass 7/7 ทั้งสาม seeds (21/21); C0 ได้ 7/7, 6/7, 6/7 (19/21). จำนวน state transitions ลดลงจาก C0 67/72/63 เป็น C1 9/10/9 ภายใต้ paired synthetic inputs เดียวกัน; ไม่ใช่หลักฐาน physical performance.

ตัวอย่าง event trace (C1, seed 41): button source 1.00 s → recognized/decision 1.10 → actual apply และ motion/RGB onset 1.14 s; both latency=.14 s. touch_conflict ที่ 7.00 ถูก near priority ชนะและ afraid guard ทำให้ touch เป็น `policy_held`, จึงไม่มี onset ของ touch. invalid/stale faults ที่ state neutral ให้ `no_state_change` และ latency N/A ไม่ใช่ศูนย์.

Replay จาก `inputs_r01.csv` ให้ `raw_C1_r01.csv` และ `events_C1_r01.csv` มี SHA-256 ตรงกับ run ต้นฉบับทุก byte.

คำสั่งรันหลัก:

```powershell
python check_submission.py --contract baseline
python lab06.py --policy student --condition all --repeats 3 --output-dir results\completed
python lab06.py --policy student --condition C1 --repeats 1 --replay results\completed\inputs_r01.csv --output-dir results\replay
```

รายงาน Word: `Lab06_Report_TH.docx`; กราฟ: `results\completed\lab06_seed_comparison.png` และ `results\completed\lab06_latency_seed41.png`.
