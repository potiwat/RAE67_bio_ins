# ใบงาน Lab04 (รายงาน 1–2 หน้า)

ชื่อ/รหัส __________________ กลุ่ม ______ วันที่ 11/11/2026 code version/hash ______

## A. ก่อนรัน (10 นาที)

Block diagram: `S → P=k_prod·S`; `H_old → C=k_clear·H_old` และ `H_old → R_old → B=k_bind·R_old`; `H_old + dt(P−C−B) → clamp → H_new → receptor → R_new → bounded mapping → phi/stride`

เหตุและผล: S กำหนดอัตราการผลิต P; H_old กำหนด clearance C และ receptor R_old ที่ใช้หา binding B; ผลสุทธิ P−C−B ปรับสถานะ H โดยมีประวัติจาก H_old; receptor อ่าน H_new แล้ว mapping จำกัดคำสั่ง phi และ stride ให้อยู่ใน bounds

| Comparison | prediction ก่อนรัน | เหตุผลจาก term ในสมการ | ผลจริงหลังรัน |
|---|---|---|---|
| C2 vs C1 | H เพิ่มเร็วกว่า; peak อาจเท่ากันเมื่อชน upper bound | `k_prod` สูงขึ้นทำให้ P สูงขึ้น แต่ H ถูก clamp ที่ 1 | latency 0.10 เทียบ 0.15 s; peak_H 1.000 เทียบ 0.999715; AUC_H 10.672410 เทียบ 9.999644 |
| C3 vs C1 | H สะสม/คงอยู่มากกว่าและ recovery ช้ากว่า | `k_clear` ต่ำลงทำให้ C ลดลง | recovery 5.10 เทียบ 2.85 s; AUC_H 11.389145 เทียบ 9.999644 |
| C4 vs C1 | H/AUC มีแนวโน้มสูงขึ้น | `k_bind=0` ทำให้ไม่มี B มาหักออกจาก H | AUC_H 10.754720 เทียบ 9.999644; peak_H 1.000 เทียบ 0.999715 |
| C0 vs C1 | C0 ตอบสนอง R ตรงกับ S ส่วน C1 มี lag และ H state | C0 ไม่มี hormone state; C1 คำนวณ H แล้วอ่าน receptor | latency ที่วัดได้ 0.05 เทียบ 0.15 s; C0 ไม่มี H (N/A) |

เขียนว่า prediction ใดอาจเปลี่ยนเพราะ H มี upper bound=1: แม้ C2/C3/C4 สร้าง H มากกว่าหรือคงอยู่ได้นานกว่า peak_H ก็อาจเท่ากับ C1 ที่ 1.0 ได้ ต้องใช้ AUC, recovery และ clamp fraction ร่วมเปรียบเทียบ

## B. เติม code และคำนวณมือ (20 นาที)

1. สมการต้นทางตามเอกสารประกอบ: `Hc(t)=beta Hc(t−1)+Hg(t)−Hr(t)`, `Hg=alpha f(S)`, `Hr=sum(gamma_i Receptor_i)`; ส่วนค่าตัวเลขในแล็บเป็น proposed course model แบบ Euler แยก `P=k_prod S`, `C=k_clear H_old`, `B=k_bind R_old` และ clamp H
2. ทดสอบ receptor ที่ H=.2, H_min=.1, H_max=.5: `(0.2−0.1)/(0.5−0.1)=0.25`
3. ใน step ใช้ H_old และ R_old ก่อนคำนวณ P/C/B แล้วอัปเดต H เพียงครั้งเดียว
4. เมื่อ H_old=0,S=1 (C1): P=.8, C=0, B=0, H_raw=H_new=.04, R_new=.04, phi=.208 rad, stride=.0554 m; รอบถัดไป H=.0784, R=.0784, phi=.21568 rad, stride=.055784 m
5. รัน checker: 13/13 cases ผ่าน; output เก็บใน `results/submission_check.json`

| input_time_s | time_s | P | C | B | H_raw | H | R | phi |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
|10.00|10.05|0.8000|0.0000|0.0000|0.0400|0.0400|0.0400|0.2080|
|10.05|10.10|0.8000|0.0240|0.0080|0.0784|0.0784|0.0784|0.2157|

แถว CSV ที่เลือกสอดคล้องกับ time convention อย่างไร? input_time_s ระบุเวลาเริ่ม update ส่วน time_s ระบุเวลาสถานะหลัง update ดังนั้น input 10.00 จึงได้ state ที่ 10.05

## C. Controlled comparison (20 นาที)

