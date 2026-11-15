# ใบงาน Lab 05 — Prediction, timing, evidence

ฉบับพิมพ์: [Word](Lab05_Student_Worksheet_TH.docx) / [PDF](Lab05_Student_Worksheet_TH.pdf)

ชื่อ/รหัส________________ กลุ่ม________ วันที่ 15/11/2026

**ขอบเขต:** main runner เป็น proposed course model ใช้ scheduled stimulus และ kinematic body; contact demo ใช้ synthetic signals ไม่ใช่ ALCS terrain experiment ของ paper

## 1. ก่อนรัน: hypothesis และ architecture (10 นาที)

1. Architecture: `S → controller (B0 fixed / B1 direct / B2-B3 hormone) → R_used → bounded phi/stride → SO(2) CPG → tripod decoder → kinematic body`. ยังไม่มี independent sensory feedback จาก body/terrain กลับเข้า controller; stimulus เป็น scheduled input.
2. Prediction (บันทึกก่อนรัน): เทียบ B1 กับ B2 คาดว่า B2 จะมี command latency/recovery ที่ไม่เป็นศูนย์เพราะ H มี state memory; B1 จะตอบที่ command_time=10.00 ทันที. Peak R ของ B2 อาจใกล้ B1 แต่ไม่เท่ากันทุกเวลา. คาด command max-step B2 ต่ำกว่า B1 แต่ total variation ตลอด step-up/down อาจใกล้กัน. ตรวจด้วย command latency, recovery, max Δphi/step และ phi time trace.
3. B3 ตัด binding term `B=k_bind R_old` ออกจาก B2; production, clearance และ H state memory ยังคงอยู่.
4. Provenance: source equation: SO(2) simultaneous rotation/tanh recurrence (Lab 03); proposed course equation: H Euler P−C−B + bounded R-to-phi/stride map; measured metric: command latency / segment speed จาก simulation; unmeasured: paper Stability/Harmony หรือ physical energy/robot stability.

## 2. รัน comparison และตรวจเวลา (15 นาที)

รัน comparison ตาม README เปิด report เลือก B2 เลื่อน timeline ไป 10.00/10.05s แล้วเปิด B2_states.csv/B2_intervals.csv เพื่อยืนยัน

| command/input time | state end time | H_start | H_end | R_used | φที่ใช้ | stride_half ที่ใช้ |
|---|---|---|---|---|---|---|
| 10.00 | 10.05 | 0.0000 | 0.0400 | 0.0000 | 0.2000 | 0.0550 |
| 10.05 | 10.10 | 0.0400 | 0.0784 | 0.0400 | 0.2080 | 0.0554 |
| 20.00 | 20.05 | 0.9997 | 0.9597 | 0.9997 | 0.3999 | 0.0650 |

อธิบายจาก CSV ว่าเหตุใด B1 command latency กับ state latency จึงต่างกัน: B1 ใช้ S_k แบบ direct ใน command ณ 10.00 จึง command latency 0; state CSV เป็น post-update จึง first R≥0.1 ปรากฏที่ state_time 10.05 มี sampling offset 0.05 s.

ตรวจ warmup/initialstates ใน config: ทุก condition เริ่ม CPG เหมือนกันหรือไม่? หลักฐาน: ใช้ warmup CPG 10 s ด้วย alpha=1.10, phi=.20 เหมือนกัน แล้ว reset H/R, body origin, foot anchors และ log; config.initial_states แสดง o1/o2 ตรงกันทุก condition.

## 3. เปรียบเทียบผลและข้อจำกัด (15 นาที)

เติมจาก metrics และ segment_metrics พร้อมหน่วย ห้ามคัดลอกผล source paper มาใส่เป็นผล run นี้

| condition | TV φ(rad) | maxΔφ/step(rad) | TV stride(m) | cmd latency(s) | cmd recovery(s) | on frequency(Hz) | on distance(m) |
|---|---|---|---|---|---|---|---|
| B0 | 0.000000 | 0.000000 | 0.000000 | N/A | N/A | 0.624877 | 0.778743 |
| B1 | 0.400000 | 0.200000 | 0.020000 | 0.000 | 0.000 | 1.268366 | 1.825152 |
| B2 | 0.399827 | 0.008000 | 0.019991 | 0.150 | 2.850 | 1.202760 | 1.706250 |
| B3 | 0.399534 | 0.008000 | 0.019977 | 0.150 | 3.800 | 1.225791 | 1.727498 |

