# ใบงาน Lab04 (รายงาน 1–2 หน้า)

ชื่อ/รหัส นางสาวสมฤทัย แก้วสุข รหัสนักศึกษา 6752500185  วันที่ ______  code version/hash student_hormone.py SHA256 10f95bd776df33723a46edef8ac8920ba7072259beee898b5fe85f69b8fb56b5

## A. ก่อนรัน (10 นาที)

![block diagram](figures/block_diagram.png)

S เพิ่ม production P → P ทำให้ H เพิ่ม ขณะที่ clearance C ลด H ตาม H_old และ binding B ลด H ตาม R_old → H ใหม่เกิดจาก H_old บวกผลสุทธิ dt·(P−C−B) H จึงเก็บประวัติของ stimulus ไว้ (ยังไม่หายทันทีเมื่อ S เป็น 0) → receptor แปลง H เป็น R ช่วง 0–1 → R ใช้ปรับ phi และ stride ผ่าน bounded mapping

> หมายเหตุ: prediction เขียนหลังจากรันโปรแกรมแล้ว คอลัมน์ prediction และเหตุผลจึงเขียนเชิงคุณภาพจากสมการเท่านั้น ตัวเลขอยู่ในคอลัมน์ผลจริง

| Comparison | prediction ก่อนรัน | เหตุผลจาก term ในสมการ | ผลจริงหลังรัน |
|---|---|---|---|
| C2 กับ C1 | H ขึ้นเร็วกว่าและสูงกว่า C1 ช่วงเปิด stimulus | P = k_prod·S ใหญ่ขึ้น ส่วน C และ B เท่าเดิม ผลสุทธิ P−C−B จึงเป็นบวกมากขึ้น | peak_H 1.0000 (ชน upper bound) เทียบกับ 0.9997, latency 0.10 s เทียบกับ 0.15 s, rise 1.05 s เทียบกับ 2.70 s, AUC 10.672 เทียบกับ 9.9996, recovery 2.85 s เท่ากัน upper clamp 0.290 |
| C3 กับ C1 | H สะสมสูงกว่าและลดลงช้ากว่ามากหลังปิด stimulus | C = k_clear·H_old เล็กลง H จึงถูกกำจัดช้า ทั้งช่วงเปิดและช่วงปิด | peak_H 1.0000, AUC 11.389 (สูงสุด), rise 1.45 s, recovery 5.10 s เทียบกับ 2.85 s ของ C1 ช้ากว่า 2.25 s upper clamp 0.273 |
| C4 กับ C1 | H สูงขึ้นและฟื้นช้าลงเล็กน้อย | ตัด B = k_bind·R_old ออก จึงเหลือแค่ clearance ที่ลด H | peak_H 1.0000, AUC 10.755, rise 1.70 s, recovery 3.80 s ช้ากว่า C1 0.95 s upper clamp 0.258 |
| C0 กับ C1 | C0 ตอบสนองทันทีและหยุดทันที ไม่มีความจำ | C0 ใช้ R = S โดยตรง ไม่มี state H จึงไม่มี P/C/B | C0 ไม่มี H (peak_H และ AUC เป็น N/A), latency 0.05 s (ความละเอียดของ log), rise 0.00 s, recovery 0.05 s เทียบกับ C1 latency 0.15 s, rise 2.70 s, recovery 2.85 s |

เขียนว่า prediction ใดอาจเปลี่ยนเพราะ H มี upper bound=1: prediction ว่า C2, C3, C4 จะมี peak สูงกว่า C1 อาจไม่จริงในเชิงตัวเลข เพราะ H ถูก clamp ไว้ที่ 1 ทั้งสามเงื่อนไขจึงมี peak_H = 1.0000 เท่ากันหมด ผลต่างไปปรากฏที่ AUC, rise time, recovery และ upper clamp fraction แทน (C2 0.290, C3 0.273, C4 0.258 ส่วน C1 = 0)

## B. เติม code และคำนวณมือ (20 นาที)

1. สมการ source: จากเอกสาร Week04 ที่อ้าง Homchanthanakul et al. (2019), IROS, DOI 10.1109/IROS40897.2019.8968580 Hc(t) = β·Hc(t−1) + Hg(t) − Hr(t),   Hg(t) = α·f(S(t)),   Hr(t) = Σ γᵢ·Receptorᵢ(t)
   proposed course model: R_old = clamp((H_old − H_min)/(H_max − H_min), 0, 1); P = k_prod·S,  C = k_clear·H_old,  B = k_bind·R_old   [normalized H / s]; H_raw = H_old + dt·(P − C − B),  H_new = clamp(H_raw, 0, 1),  R_new = receptor(H_new); phi = clamp(0.20 + 0.20·R_new, 0.10, 0.45) rad,  stride_half = clamp(0.055 + 0.010·R_new, 0.040, 0.070) m; dt = 0.05 s, duration 30 s, H0 = 0 (เป็น proposed course model ไม่ได้แทน β ด้วย k_clear โดยตรง)