รัน C0–C4 ใช้ dt,duration,H0,stimulus,mapping เดียวกัน เปิด report.html และกรอกค่าจาก metrics.json ไม่อ่านค่าด้วยสายตาอย่างเดียว

| Condition | peak_H | AUC_H | latency s | rise s | recovery s | upper clamp fraction | phi TV rad |
|---|---|---|---|---|---|---|---|
|C0|N/A|N/A|0.050|0.000|0.050|N/A|0.400000|
|C1|0.999715|9.999644|0.150|2.700|2.850|0.000000|0.399829|
|C2|1.000000|10.672410|0.100|1.050|2.850|0.290000|0.399943|
|C3|1.000000|11.389145|0.150|1.450|5.100|0.273333|0.397890|
|C4|1.000000|10.754720|0.150|1.700|3.800|0.258333|0.399548|

ตอบด้วยตัวเลข: C3 ฟื้นช้ากว่า C1 เท่าไร? C2/C3 peak เท่ากันหรือไม่ และ metric ใดแยกสองระบบนี้ได้? C0 มี H หรือไม่? TV ที่ต่ำกว่าเพียงอย่างเดียวพิสูจน์คุณภาพ gait ได้หรือไม่?

ผลเปรียบเทียบ: C3 recovery ช้ากว่า C1 อยู่ 2.25 s (5.10−2.85); C2/C3 peak_H เท่ากันที่ 1.000 แต่ AUC_H ต่างกัน 10.672410 กับ 11.389145 และ recovery ต่างกัน 2.85 กับ 5.10 s; C0 ไม่มี H (N/A); TV ที่ต่ำกว่าไม่ใช่หลักฐานคุณภาพ gait เพราะ Lab04 ไม่ได้จำลอง gait

## D. Extreme tests และ handoff (10 นาที)

รัน zero,one,spike,fault ของ C1 ตรวจว่า spike มี on interval เพียงหนึ่งแถว fault มี flag และ state reset แล้วเริ่มกลับได้ แยก software bounds จาก actuator limits และ emergency stop

ทดลองส่ง contract เดิมของ Week03 จาก `..\lab_03\results\week4_bridge\handoff_contract.json` แล้วตรวจ phi/stride ที่ R=0 และ R=1: R=0 ให้ phi=0.200 rad, stride=0.055 m; R=1 ให้ phi=0.400 rad, stride=0.065 m ระบุสิ่งที่ Lab04 ยังไม่ได้ทดสอบ: การรัน CPG/gait แบบ integrated, body motion, actuator, contact force และ hardware safety

ผล extreme tests: zero มี peak_H=0 และ fault_count=0; one มี peak_H≈1; spike มี stimulus=1 หนึ่ง update ที่ input_time_s=10.00 และ peak_H=0.04; fault_count=1 โดย input_time_s=15.00 ส่งผลให้ H=R=0 ที่ state time_s=15.05 จากนั้น state เริ่มสะสมใหม่ที่ 15.10

## E. สรุปส่งงาน (10 นาที)

เขียน 3 ย่อหน้า: (1) กลไกและ provenance (2) prediction ที่ข้อมูลสนับสนุน/ปฏิเสธพร้อมตัวเลข (3) ข้อจำกัดและการทดลอง Week05 ที่ต้องทำต่อ แนบคำสั่งรันและ config/hash ทุกข้อสรุปต้องอ้าง metric หรือ timestamp

Checklist: ☑ code ☑ comparison CSV 5 files ☑ extreme CSV 4 files ☑ config ☑ plots ☑ metrics ☑ report ☑ คำสั่งรันซ้ำ

คำสั่งรันซ้ำ (จากโฟลเดอร์ `lab_04`, ใช้ output directories ว่าง):

```powershell
python check_submission.py --student-file student_hormone.py
python lab04.py --controller-source student --condition all --profile step --contract ..\lab_03\results\week4_bridge\handoff_contract.json --output-dir results\comparison
python lab04.py --controller-source student --condition C1 --profile zero --contract ..\lab_03\results\week4_bridge\handoff_contract.json --output-dir results\zero
python lab04.py --controller-source student --condition C1 --profile one --contract ..\lab_03\results\week4_bridge\handoff_contract.json --output-dir results\one
python lab04.py --controller-source student --condition C1 --profile spike --contract ..\lab_03\results\week4_bridge\handoff_contract.json --output-dir results\spike
python lab04.py --controller-source student --condition C1 --profile fault --contract ..\lab_03\results\week4_bridge\handoff_contract.json --output-dir results\fault
```