1. ผลข้อใดสนับสนุน hypothesis และผลข้อใดไม่สนับสนุน? B2 command latency 0.15 s และ recovery 2.85 s สนับสนุน memory/lag เทียบ B1 ที่ 0.00/0.00; phi max-step B2=.008 rad เทียบ B1=.20 rad. แต่ phi total variation ใกล้กัน (.399827 เทียบ .400000) จึงไม่สนับสนุนการคาดว่า TV ลดลงมาก.
2. การลด TV ยืนยันว่าหุ่นยนต์ไม่ล้มหรือใช้พลังงานน้อยลงหรือไม่? ไม่ได้; ต้องมี dynamic body/CoM, contact force/friction, motor/torque/current/energy และการทดลอง hardware ที่ทำซ้ำได้.
3. Bounds เหมือนกันทำให้ command amplitude เท่ากันหรือไม่? ไม่; B1 peak R_used=1 ให้ phi=.40 rad, B2 peak≈.9997 แต่ ramp/decay ใช้ค่าเฉลี่ย phi_on=.3750 และ phi_off=.2250 rad; same bounds constrain range, not trajectory/amplitude at every time.
4. ทำไมไม่ใช้ frequency เฉลี่ย 30s แทน pre/on/off? เพราะรวม transient ขาขึ้นและลงเข้าด้วยกันจนซ่อนผลตามช่วง stimulus และ command lag; ให้รายงาน segment frequency พร้อมจำนวน complete periods.

## 4. เปลี่ยนหนึ่งปัจจัยและตรวจ fault (20 นาที)

เลือก phi-only หรือ stride-only ตั้ง prediction ก่อนรัน ตรวจ parameter ที่คงที่จาก intervalCSV แล้วเปรียบเทียบ B1/B2 กับ bothmapping

Prediction ก่อนรัน (phi-only): สิ่งที่เปลี่ยน = active phi gain; สิ่งที่คงที่ = stride_half=.055 m, alpha, dt, H rates, stimulus, initial states และ bounds; metric หลัก = B1/B2 on-segment frequency กับ on-distance. คาดว่าการปรับ phi จะเปลี่ยน cadence/frequency แต่ stride mapping ไม่เปลี่ยน; B2 จะมี lag เมื่อเทียบ direct B1.

ผลและข้อจำกัด causal claim: ใน phi-only, stride_half คงที่ .055 m; B1 on frequency/distance = 1.268366 Hz / 1.549111 m, B2 = 1.202760 Hz / 1.467193 m. ผลสอดคล้องกับ cadence ลดเล็กน้อยจาก hormone trajectory เมื่อเทียบ direct path แต่เป็น deterministic kinematic model; ไม่พิสูจน์ผลต่อ robot จริง.

รัน faultprofile เปิด input15.00 แล้วบันทึก:

| field | B2 value |
|---|---|
| fault at command15.00 | fault=1 (input_time=15.00, state end=15.05) |
| H_used / R_used | 0.0000 / 0.0000 |
| φ / stride ที่ใช้ | 0.200 rad / 0.055 m |
| H state15.05 | 0.0000 |
| H state15.10 | 0.0400 |

อธิบายว่า fallback ทำก่อนหรือหลัง command และเหตุใด policy นี้ยังไม่รับรอง hardware safety: fallback ทำก่อน command ของ interval [15.00,15.05); invalid S สร้าง R_used=0 และ H/R reset. เป็นเพียง software rule ใน simulation ไม่มี actuator watchdog, emergency stop, sensor diagnostics หรือ hardware validation.

## 5. Contact mini-lab (20 นาที)

เปิด contactreport เลือก cases ด้านล่าง เปรียบเทียบ SI, SIF, absoluteerror และ validity

