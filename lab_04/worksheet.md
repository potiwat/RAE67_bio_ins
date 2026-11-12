# ใบงาน Lab04 (รายงาน 1–2 หน้า)

ชื่อ นายนฤเบศ หนูเจริญ รหัสนักศึกษา 6752500347 code version/hash: student_hormone.py SHA256 `cb5962b0ff5108e6987c111bb7b75ef1a09640639d2b3a62faf3de755ed37e4d` (Python 3.13.7)

## A. ก่อนรัน (10 นาที)

Block diagram: `figures/block_diagram.png`

- S → P: P = k_prod·S stimulus กำหนดอัตราการสร้าง H
- H_old → C และ R_old → B: H เดิมกับ receptor เดิมกำหนดอัตราการกำจัด
- P, C, B → H: H_new = clamp(H_old + dt(P − C − B), 0, 1) H เป็น state ที่เก็บผลของ stimulus ในอดีต หลัง S ดับ H ค่อย ๆ ลดลง ไม่หายทันที
- H → R → phi/stride: receptor normalize/clamp แล้ว bounded mapping แปลงเป็นคำสั่ง

> หมายเหตุ: prediction และเหตุผลเขียนหลังจากรันโปรแกรมแล้ว จึงเขียนเชิงคุณภาพจากหลักการเท่านั้น

| Comparison | prediction ก่อนรัน | เหตุผลจาก term ในสมการ | ผลจริงหลังรัน |
|---|---|---|---|
| C2 vs C1 | H ขึ้นเร็วกว่าและอาจชน upper bound | P = k_prod·S ใหญ่ขึ้น | latency 0.10 vs 0.15 s, rise 1.05 vs 2.70 s, AUC 10.672 vs 10.000, upper clamp 0.290 vs 0 |
| C3 vs C1 | ฟื้นช้ากว่าหลัง S ดับ | C = k_clear·H_old เล็กลง | recovery 5.10 vs 2.85 s, AUC 11.389 |
| C4 vs C1 | H สูงขึ้นและฟื้นช้ากว่าเล็กน้อย | ไม่มี B | recovery 3.80 vs 2.85 s, AUC 10.755 |
| C0 vs C1 | R ตาม S ทันที ไม่มี memory | R = S ไม่มี H | latency 0.05 s, rise 0.00 s, recovery 0.05 s, peak_H N/A |

เขียนว่า prediction ใดอาจเปลี่ยนเพราะ H มี upper bound=1: ความคิดที่ว่า C2 หรือ C3 จะมี peak_H สูงกว่า C1 ไม่ถูก เพราะ C2, C3, C4 มี peak_H = 1.0000 เท่ากันจาก clamp ต้องดู AUC, rise และ recovery แทน

## B. เติม code และคำนวณมือ (20 นาที)

1. Source (Week04 อ้าง Homchanthanakul et al. 2019): Hc(t) = β·Hc(t−1) + Hg(t) − Hr(t), Hg = α·f(S), Hr = Σγᵢ·Receptorᵢ
   Proposed course model: P = k_prod·S, C = k_clear·H_old, B = k_bind·R_old, H_raw = H_old + dt(P − C − B), H_new = clamp(H_raw, 0, 1), dt = 0.05 s
2. receptor(0.2, 0.1, 0.5) = (0.2 − 0.1)/(0.5 − 0.1) = 0.25 (อยู่ใน [0, 1] จึงไม่ถูก clamp)
3. step ใช้ H_old และ R_old คำนวณ P, C, B ก่อน แล้วอัปเดต H ครั้งเดียว
4. คำนวณด้วย Python ตรงกับ CSV (C1, H_old = 0, S = 1)
5. checker ผ่าน 13/13 case

| input_time_s | time_s | P | C | B | H_raw | H | R | phi |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
|10.00|10.05|0.8000|0.0000|0.0000|0.0400|0.0400|0.0400|0.2080|
|10.05|10.10|0.8000|0.0240|0.0080|0.0784|0.0784|0.0784|0.2157|

stride_half ที่ 10.05 และ 10.10 s คือ 0.05540 และ 0.05578 m

แถว CSV ที่เลือกสอดคล้องกับ time convention อย่างไร? time_s เป็นเวลาหลัง update แถว input_time_s = 10.00 คือ update แรกที่ S = 1 จึงได้ state ที่ 10.05 s และ update ที่สองได้ 10.10 s สองแถวแรกของไฟล์ยังเป็น S = 0

## C. Controlled comparison (20 นาที)

ค่าจาก `results/comparison/metrics.json`

| Condition | peak_H | AUC_H | latency s | rise s | recovery s | upper clamp fraction | phi TV rad |
|---|---|---|---|---|---|---|---|
|C0|N/A|N/A|0.05|0.00|0.05|N/A|0.4000|
|C1|0.9997|9.9996|0.15|2.70|2.85|0.000|0.3998|
|C2|1.0000|10.6724|0.10|1.05|2.85|0.290|0.3999|
|C3|1.0000|11.3891|0.15|1.45|5.10|0.273|0.3979|
|C4|1.0000|10.7547|0.15|1.70|3.80|0.258|0.3995|

