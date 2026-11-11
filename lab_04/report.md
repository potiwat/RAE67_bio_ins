# Lab 04 — Artificial Hormone Mechanism

## คำถามและ prediction

ทดสอบว่า stimulus เปลี่ยน hormone state ผ่าน production, clearance และ binding อย่างไร ก่อนส่ง receptor output ไปยัง `φ`/stride mapping. คาดว่า C2 (production สูงกว่า C1) จะสะสม H เร็วกว่า; C3 (clearance ต่ำกว่า) จะฟื้นช้ากว่า C1; C4 (ไม่มี binding) จะมี H มากกว่ากรณี C1. คาดว่า C0 ไม่มี H state เพราะใช้ direct `R=S`.

## วิธีการ

เติม `receptor` ให้ normalize และ clamp H พร้อมปฏิเสธค่า non-finite/range ที่ผิด และเติม `step` ให้ใช้ H/R เก่าคำนวณ P/C/B ก่อนอัปเดต H ใหม่ จากนั้นคำนวณ receptor ใหม่และส่งเข้าขอบเขต Week 03. Checker ผ่าน 13 test cases รวม receptor bounds, simultaneous old-state update, clamp และ invalid stimulus.

รัน C0–C4 ใน deterministic proposed course model: `dt=0.05 s`, duration `30 s`, H0=0, stimulus 0 ใน [0,10), 1 ใน [10,20), แล้ว 0 ใน [20,30). รันเพิ่ม C1 สำหรับ zero, one, spike (หนึ่ง input interval) และ fault (NaN ที่ input 15.00 s). ไม่มี random seed. ผล raw, config, metrics, graphs และ HTML อยู่ใน `results/lab04_complete_20261111/`.

## Controlled comparison

| Condition | peak H | AUC H (H·s) | latency (s) | rise 10–90% (s) | recovery (s) | upper clamp fraction | φ TV (rad) |
|---|---:|---:|---:|---:|---:|---:|---:|
| C0 | N/A | N/A | 0.050 | 0.000 | 0.050 | N/A | 0.400000 |
| C1 | 0.999715 | 9.999644 | 0.150 | 2.700 | 2.850 | 0.000000 | 0.399829 |
| C2 | 1.000000 | 10.672410 | 0.100 | 1.050 | 2.850 | 0.290000 | 0.399943 |
| C3 | 1.000000 | 11.389145 | 0.150 | 1.450 | 5.100 | 0.273333 | 0.397890 |
| C4 | 1.000000 | 10.754721 | 0.150 | 1.700 | 3.800 | 0.258333 | 0.399548 |

C0 ไม่มี hormone state; H-related fields เป็น null ไม่ใช่ศูนย์. C3 ฟื้นช้ากว่า C1 `5.10−2.85=2.25 s`. C2 และ C3 peak H เท่ากันที่ upper bound 1.0 แต่ AUC ต่างกัน 0.716735 H·s และ recovery ต่างกัน 2.25 s จึงต้องอ่าน AUC/recovery/clamp fraction ร่วมกับ peak. การเพิ่ม production ใน C2 ไม่ทำให้ peak สูงกว่า 1 เพราะ H ถูกจำกัดด้วย bound. C0 latency ใน log คือ 0.05 s จาก post-update sampling convention ไม่ใช่ sensor/hardware delay.

| Comparison | Prediction | Result |
|---|---|---|
| C2 vs C1 | production สูงทำให้ H เพิ่มเร็ว/สะสมมากขึ้น | C2 rise 1.05 s เทียบ C1 2.70 s; AUC 10.672410 เทียบ 9.999644 H·s; peak ถูก bound ที่ 1 |
| C3 vs C1 | clearance ต่ำทำให้ decay ช้า | recovery 5.10 เทียบ 2.85 s; AUC 11.389145 เทียบ 9.999644 H·s |
| C4 vs C1 | ตัด binding ทำให้ removal ลดลง | AUC 10.754721 เทียบ 9.999644 H·s; recovery 3.80 เทียบ 2.85 s |
| C0 vs C1 | C0 direct path ไม่มี hormone | C0 `peak_H`/AUC เป็น N/A; ไม่มี H state ใน CSV |

กราฟผลจริงจาก metrics/CSV:

- [H concentration](results/lab04_complete_20261111/comparison/h.svg)
- [receptor output](results/lab04_complete_20261111/comparison/r.svg)
- [φ command](results/lab04_complete_20261111/comparison/phi_rad.svg)
- [stride command](results/lab04_complete_20261111/comparison/stride_half_m.svg)
- [HTML report](results/lab04_complete_20261111/comparison/report.html)

## คำนวณและ extreme-input tests

สำหรับ C1 ที่ input 10.00 s, `H_old=0,S=1`: `P=.8`, `C=0`, `B=0`, `H_raw=.04`, `H_new=R_new=.04`, `φ=.208 rad`, `stride=.0554 m`. รอบถัดไป (input 10.05 s): `P=.8`, `C=.024`, `B=.008`, `H_raw=H_new=.0784`, `R=.0784`, `φ=.21568 rad`, `stride=.055784 m`. แถว input 10.00 บันทึก state หลัง update ที่ `time_s=10.05`.

zero profile คง peak H=0 และ command TV=0; one profile ให้ peak H≈1; spike มี input S=1 เพียงหนึ่งช่วงที่ 10.00 s และ peak H=.04. Fault row ที่ input 15.00 s บันทึก `fault=1`, H/R/raw/P/C/B=0, `φ=.20`, `stride=.055`; ที่ input 15.05 s stimulus กลับ valid และ H=R=.04 ที่ state 15.10 s. Software bounds/fallback ไม่ใช่ actuator limits หรือ emergency stop.

เมื่อ `R=0` mapping ให้ `φ=.20 rad`, stride half `.055 m`; เมื่อ `R=1` ให้ `.40 rad`, `.065 m`. Lab04 ส่งออก command เท่านั้น ยังไม่ได้รัน CPG/gait integration หรือทดสอบ hardware.

## สรุปและข้อจำกัด

ข้อมูลสนับสนุนว่าการเปลี่ยน production, clearance และ binding ส่งผลต่อ AUC และ recovery ขณะที่ upper clamp ทำให้ C2–C4 มี peak H เท่ากัน. ค่า `φ` total variation ใกล้กันไม่ใช่หลักฐานคุณภาพ gait; Lab04 ไม่มี gait output. ทุกอัตรา, bounds และ mapping เป็น proposed course model; ไม่มีการวัด actuator, sensor, stability หรือ locomotion จริง.

คำสั่งทำซ้ำ:

```powershell
python check_submission.py --student-file student_hormone.py
python lab04.py --controller-source student --condition all --profile step --output-dir results\lab04_complete_20261111\comparison
python lab04.py --controller-source student --condition C1 --profile zero --output-dir results\lab04_complete_20261111\zero
python lab04.py --controller-source student --condition C1 --profile one --output-dir results\lab04_complete_20261111\one
python lab04.py --controller-source student --condition C1 --profile spike --output-dir results\lab04_complete_20261111\spike
python lab04.py --controller-source student --condition C1 --profile fault --output-dir results\lab04_complete_20261111\fault
```

ค่าพารามิเตอร์และ SHA-256 ของ controller/runner ถูกบันทึกในแต่ละ `config.json`.
