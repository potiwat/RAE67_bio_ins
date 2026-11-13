# ใบงาน Lab 05 — Prediction, timing, evidence

ฉบับพิมพ์: [Word](Lab05_Student_Worksheet_TH.docx) / [PDF](Lab05_Student_Worksheet_TH.pdf)

ชื่อ/รหัส วทัญญู ชำนาญ (6752500096), ณัฐพงศ์ เวชยานนท์ (6752500177), นิธิวัฒน์ สุทธิ (6752500037), ปุญญพัฒน์ ปราณีชาติ (6752500355) กลุ่ม ภาคีนกอีก๋อย วันที่ 11/7/2026

**ขอบเขต:** main runner เป็น proposed course model ใช้ scheduled stimulus และ kinematic body; contact demo ใช้ synthetic signals ไม่ใช่ ALCS terrain experiment ของ paper

## 1. ก่อนรัน: hypothesis และ architecture (10 นาที)

1. วาด S→controller→R_used→φ/stride→CPG→decoder→body ของ Lab แล้ววงจุดที่ยังไม่มี independent sensory feedback
2. เขียน hypothesis1 ข้อสำหรับ B1 เทียบ B2 พร้อมตัวชี้วัดและทิศทางที่คาด เช่น TV, latency/recovery, segmentfrequency หลีกเลี่ยงคำว่า “ดีขึ้น” โดยไม่มี metric
3. B3 ตัดอะไรออกจาก B2? สิ่งใดที่ยังคงมี memory?
4. ตาราง provenance: source equation1 รายการ, proposedcourseequation1 รายการ, expectedmeasurement1 รายการ และ metric ที่วัดไม่ได้ 1 รายการ

## 2. รัน comparison และตรวจเวลา (15 นาที)

รัน comparison ตาม README เปิด report เลือก B2 เลื่อน timeline ไป 10.00/10.05s แล้วเปิด B2_states.csv/B2_intervals.csv เพื่อยืนยัน

| command/input time | state end time | H_start | H_end | R_used | φที่ใช้ | stride_half ที่ใช้ |
|---|---|---|---|---|---|---|
| 10.00 | 10.05 | 0.0000 | 0.0400 | 0.0000 | 0.2000 | 0.0550 |
| 10.05 | 10.10 | 0.0400 | 0.0784 | 0.0400 | 0.2080 | 0.0554 |
| 20.00 | 20.05 | 0.9997 | 0.9597 | 0.9997 | 0.3999 | 0.0650 (0.064997) |s
อธิบายจาก CSV ว่าเหตุใด B1 command latency กับ state latency จึงต่างกัน: B1 ใช้ R_used = ทันที (command 10.00 มี R_used = 1) จึง command latency = 0 แต่ state ถูกบันทึกหลัง update ที่ 10.05 จึงช้า 0.05 s เป็นเรื่อง sampling ไม่ใช่ hardware latency

ตรวจ warmup/initialstates ใน config: ทุก condition เริ่ม CPG เหมือนกันหรือไม่? หลักฐานเหมือนกัน config มี warmup 10 s (φ = 0.2, α = 1.1) และ initial o1 = −0.02697, o2 = −0.56086 เท่ากันทุก condition

## 3. เปรียบเทียบผลและข้อจำกัด (15 นาที)

เติมจาก metrics และ segment_metrics พร้อมหน่วย ห้ามคัดลอกผล source paper มาใส่เป็นผล run นี้

| condition | TV φ(rad) | maxΔφ/step(rad) | TV stride(m) | cmd latency(s) | cmd recovery(s) | on frequency(Hz) | on distance(m) |
|---|---|---|---|---|---|---|---|
| B0 | 0.0000 | 0.0000 | 0.0000 | N/A | N/A | 0.6249 | 0.7787 |
| B1 | 0.4000 | 0.2000 | 0.0200 | 0.00 | 0.00 | 1.2684 | 1.8252 |
| B2 | 0.3998 | 0.0080 | 0.0200 | 0.15 | 2.85 | 1.2028 | 1.7063 |
| B3 | 0.3995 | 0.0080 | 0.0200 | 0.15 | 3.80 | 1.2258 | 1.7275 |

1. ผลข้อใดสนับสนุน hypothesis และผลข้อใดไม่สนับสนุน B2 (0.008) ต่ำกว่า B1 (0.2) ประมาณ 25 เท่า และ B2 มี latency 0.15 s ไม่สนับสนุน: TV ไม่ลด (0.3998 vs 0.4000 rad)
การลด
2. การลด TV ยืนยันว่าหุ่นยนต์ไม่ล้มหรือใช้พลังงานน้อยลงหรือไม่? ขาดข้อมูลอะไร? ขาดข้อมูลอะไร? ไม่ยืนยัน TV เป็นแค่ผลรวมการเปลี่ยน command ใน simulator ขาดข้อมูล body dynamics (แรง, CoM) และพลังงาน/torque
3. Bounds เหมือนกันทำให้ commandamplitude เท่ากันหรือไม่? ใช้ peak/trace ประกอบ ไม่จำเป็น ขึ้นกับ peak R_used ไม่มี clamp เกิดขึ้น และ mean ช่วง on ต่างกัน
4. ทำไมไม่ใช้ frequency เฉลี่ย 30s แทน pre/on/off? เพราะค่าเฉลี่ยผสมหลายช่วงที่ความถี่ต่างกัน และช่วง off ยังเป็น transient จึงไม่เรียก steady state

## 4. เปลี่ยนหนึ่งปัจจัยและตรวจ fault (20 นาที)