2. receptor(H=0.2, H_min=0.1, H_max=0.5) = (0.2−0.1)/(0.5−0.1) = 0.25
3. step เก็บ H_old และ R_old ก่อนคำนวณ P, C, B แล้วอัปเดต H ครั้งเดียว
4. คำนวณมือ (ตารางด้านล่าง) ตรงกับ C1_step.csv
5. check_submission.py ผ่าน 13/13 case

| input_time_s | time_s | P | C | B | H_raw | H | R | phi |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
|10.00|10.05|0.8000|0.0000|0.0000|0.0400|0.0400|0.0400|0.2080|
|10.05|10.10|0.8000|0.0240|0.0080|0.0784|0.0784|0.0784|0.2157|

แถว CSV ที่เลือกสอดคล้องกับ time convention อย่างไร? แถวแรกของไฟล์ (time_s = 0.00 และ 0.05) ยังอยู่ช่วง S = 0 ค่าทุกตัวจึงเป็น 0 time_s ในแต่ละแถวคือเวลาหลัง update ส่วน input_time_s คือเวลาต้นช่วงที่ใช้ stimulus stimulus เปิดที่ input_time_s = 10.00 ผลจึงอยู่ในแถว time_s = 10.05 (H = 0.0400) และ update ถัดไปอยู่ที่ 10.10 (H = 0.0784) ตรงกับที่คำนวณมือ

## C. Controlled comparison (20 นาที)

| Condition | peak_H | AUC_H | latency s | rise s | recovery s | upper clamp fraction | phi TV rad |
|---|---|---|---|---|---|---|---|
|C0|N/A (ไม่มี H)|N/A|0.05|0.00|0.05|N/A|0.4000|
|C1|0.9997|9.9996|0.15|2.70|2.85|0.000|0.3998|
|C2|1.0000|10.6724|0.10|1.05|2.85|0.290|0.3999|
|C3|1.0000|11.3891|0.15|1.45|5.10|0.273|0.3979|
|C4|1.0000|10.7547|0.15|1.70|3.80|0.258|0.3995|

- C3 ฟื้นช้ากว่า C1 เท่าไร? recovery ของ C3 = 5.10 s และ C1 = 2.85 s (จาก metrics.csv) ผลต่าง 5.10 − 2.85 = 2.25 s C3 จึงฟื้นช้ากว่า C1 2.25 s สอดคล้องกับ k_clear ที่ลดจาก 0.6 เป็น 0.25 ทำให้ H ลดลงช้าหลังปิด stimulus ที่ 20 s (ความละเอียดของเวลาคือ 0.05 s)
- C2/C3 peak เท่ากันหรือไม่ และ metric ใดแยกได้? C2 และ C3 มี peak_H = 1.0000 เท่ากันเพราะชน upper bound จึงใช้ peak แยกไม่ได้ metric ที่แยกได้คือ recovery (C2 2.85 s, C3 5.10 s), rise 10–90 (C2 1.05 s, C3 1.45 s), latency (C2 0.10 s, C3 0.15 s), AUC (C2 10.672, C3 11.389 H·s) และ upper clamp fraction (C2 0.290, C3 0.273) สรุปคือ C2 ขึ้นเร็วกว่าเพราะ production สูง ส่วน C3 ค้างนานกว่าเพราะ clearance ต่ำ
- C0 มี H หรือไม่ / TV ต่ำพิสูจน์คุณภาพ gait ได้หรือไม่? C0 ไม่มี H ใน CSV ช่อง h, raw, p, c, b เป็นค่าว่าง และ peak_H, AUC เป็น N/A เพราะ C0 ใช้ R = S โดยตรง phi TV ของทุก condition ใกล้กันมาก (C0 0.4000, C1 0.3998, C3 0.3979 rad) ค่า TV ต่ำเพียงอย่างเดียวจึงพิสูจน์คุณภาพ gait ไม่ได้ เพราะ TV บอกแค่ผลรวมของการเปลี่ยนคำสั่ง ไม่ได้บอกจังหวะ ความเร็วในการตอบสนอง ความเสถียร หรือการเดินจริง และ Lab04 ยังไม่ได้รัน CPG

## D. Extreme tests และ handoff (10 นาที)

