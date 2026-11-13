# ใบงาน Lab 05 — Prediction, timing, evidence

ฉบับพิมพ์: [Word](Lab05_Student_Worksheet_TH.docx) / [PDF](Lab05_Student_Worksheet_TH.pdf) · รายงาน: [Lab05_Report_TH.docx](Lab05_Report_TH.docx)

ชื่อ นายกฤตัชญ์ติณห์ เครือทอง รหัสนักศึกษา 6752500223

**ขอบเขต:** main runner เป็น proposed course model ใช้ scheduled stimulus และ kinematic body; contact demo ใช้ synthetic signals ไม่ใช่ ALCS terrain experiment ของ paper

## 1. ก่อนรัน: hypothesis และ architecture (10 นาที)

1. S → controller (B0 ค่าคงที่, B1 ใช้ S ตรงๆ, B2/B3 ผ่าน H) → R_used → bounded mapping → φ/stride → SO(2) CPG → tripod decoder → body จุดที่ยังไม่มี independent sensory feedback คือ contact ซึ่งมาจาก sign ของ o₂ ใน decoder เอง และไม่มีสัญญาณจาก body หรือพื้นย้อนกลับมาที่ controller หรือ CPG
2. Hypothesis: B2 จะมี max Δφ ต่อ step (rad) เล็กกว่า B1 มาก แต่ TV ของ φ (rad) ใกล้กัน และ B2 จะมี command recovery (s) นานกว่า B1 (hypothesis นี้เขียนหลังรันโปรแกรมแล้ว)
3. B3 ตัด binding term (k_bind = 0) ออก แต่ state H ยังมี memory จึงยังค่อยๆ ขึ้นและลด
4. Provenance: source equation `Hc(t) = β·Hc(t−1) + Hg(t) − Hr(t)` (Homchanthanakul 2019); proposed course equation `H = clamp(H + dt(k_prod·S − k_clear·H − k_bind·R), 0, 1)`; expected measurement คือ max Δφ/step และ command recovery; metric ที่วัดไม่ได้คือ Stability ของ paper (ไม่มีแรงสัมผัสและ center of mass)

## 2. รัน comparison และตรวจเวลา (15 นาที)

| command/input time | state end time | H_start | H_end | R_used | φที่ใช้ | stride_half ที่ใช้ |
|---|---|---|---|---|---|---|
| 10.00 | 10.05 | 0.0000 | 0.0400 | 0.0000 | 0.2000 | 0.0550 |
| 10.05 | 10.10 | 0.0400 | 0.0784 | 0.0400 | 0.2080 | 0.0554 |
| 20.00 | 20.05 | 0.9997 | 0.9597 | 0.9997 | 0.3999 | 0.0650 |

B1 command latency กับ state latency ต่างกันเพราะ: B1 ใช้ S_k ของ interval นั้นทันที ที่ command_time 10.00 จึงได้ r_used = 1 และ φ = 0.40 (command latency 0.000 s) แต่ state ถูกบันทึกหลัง update ที่ 10.05 (state latency 0.050 s) ส่วนต่างหนึ่ง dt เป็นการจัดเวลาการคำนวณใน model ไม่ใช่ hardware latency

warmup/initial states: ทุก condition ใช้ CPG warmup 10 s ด้วย baseline เดียวกัน แล้ว reset H/R, body origin, foot anchors และ logs โดยคง CPG outputs หลัง warmup ตรวจจาก config.json ของ run

## 3. เปรียบเทียบผลและข้อจำกัด (15 นาที)

| condition | TV φ(rad) | maxΔφ/step(rad) | TV stride(m) | cmd latency(s) | cmd recovery(s) | on frequency(Hz) | on distance(m) |
|---|---|---|---|---|---|---|---|
| B0 | 0.000 | 0.000 | 0.000 | N/A | N/A | 0.625 | 0.779 |
| B1 | 0.400 | 0.200 | 0.020 | 0.000 | 0.000 | 1.268 | 1.825 |
| B2 | 0.400 | 0.008 | 0.020 | 0.150 | 2.850 | 1.203 | 1.706 |
| B3 | 0.400 | 0.008 | 0.020 | 0.150 | 3.800 | 1.226 | 1.727 |

1. สนับสนุน: max Δφ/step ของ B2 0.008 rad เทียบ 0.200 rad ของ B1 และ recovery 2.850 s เทียบ 0.000 s TV ของ φ เท่ากันที่ 0.400 rad ตามที่คาด ผลที่ไม่ได้คาด: ระยะรวม 30 s ของ B2 (3.383 m) ใกล้ B1 (3.378 m) เพราะ B2 ช้ากว่าในช่วง on (1.706 เทียบ 1.825 m) แต่เร็วกว่าในช่วง off (0.900 เทียบ 0.776 m)
2. ไม่ยืนยัน เพราะยังไม่มีข้อมูลแรงสัมผัสพื้น ตำแหน่ง center of mass หรือกระแสมอเตอร์ การนับ min_support = 3 ไม่ได้แปลว่าเสถียร
3. ไม่เท่ากันเสมอ peak ของ R_used เป็น 1.000 ทุกตัวยกเว้น B0 จึงได้ φ สูงสุดประมาณ 0.40 rad แต่ค่าเฉลี่ยช่วง on ต่างกัน: B1 0.400, B2 0.375, B3 0.382 rad
4. ค่าเฉลี่ย 30 s รวมช่วง baseline กับช่วงกระตุ้นจนผลไม่ชัด เช่น B1 ช่วง on 1.268 Hz แต่ pre/off 0.625 Hz และช่วง off ของ B2 ยังมี 0.698 Hz (φ เฉลี่ย 0.225 rad) จึงยังไม่ใช่ steady state