เลือก phi-only หรือ stride-only ตั้ง prediction ก่อนรัน ตรวจ parameter ที่คงที่จาก intervalCSV แล้วเปรียบเทียบ B1/B2 กับ bothmapping

สิ่งที่เปลี่ยน phi-only สิ่งที่คงที่stride_half metric หลักon frequency predictionความถี่ใกล้เคียง both แต่ distance ต่ำกว่า
ผลและข้อจำกัด causalclaim:สรุปว่า  กำหนดความถี่ และ stride เพิ่มระยะ ข้อจำกัด: run เดียว deterministic ไม่ใช่ independent trials และยังไม่ได้แยก interaction ของ φ กับ stride

รัน faultprofile เปิด input15.00 แล้วบันทึก:

| field | B2 value |
|---|---|
| fault at command15.00 | fault = 1 (S = NaN ที่ input 15.00) |
| H_used / R_used | 0.0 / 0.0 (H ก่อนหน้า = 0.9831) |
| φ / stride ที่ใช้ | 0.2000 rad / 0.055 m |
| H state15.05 | 0.0 |
| H state15.10 | 0.04 |

อธิบายว่า fallback ทำก่อนหรือหลัง command และเหตุใด policy นี้ยังไม่รับรอง hardware safety: Fallback ทำก่อน command: ที่เวลา 15.00 s เมื่อเกิด fault S=NaN ระบบรีเซ็ต h_used และ r_used เป็น 0 ทันที แม้ H ก่อนหน้าจะเท่ากับ 0.9831 ทำให้ใช้ค่า baseline varphi = 0.20rad,stride = 0.055m$ ในช่วง 5.00, 15.05 ทันที แล้วจึงเริ่มสะสม H ใหม่เป็น 0.04 ที่เวลา 15.10 s

## 5. Contact mini-lab (20 นาที)

เปิด contactreport เลือก cases ด้านล่าง เปรียบเทียบ SI, SIF, absoluteerror และ validity

| case | SI ของแต่ละขาโดยทั่วไป | SIF | absoluteerror | สิ่งที่อนุมานไม่ได้ |
|---|---|---|---|---|
| matched | +1 ทุกขา| 0| 0.0000| ไม่ได้พิสูจน์ว่าเดินบน terrain ได้ เพราะเป็น synthetic|
| gain-offset | +1 ทุกขา| ≈0| 0.1628| SI สูงไม่ได้แปลว่า amplitude/offset ตรงกัน|
| mixed-delay | LF/RM/LH = +1, RF/LM/RH ≈ 0|0.5| 0.2260| ไม่ระบุได้ว่าความต่างเกิดจาก delay หรือสาเหตุอื่น|
| all-inverted | −1 ทุกขา|≈0|0.6314| SIF=0 ไม่ได้แปลว่าไม่มีความผิดปกติ|
| constant | N/A (variance=0)|N/A|0.0000| อนุมาน SI=0 ไม่ได้ ต้องเป็น N/A|

1. ทำไม gain-offset ให้ correlation สูงแม้ error ไม่เป็น 0? Pearson วัดเฉพาะรูปร่างความสัมพันธ์เชิงเส้น ไม่สน gain/offset จึงได้ SI = 1 แต่ expected−actuaส ยังมีค่า
2. เมื่อทุกขา inverted ทำไม SIF จึงยังเป็น 0? release ที่ SIF0 มีค่าเท่าไร? −1 เท่ากัน SD ระหว่างขาจึงเป็น 0 release = 1
3. constant ควรเป็น SI0 หรือ N/A?0 ทำให้ Pearson ไม่นิยาม (คำนวณไม่ได้ ไม่ใช่ไม่มี correlation)
4. fault หนึ่ง sample มีผลต่อ rollingwindows กี่ rows ไม่นับ startup49rows? ตรวจ CSV50 rows เพราะ NaN อยู่ในทุก window ที่ครอบ sample นั้น; window แรกที่ valid คือ 2.45 s
5. pairedPearson ของ demo มีสถานะ source/proposed ใด? ต่อ Cg/MI แล้วหรือยัง? ป็น proposed course definition ไม่ใช่ Eq.(3) ของ paper และยังไม่ได้ต่อ Cg/MI

## 6. ส่งงานและ exit ticket (10 นาที)

ส่ง prediction ก่อนรัน, config/manifest/rawCSV ของ comparison+one-factorrun+fault, contactmetrics และ CSV หนึ่ง case ที่อภิปราย, ตารางพร้อมหน่วยและกราฟ 2 รูป พร้อมรายงาน 2–3 หน้า บอกคำสั่งและ Pythonversion เพื่อรันซ้ำ

Exit: เขียนหนึ่ง claim ที่ข้อมูลรองรับ และหนึ่ง claim ที่ยังรองรับไม่ได้ พร้อมชื่อ metric/ข้อมูลที่ต้องเพิ่ม

**Rubric20 คะแนน:** architecture/provenance4; timing/fault4; reproducibility/data3; quantitativecomparison/one-factor5; interpretation/contact/N/A4 คะแนนมาจากเหตุผลกับหลักฐาน ไม่ได้ให้เต็มเพราะ runner รันผ่านหรือเพราะผล “ดีขึ้น” ตามคาด

**Workshop 25 นาทีในคาบ Week05:** ทำข้อ 1 แบบย่อ 5 นาที, ข้อ 2 10 นาที, ข้อ 3 10 นาที ส่วน one-factor/fault/contact เป็น extended lab หรือการบ้าน ใช้เวลารวม 90 นาทีตามใบงาน ไม่รวมเวลาติดตั้ง Python