| case | SI ของแต่ละขาโดยทั่วไป | SIF | absoluteerror | สิ่งที่อนุมานไม่ได้ |
|---|---|---|---|---|
| matched | 1.000 ทุกขา | 0.0000 | 0.0000 | ไม่พิสูจน์ physical contact correctness |
| gain-offset | 1.000 ทุกขา | 0.0000 | 0.1628 | correlation ไม่วัด gain/offset agreement |
| mixed-delay | LF/RM/LH=1; อีก 3≈0.00001 | 0.5000 | 0.2260 | ไม่ยืนยัน terrain adaptation |
| all-inverted | -1.000 ทุกขา | 0.0000 | 0.6314 | SIF=0 ไม่แปลว่าขาถูกต้อง |
| constant | N/A เพราะ zero variance | N/A | 0.0000 | ไม่สรุป SI=0 |
| fault | mean SI valid=1; 99 SIF rows N/A | 0.0000 ใน valid rows | 0.0000 | ไม่ตรวจ physical sensor fault recovery |

1. ทำไม gain-offset ให้ correlation สูงแม้ error ไม่เป็น 0? Pearson ไม่เปลี่ยนภายใต้ affine gain/offset บวก แต่ absolute error ยังแสดงความต่างของ amplitude/offset.
2. เมื่อทุกขา inverted ทำไม SIF จึงยังเป็น 0? SI ทุกขาเท่ากับ -1 จึงไม่มีความกระจาย; release ที่ SIF=0 คือ 1/(1+exp(0))=.5.
3. constant ควรเป็น SI0 หรือ N/A? N/A เพราะ variance เป็นศูนย์ ทำให้ correlation นิยามไม่ได้.
4. fault หนึ่ง sample มีผลต่อ rolling windows กี่ rows ไม่นับ startup 49 rows? ตรวจ CSV พบ 50 rows เพิ่มเติม (sample_time 15.00–17.45); รวม unavailable SIF 99 rows = startup 49 + fault windows 50.
5. paired Pearson ของ demo มีสถานะ source/proposed ใด? เป็น proposed course definition ไม่ใช่การ reproduce Eq.(3) ตามพิมพ์; ยังไม่ต่อ Cg/HR/MI_H recurrence.

## 6. ส่งงานและ exit ticket (10 นาที)

ส่ง prediction ก่อนรัน, config/manifest/raw CSV ของ comparison+one-factor run+fault, contact metrics และ CSV หนึ่ง case ที่อภิปราย, ตารางพร้อมหน่วยและกราฟ 2 รูป พร้อมรายงาน 2–3 หน้า บอกคำสั่งและ Python version เพื่อรันซ้ำ

Exit: Claim ที่ข้อมูลรองรับ: ใน proposed course model B2 มี command latency=.15 s, phi max-step=.008 rad และ recovery=2.85 s; วัดด้วย command metrics จาก step profile. Claim ที่ยังรองรับไม่ได้: B2 ปลอดภัย/ประหยัดพลังงานกว่า B1; ต้องเพิ่ม rigid-body/CoM/contact-force/torque/current measurement และ trials บน robot.

**Rubric 20 คะแนน:** architecture/provenance 4; timing/fault 4; reproducibility/data 3; quantitative comparison/one-factor 5; interpretation/contact/N/A 4 คะแนนมาจากเหตุผลกับหลักฐาน ไม่ได้ให้เต็มเพราะ runner รันผ่านหรือเพราะผล “ดีขึ้น” ตามคาด

**Workshop 25 นาทีในคาบ Week05:** ทำข้อ 1 แบบย่อ 5 นาที, ข้อ 2 10 นาที, ข้อ 3 10 นาที ส่วน one-factor/fault/contact เป็น extended lab หรือการบ้าน ใช้เวลารวม 90 นาทีตามใบงาน ไม่รวมเวลาติดตั้ง Python

## ผลการรันและการทำซ้ำ

ทดสอบด้วย Python 3.13.7; ทุก run มี 600 updates / 601 states. ไฟล์ผล raw, config, metrics, report HTML, source snapshot และ SHA-256 manifest อยู่ใน subfolders ของ `results`.

```powershell
python lab05.py --condition all --profile step --mapping both --output-dir results\comparison
python lab05.py --mapping phi-only --output-dir results\phi_only
python lab05.py --mapping stride-only --output-dir results\stride_only
python lab05.py --condition B2 --profile zero --output-dir results\zero
python lab05.py --condition B2 --profile one --output-dir results\one
python lab05.py --condition B2 --profile spike --output-dir results\spike
python lab05.py --condition all --profile fault --output-dir results\fault
python contact_demo.py --output-dir results\contact
```

รายงาน Word: `Lab05_Report_TH.docx`. ภาพหลัก: `results\comparison\lab05_comparison.png`, `results\contact\contact_metrics.png`.