## 4. เปลี่ยนหนึ่งปัจจัยและตรวจ fault (20 นาที)

สิ่งที่เปลี่ยน: รันทั้ง phi-only และ stride-only เทียบกับ both · สิ่งที่คงที่: phi-only คง stride_half 0.055 m, stride-only คง φ 0.20 rad · metric หลัก: on distance (m) และ on frequency (Hz) · prediction: phi-only เปลี่ยนทั้ง frequency และระยะ ส่วน stride-only เปลี่ยนแค่ระยะ

ผลและข้อจำกัด causal claim: B2 phi-only 1.203 Hz, 1.467 m; stride-only 0.625 Hz, 0.902 m; both 1.203 Hz, 1.706 m (B0 0.779 m) φ มีผลต่อระยะมากกว่า stride และผลสองตัวไม่บวกกันตรงๆ เป็นผลใน kinematic model เท่านั้น

| field | B2 value |
|---|---|
| fault at command15.00 | fault = 1 |
| H_used / R_used | 0.0000 / 0.0000 (H ก่อนหน้า 0.9831) |
| φ / stride ที่ใช้ | 0.2000 rad / 0.0550 m |
| H state15.05 | 0.0000 |
| H state15.10 | 0.0400 |

fallback ทำก่อน command ในแถว input 15.00 จึงได้ φ = 0.20 rad ใน interval เดียวกันทันที policy นี้ยังไม่รับรอง hardware safety เพราะแค่กลับไปเดินที่ baseline ไม่ได้หยุดหุ่น ไม่ตรวจ actuator, torque หรือ emergency stop และทำให้ φ กระโดด 0.196 rad ในหนึ่ง step

## 5. Contact mini-lab (20 นาที)

| case | SI ของแต่ละขาโดยทั่วไป | SIF | absoluteerror | สิ่งที่อนุมานไม่ได้ |
|---|---|---|---|---|
| matched | 1.000 | 0.000 | 0.000 | ไม่ได้บอกว่ามี terrain feedback จริง |
| gain-offset | 1.000 | 0.000 | 0.163 | SI สูงไม่ได้แปลว่าค่าตรงกัน |
| mixed-delay | 1.000 | 0.500 | 0.226 | ไม่บอกว่าขาใดช้าเพราะอะไร |
| all-inverted | −1.000 | 0.000 | 0.631 | SIF = 0 ไม่ได้แปลว่าทุกขาถูก |
| constant | N/A | N/A | 0.000 | correlation ไม่นิยามเมื่อ variance เป็น 0 |

1. Pearson วัดแค่การขึ้นลงพร้อมกัน actual = 0.2 + 0.5·expected จึงได้ SI 1.000 แต่ MAE 0.163
2. SIF คือ SD ของ SI ทั้ง 6 ขา ทุกขาเป็น −1.000 เท่ากันจึงได้ 0 release ที่ SIF 0 คือ 1/(1 + e⁰) = 0.5
3. ควรเป็น N/A เพราะต้องหารด้วย SD ที่เป็น 0 ผลรันจริงเป็น N/A ทั้ง 600 rows
4. fault ที่ sample 300 (15.00 s) ทำให้ window ใช้ไม่ได้ถึง sample 349 (17.45 s) รวม 50 rows (unavailable 99 ลบ startup 49)
5. เป็น proposed course definition ไม่ใช่ verified reproduction ของ Eq.(3) และยังไม่ได้ต่อ C_g/MI

## 6. ส่งงานและ exit ticket (10 นาที)

ไฟล์ส่ง: prediction ในข้อ 1, config/manifest/raw CSV ใน `results/comparison`, `results/phi_only`, `results/stride_only`, `results/fault`, contact metrics ใน `results/contact`, ตารางและกราฟใน [Lab05_Report_TH.docx](Lab05_Report_TH.docx) ใช้ Python 3.10

```sh
python3 lab05.py --output-dir results/comparison
python3 lab05.py --mapping phi-only --output-dir results/phi_only
python3 lab05.py --mapping stride-only --output-dir results/stride_only
python3 lab05.py --profile fault --output-dir results/fault
python3 contact_demo.py --output-dir results/contact
```

Exit: claim ที่ข้อมูลรองรับคือใน model นี้ hormone path (B2) ลด max Δφ/step จาก 0.200 rad (B1) เหลือ 0.008 rad โดย φ TV เท่ากันที่ 0.400 rad · claim ที่ยังรองรับไม่ได้คือการเปลี่ยนคำสั่งแบบนุ่มนวลทำให้หุ่นเดินเสถียรขึ้นหรือใช้พลังงานน้อยลง ต้องเพิ่มแรงสัมผัส ตำแหน่ง center of mass และกระแสมอเตอร์
