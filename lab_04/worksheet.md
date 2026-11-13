# ใบงาน Lab04 (รายงาน 1–2 หน้า)

ชื่อ/รหัส วทัญญู ชำนาญ (6752500096), ณัฐพงศ์ เวชยานนท์ (6752500177), นิธิวัฒน์ สุทธิ (6752500037), ปุญญพัฒน์ ปราณีชาติ (6752500355) กลุ่ม ภาคีนกอีก๋อย วันที่ 11/7/2026  code version/hash student_hormone.py sha256 bc215a2e08bf8efe… (Python 3.10)

## A. ก่อนรัน (10 นาที)

วาด block diagram แล้วเขียนประโยคเชื่อมแต่ละคู่ S, P/C/B, H, R, phi/stride ให้เห็นว่า state เก็บประวัติอย่างไร

| Comparison | prediction ก่อนรัน | เหตุผลจาก term ในสมการ | ผลจริงหลังรัน |
|---|---|---|---|
| C2 vs C1 | H ขึ้นเร็วกว่า ถึงเพดานเร็ว | k_prod 0.8→1.2 ทำให้ P ใหญ่ขึ้น | rise 1.05 s (C1 2.70 s), AUC 10.67, recovery เท่า C1 (2.85 s) |
| C3 vs C1 | H ฟื้นช้ากว่ามาก | k_clear 0.6→0.25 ทำให้ C ลด อัตราลดช่วงปิดเหลือ 0.45 /s | recovery 5.10 s (C1 2.85 s) ช้ากว่า 2.25 s, AUC 11.39 |
| C4 vs C1 | H ฟื้นช้ากว่า | k_bind=0 เอา B ออก อัตราลดช่วงปิดเหลือ 0.6 /s | recovery 3.80 s (C1 2.85 s), rise 1.70 s |
| C0 vs C1 | C0 ตอบสนองทันที ไม่มีค่าหน่วง | C0 ไม่มี H สถานะ R = S โดยตรง | C0 latency 0.05 s, rise 0 s; C1 latency 0.15 s, rise 2.70 s |

เขียนว่า prediction ใดอาจเปลี่ยนเพราะ H มี upper bound=1 __________________

## B. เติม code และคำนวณมือ (20 นาที)

1. แยก source equation กับ proposed course model คนละกรอบ
2. เติม receptor ก่อน แล้วทดสอบ H=.2, H_min=.1, H_max=.5
3. เติม step: เก็บ H_old และ R_old ก่อนคำนวณ removal
4. เมื่อ H_old=0,S=1 ให้คำนวณ P,C,B,H_raw,H_new,R_new,phi,stride แล้วทำรอบถัดไป
5. รัน checker เก็บ output หากไม่ผ่านให้บันทึก case และเหตุที่แก้

| input_time_s | time_s | P | C | B | H_raw | H | R | phi |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
|10.00|10.05|0.8|0|0|0.0400|0.0400|0.0400|0.2080|
|10.05|10.10|0.8|0.024|0.008|0.0784|0.0784|0.0784|0.21568|

แถว CSV ที่เลือกสอดคล้องกับ time convention อย่างไร? time_s คือเวลาหลัง update; input 10.00 และ 10.05 ให้ state ที่ 10.05 และ 10.10 ส่วนสองแถวแรกของไฟล์ยังเป็น S = 0

## C. Controlled comparison (20 นาที)

รัน C0–C4 ใช้ dt,duration,H0,stimulus,mapping เดียวกัน เปิด report.html และกรอกค่าจาก metrics.json ไม่อ่านค่าด้วยสายตาอย่างเดียว

| Condition | peak_H | AUC_H | latency s | rise s | recovery s | upper clamp fraction | phi TV rad |
|---|---|---|---|---|---|---|---|
|C0|N/A|N/A|0.05|0.00|0.05|N/A|0.4000|
|C1|0.9997|9.9996|0.15|2.70|2.85|0.0000|0.3998|
|C2|1.0000|10.6724|0.10|1.05|2.85|0.2900|0.3999|
|C3|1.0000|11.3891|0.15|1.45|5.10|0.2733|0.3979|
|C4|1.0000|10.7547|0.15|1.70|3.80|0.2583|0.3995|

ตอบด้วยตัวเลข: C3 ฟื้นช้ากว่า C1 เท่าไร? C2/C3 peak เท่ากันหรือไม่ และ metric ใดแยกสองระบบนี้ได้? C0 มี H หรือไม่? TV ที่ต่ำกว่าเพียงอย่างเดียวพิสูจน์คุณภาพ gait ได้หรือไม่?
C3 ฟื้นช้ากว่า C1 เท่าไร: 5.10 − 2.85 = 2.25 s (ประมาณ 1.8 เท่า) เพราะ k_clear ลดจาก 0.6 เป็น 0.25
C2/C3 peak เท่ากันหรือไม่: เท่ากัน (1.0) เพราะ clamp แยกได้ด้วย recovery (2.85 กับ 5.10 s), AUC (10.67 กับ 11.39), rise (1.05 กับ 1.45 s) และ clamp fraction (0.29 กับ 0.2733)
C0 มี H หรือไม่: ไม่มี (R = S โดยตรง) ใน CSV เป็นค่าว่างและใน JSON เป็น null ไม่ใช่ 0
TV ต่ำอย่างเดียวพิสูจน์คุณภาพ gait ได้หรือไม่: ไม่ได้ เพราะ Lab04 ไม่ได้จำลอง gait หรือวัด body motion และ phi TV ต่างกันน้อยมาก (0.398–0.400 rad)

## D. Extreme tests และ handoff (10 นาที)

รัน zero,one,spike,fault ของ C1 ตรวจว่า spike มี on interval เพียงหนึ่งแถว fault มี flag และ state reset แล้วเริ่มกลับได้ แยก software bounds จาก actuator limits และ emergency stop

ทดลองส่ง contract เดิมของ Week03 ถ้ามี แล้วตรวจ phi/stride ที่ R=0 และ R=1 ระบุสิ่งที่ Lab04 ยังไม่ได้ทดสอบ gait/CPG, พลังงาน, ความเสถียร, actuator limits, emergency stop และฮาร์ดแวร์จริง
sssssss
## E. สรุปส่งงาน (10 นาที)

เขียน 3 ย่อหน้า: (1) กลไกและ provenance (2) prediction ที่ข้อมูลสนับสนุน/ปฏิเสธพร้อมตัวเลข (3) ข้อจำกัดและการทดลอง Week05 ที่ต้องทำต่อ แนบคำสั่งรันและ config/hash ทุกข้อสรุปต้องอ้าง metric หรือ timestamp

Checklist: □ code □ comparison CSV 5 files □ extreme CSV 4 files □ config □ plots □ metrics □ report □ คำสั่งรันซ้ำ