- C3 ฟื้นช้ากว่า C1 5.10 − 2.85 = 2.25 s
- C2 กับ C3 มี peak เท่ากัน (1.0000) แยกได้ด้วย recovery (2.85 vs 5.10 s), AUC (10.672 vs 11.389) และ rise (1.05 vs 1.45 s)
- C0 ไม่มี H (ช่อง H ใน CSV ว่าง)
- TV ต่ำอย่างเดียวพิสูจน์คุณภาพ gait ไม่ได้ phi TV ทุก condition อยู่ที่ 0.398–0.400 rad ทั้งที่ dynamics ต่างกัน และ Lab04 ยังไม่ได้รัน gait

## D. Extreme tests และ handoff (10 นาที)

- zero: H = R = 0 ตลอด, phi 0.20 rad, stride 0.055 m
- one: H ขึ้นจนถึง 1.0000 ที่ 30.00 s (P = 0.8 = C + B สมดุลพอดี ไม่ clamp), phi 0.40 rad, stride 0.065 m
- spike: on interval 1 แถว (0.05 s ที่ input 10.00) H สูงสุด 0.0400 แล้วลดลง (10.10 s: 0.0384)
- fault: 15.00 s H = 0.9831 → 15.05 s fault = 1, H = R = 0, phi 0.20, stride 0.055 → 15.10 s H = 0.0400 เริ่มสะสมใหม่

Software bounds จำกัดแค่ค่าคำสั่งในโค้ด ส่วน actuator limits เป็นขีดจำกัดทางกายภาพของ driver/hardware และ emergency stop ต้องตัดกำลังได้โดยไม่พึ่งซอฟต์แวร์

ทดลองส่ง contract ของ Lab03 (`--contract ../lab_03/results/week4_bridge/handoff_contract.json`) runner รับได้และผล C1 เท่าเดิม ที่ R = 0 ได้ phi 0.20 rad, stride 0.055 m และ R = 1 ได้ phi 0.40 rad, stride 0.065 m อยู่ใน bounds ทั้งคู่ สิ่งที่ Lab04 ยังไม่ได้ทดสอบ: CPG, gait, body motion, พลังงาน, เสถียรภาพ, noise ของ sensor และหุ่นยนต์จริง

## E. สรุปส่งงาน (10 นาที)

(1) H เป็น state ที่สะสม P − C − B ทุก step เมื่อเปิด stimulus ที่ 10 s H ของ C1 เป็น 0.0400 และ 0.0784 ที่ 10.05 และ 10.10 s และหลังปิดที่ 20 s H ค่อย ๆ ลดลง (recovery 2.85 s) สมการ source มาจาก Week04 ที่อ้าง Homchanthanakul et al. (2019) ส่วนรูป Euler ที่แยกอัตราและ bounds เป็น proposed course model

(2) ข้อมูลสนับสนุนว่า production เพิ่มทำให้ตอบเร็วขึ้น (C2 latency 0.10 vs 0.15 s, rise 1.05 vs 2.70 s) และ clearance ลดทำให้ฟื้นช้า (C3 recovery 5.10 vs 2.85 s) แต่ปฏิเสธความคิดว่า peak จะสูงขึ้น เพราะ C2–C4 ชน upper bound ที่ 1.0000 เท่ากัน (clamp fraction 0.290, 0.273, 0.258)

(3) ผลนี้เป็น subsystem simulation แบบ deterministic ไม่มี CPG ไม่มี body motion และไม่ได้ทดสอบกับหุ่นยนต์จริง Week05 ต้องต่อ R เข้ากับ CPG แล้วเทียบ mapping แบบ both, phi-only และ stride-only เพื่อแยกผล hormone ออกจากผล CPG และ mapping

คำสั่งรันซ้ำ:

```sh
python check_submission.py --student-file student_hormone.py
python lab04.py --controller-source student --condition all --profile step --output-dir results/comparison
python lab04.py --controller-source student --condition C1 --profile zero --output-dir results/zero
python lab04.py --controller-source student --condition C1 --profile one --output-dir results/one
python lab04.py --controller-source student --condition C1 --profile spike --output-dir results/spike
python lab04.py --controller-source student --condition C1 --profile fault --output-dir results/fault
python lab04.py --controller-source student --condition C1 --profile step --contract ../lab_03/results/week4_bridge/handoff_contract.json --output-dir results/lab03_contract
```

Checklist: ☑ code ☑ comparison CSV 5 files ☑ extreme CSV 4 files ☑ config ☑ plots ☑ metrics □ report ☑ คำสั่งรันซ้ำ
