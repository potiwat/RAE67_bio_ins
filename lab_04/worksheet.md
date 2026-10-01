# ใบงาน Lab04 (รายงาน 1–2 หน้า)

ชื่อ/รหัส __________________ กลุ่ม ______ วันที่ ______ code version/hash ______

## A. ก่อนรัน (10 นาที)

วาด block diagram แล้วเขียนประโยคเชื่อมแต่ละคู่ S, P/C/B, H, R, phi/stride ให้เห็นว่า state เก็บประวัติอย่างไร

| Comparison | prediction ก่อนรัน | เหตุผลจาก term ในสมการ | ผลจริงหลังรัน |
|---|---|---|---|
| C2 vs C1 | | | |
| C3 vs C1 | | | |
| C4 vs C1 | | | |
| C0 vs C1 | | | |

เขียนว่า prediction ใดอาจเปลี่ยนเพราะ H มี upper bound=1 __________________

## B. เติม code และคำนวณมือ (20 นาที)

1. แยก source equation กับ proposed course model คนละกรอบ
2. เติม receptor ก่อน แล้วทดสอบ H=.2, H_min=.1, H_max=.5
3. เติม step: เก็บ H_old และ R_old ก่อนคำนวณ removal
4. เมื่อ H_old=0,S=1 ให้คำนวณ P,C,B,H_raw,H_new,R_new,phi,stride แล้วทำรอบถัดไป
5. รัน checker เก็บ output หากไม่ผ่านให้บันทึก case และเหตุที่แก้

| input_time_s | time_s | P | C | B | H_raw | H | R | phi |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
|10.00|10.05||||||||
|10.05|10.10||||||||

แถว CSV ที่เลือกสอดคล้องกับ time convention อย่างไร? __________________

## C. Controlled comparison (20 นาที)

รัน C0–C4 ใช้ dt,duration,H0,stimulus,mapping เดียวกัน เปิด report.html และกรอกค่าจาก metrics.json ไม่อ่านค่าด้วยสายตาอย่างเดียว

| Condition | peak_H | AUC_H | latency s | rise s | recovery s | upper clamp fraction | phi TV rad |
|---|---|---|---|---|---|---|---|
|C0||||||||
|C1||||||||
|C2||||||||
|C3||||||||
|C4||||||||

ตอบด้วยตัวเลข: C3 ฟื้นช้ากว่า C1 เท่าไร? C2/C3 peak เท่ากันหรือไม่ และ metric ใดแยกสองระบบนี้ได้? C0 มี H หรือไม่? TV ที่ต่ำกว่าเพียงอย่างเดียวพิสูจน์คุณภาพ gait ได้หรือไม่?

## D. Extreme tests และ handoff (10 นาที)

รัน zero,one,spike,fault ของ C1 ตรวจว่า spike มี on interval เพียงหนึ่งแถว fault มี flag และ state reset แล้วเริ่มกลับได้ แยก software bounds จาก actuator limits และ emergency stop

ทดลองส่ง contract เดิมของ Week03 ถ้ามี แล้วตรวจ phi/stride ที่ R=0 และ R=1 ระบุสิ่งที่ Lab04 ยังไม่ได้ทดสอบ __________________________________

## E. สรุปส่งงาน (10 นาที)

เขียน 3 ย่อหน้า: (1) กลไกและ provenance (2) prediction ที่ข้อมูลสนับสนุน/ปฏิเสธพร้อมตัวเลข (3) ข้อจำกัดและการทดลอง Week05 ที่ต้องทำต่อ แนบคำสั่งรันและ config/hash ทุกข้อสรุปต้องอ้าง metric หรือ timestamp

Checklist: □ code □ comparison CSV 5 files □ extreme CSV 4 files □ config □ plots □ metrics □ report □ คำสั่งรันซ้ำ