- zero: H = R = 0 ตลอด 30 s, phi = 0.20, stride = 0.055, fault = 0 (แถวท้าย 29.80–30.00 s เป็น 0 ทั้งหมด)
- one: H เพิ่มจนประมาณ 1 (≥ 0.999 ตั้งแต่ 8.50 s) แถวท้าย H = R = 1.0000, phi = 0.40, stride = 0.065, upper clamp fraction = 0, AUC 28.75
- Spike มี on interval 1 แถว (input_time_s = 10.00) นาน 0.05 s ได้ H = R = 0.0400 ที่ 10.05 แล้วลดลงเป็น 0.0384 ที่ 10.10 และ 0.0369 ที่ 10.15 หลัง fault ระบบ reset และกลับมาสะสมได้: แถวก่อน fault time_s 15.00 H = 0.9831, fault = 0; แถว fault time_s 15.05 (S = NaN) H = R = 0, raw = p = c = b = 0, fault = 1, phi = 0.2000, stride = 0.0550; แถวถัดไป 15.10 H = 0.0400 และ 15.15 H = 0.0784 เริ่มสะสมใหม่จากศูนย์ fault_count = 1
- Contract: ใช้ ../lab_03/results/week4_bridge/handoff_contract.json จาก Lab 03 runner รับได้ alpha = 1.1, dt = 0.05, lift = 0.03 ตรงเดิม ผล C1 เท่ากับที่ใช้ contract ที่แจก (AUC 9.9996, latency 0.15 s, recovery 2.85 s)
- R = 0 → phi 0.200 rad, stride 0.055 m; R = 1 → phi 0.400 rad, stride 0.065 m อยู่ใน bounds ทั้งคู่
- software bounds กับ actuator limits/emergency stop: software bounds คือการ clamp ค่าในโปรแกรม (H 0–1, phi 0.10–0.45 rad, stride 0.040–0.070 m) ซึ่งจำกัดเฉพาะคำสั่งที่ส่งออกไป actuator limits คือขีดจำกัดจริงของมอเตอร์และกลไก (มุม, torque, ความเร็ว) ที่ต้องดูจาก datasheet และตรวจกับหุ่นจริง ส่วน emergency stop เป็นกลไกหยุดฉุกเฉินแยกอิสระจาก software นี้ ใช้ได้แม้โปรแกรมผิดพลาด software bounds จึงไม่ได้แทนสองอย่างนี้
- สิ่งที่ Lab04 ยังไม่ได้ทดสอบ: Lab04 ยังไม่ได้รัน CPG ไม่ได้วัด body motion, gait, ความเสถียร พลังงาน หรือแรงสัมผัส และยังไม่ได้ทดสอบกับ sensor และหุ่นยนต์จริง (ผลทั้งหมดมาจาก simulator) ก่อนอ้างผลกับหุ่นจริงต้องเก็บหลักฐาน integrated test กับ CPG (Week05), การวัด actuator tracking, การทดสอบ fault กับ sensor จริง และยืนยัน limits/emergency stop ของฮาร์ดแวร์

## E. สรุปส่งงาน (10 นาที)

H ทำหน้าที่เป็นความจำของ stimulus: ทุก step H ใหม่ = H_old + dt·(P − C − B) เมื่อ S = 1 production ทำให้ H สะสมขึ้นเรื่อย ๆ จน clearance และ binding สมดุล และเมื่อ S กลับเป็น 0 H ยังค้างอยู่และลดลงตาม clearance/binding ไม่ได้หายทันทีแบบ C0 สมการ source คือ Hc(t) = β·Hc(t−1) + Hg − Hr จาก Homchanthanakul et al. (2019) ส่วนสมการ Euler ที่แยก P, C, B, ค่าอัตรา, bounds และ mapping ไป phi/stride เป็น proposed course model ของ Lab

ข้อมูลสนับสนุน prediction ว่า C2 ขึ้นเร็วกว่า (latency 0.10 s, rise 1.05 s เทียบกับ C1 0.15 s และ 2.70 s), C3 ค้างนานกว่า (recovery 5.10 s เทียบกับ 2.85 s) และ C4 ฟื้นช้ากว่า C1 (3.80 s) ส่วน prediction ว่า peak จะสูงกว่าต้องปรับ เพราะ C2–C4 มี peak_H = 1.0000 เท่ากันจากการ clamp (upper clamp 0.258–0.290) C0 ตอบสนองภายใน 0.05 s ที่ 10.05 s แต่ไม่มีความจำ การคำนวณมือ H = 0.0400 และ 0.0784 ตรงกับแถว 10.05 และ 10.10 ของ C1_step.csv และ fault ที่ 15.05 s reset แล้วสะสมใหม่ได้

ผลนี้มาจาก simulator ด้วย proposed course model ยังไม่ได้รัน CPG ไม่มี gait, dynamics หรือหุ่นจริง และค่าอัตราไม่ได้ปรับจากข้อมูลจริง ใน Week05 ควรต่อ R เข้ากับ CPG ของ Lab03 แล้วเปรียบเทียบแบบ one-factor เช่น เปลี่ยนเฉพาะ phi หรือเฉพาะ stride และเทียบ C0 กับ hormone condition ด้วยการวัด frequency, speed และ transient ของ gait จริงในแบบจำลอง เพื่อแยกผลของ hormone dynamics ออกจากผลของ CPG และ mapping

คำสั่งรัน: python lab04.py --controller-source student --condition all --profile step --output-dir results/comparison; --condition C1 --profile zero / one / spike / fault --output-dir results/zero, results/one, results/spike, results/fault; --condition C1 --profile step --contract ../lab_03/results/week4_bridge/handoff_contract.json --output-dir results/lab03_contract  config: results/*/config.json (controller_sha256 10f95bd776df33723a46edef8ac8920ba7072259beee898b5fe85f69b8fb56b5, runner_sha256 f66d8f29996644c2fb9cc3830298c3bd339080120e9eb657767eb7071b94e3cd)

Checklist: ☑ code ☑ comparison CSV 5 files ☑ extreme CSV 4 files ☑ config ☑ plots ☑ metrics □ report ☑ คำสั่งรันซ้ำ
